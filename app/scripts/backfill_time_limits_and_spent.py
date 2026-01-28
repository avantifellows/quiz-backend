#!/usr/bin/env python
"""
Backfill script to populate session timing fields for a targeted set of sessions:
- time_limit_max (from quiz.time_limit.max)
- start_quiz_time (from the first start-quiz event)
- end_quiz_time (from the last end-quiz event)
- total_time_spent (computed from events; float, allows incomplete sessions)
- time_remaining (derived: time_limit_max - total_time_spent for timed quizzes)
- updated_at (last event timestamp if present, else created_at)

Key behavior:
- Scope: latest session per (user_id, quiz_id) where:
  - has_quiz_ended == False, OR
  - created_at is within the last 2 months
- Safe to run multiple times; only sets fields when values are available.
- For untimed quizzes (no time_limit_max), time_remaining is left untouched.
- Uses the same time computation semantics as backend/ETL, including capped gaps for non-dummy events.
"""

import os
import time
from datetime import datetime, timedelta
from typing import Optional

from pymongo import UpdateOne
from bson import ObjectId

import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.append(ROOT)

from database import client  # noqa: E402
from schemas import EventType  # noqa: E402


RECENT_SESSION_DAYS = 120  # backfill sessions from past 60 days -- to avoid etl errors
OPEN_SESSION_DAYS = (
    400  # backfill "open" sessions from past one year -- in case students resume
)


def str_to_datetime(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _time_elapsed_secs(dt_1, dt_2) -> float:
    d1 = str_to_datetime(dt_1)
    d2 = str_to_datetime(dt_2)
    if d1 is None or d2 is None:
        return 0
    return (d1 - d2).total_seconds()


def compute_time_spent_from_events(
    events, allow_incomplete: bool = False
) -> Optional[float]:
    """
    Compute total time spent from events (same as backend logic).
    Returns seconds as a float (rounded to 2 decimals) or None.

    Rules:
    - Requires a start-quiz as the first event.
    - Dummy events add (gap since previous event end) + (dummy duration).
      If a dummy follows a dummy, only add the gap since the previous dummy ended.
    - Resume events add a capped gap (<= 20s) only if the previous event wasn't a dummy.
    - End-quiz adds the full gap since previous event end.
    - If allow_incomplete is False and the session looks in-progress, returns None.
    """
    if not events:
        return None
    first_event = events[0]
    if not first_event or first_event.get("event_type") != EventType.start_quiz:
        return None
    total_time_spent = 0.0
    previous_event = first_event
    for event in events[1:]:
        if "created_at" not in event:
            continue
        etype = event.get("event_type")
        prev_type = previous_event.get("event_type")
        prev_end = previous_event.get("updated_at") or previous_event.get("created_at")
        if etype == EventType.dummy_event:
            if prev_type == EventType.dummy_event:
                delta = _time_elapsed_secs(event.get("created_at"), prev_end)
            else:
                delta = _time_elapsed_secs(event.get("created_at"), prev_end)
                delta += _time_elapsed_secs(
                    event.get("updated_at"), event.get("created_at")
                )
            if delta > 0:
                total_time_spent += float(delta)
        elif etype == EventType.end_quiz:
            delta = _time_elapsed_secs(event.get("created_at"), prev_end)
            if delta > 0:
                total_time_spent += float(delta)
        elif etype == EventType.resume_quiz:
            # Resume adds a capped gap only if the previous event wasn't a dummy window.
            if prev_type != EventType.dummy_event:
                gap = _time_elapsed_secs(event.get("created_at"), prev_end)
                total_time_spent += max(0, min(gap, 20))
        previous_event = event
    if total_time_spent == 0 and not allow_incomplete:
        return None
    return round(float(total_time_spent), 2)


def main():
    db = client.quiz
    sessions = db.sessions
    quizzes = db.quizzes

    cutoff = datetime.utcnow() - timedelta(days=RECENT_SESSION_DAYS)
    start_object_id = ObjectId.from_datetime(cutoff)
    open_match = {"has_quiz_ended": False}
    if OPEN_SESSION_DAYS > 0:
        open_cutoff = datetime.utcnow() - timedelta(days=OPEN_SESSION_DAYS)
        open_object_id = ObjectId.from_datetime(open_cutoff)
        open_match["_id"] = {"$gte": f"{open_object_id}"}
    print(
        "Starting backfill "
        f"(RECENT_SESSION_DAYS={RECENT_SESSION_DAYS}, "
        f"OPEN_SESSION_DAYS={OPEN_SESSION_DAYS})"
    )
    # Backfill scope:
    # - all sessions with has_quiz_ended == False
    # - all sessions from the last 2 months
    # But only the latest session per (user_id, quiz_id)
    candidate_match = {
        "$or": [
            open_match,
            {"_id": {"$gte": f"{start_object_id}"}},
        ]
    }

    pipeline = [
        {"$match": candidate_match},
        {
            "$project": {
                "_id": 1,
                "user_id": 1,
                "quiz_id": 1,
                "events": 1,
                "created_at": 1,
                "updated_at": 1,
                "has_quiz_ended": 1,
                "time_limit_max": 1,
                "start_quiz_time": 1,
                "end_quiz_time": 1,
                "total_time_spent": 1,
                "time_remaining": 1,
            }
        },
        {"$sort": {"quiz_id": 1, "user_id": 1, "_id": -1}},
        {
            "$group": {
                "_id": {"user_id": "$user_id", "quiz_id": "$quiz_id"},
                "doc": {"$first": "$$ROOT"},
            }
        },
        {"$replaceRoot": {"newRoot": "$doc"}},
    ]

    updates = []
    batch_size = 500
    count = 0
    processed = 0
    start_time = time.time()
    quiz_time_limit_cache = {}

    print("Running aggregation...")
    for doc in sessions.aggregate(pipeline, allowDiskUse=True):
        processed += 1
        if processed % 500 == 0:
            elapsed = time.time() - start_time
            print(f"Processed {processed} sessions in {elapsed:.1f}s...")
        sid = doc["_id"]
        quiz_id = doc.get("quiz_id")
        events = doc.get("events")

        # Fetch quiz time_limit.max if missing on the session
        time_limit_max = doc.get("time_limit_max")
        if time_limit_max is None and quiz_id:
            if quiz_id in quiz_time_limit_cache:
                time_limit_max = quiz_time_limit_cache[quiz_id]
            else:
                quiz = quizzes.find_one({"_id": quiz_id})
                if (
                    quiz
                    and quiz.get("time_limit")
                    and quiz["time_limit"].get("max") is not None
                ):
                    time_limit_max = quiz["time_limit"]["max"]
                quiz_time_limit_cache[quiz_id] = time_limit_max

        # Compute total_time_spent only if it's missing
        total_time_spent = doc.get("total_time_spent")
        if total_time_spent is None and events:
            total_time_spent = compute_time_spent_from_events(
                events, allow_incomplete=True
            )

        # Derive start/end times from events if missing
        start_quiz_time = doc.get("start_quiz_time")
        end_quiz_time = doc.get("end_quiz_time")
        if start_quiz_time is None and events:
            start_evt = next(
                (e for e in events if e.get("event_type") == EventType.start_quiz), None
            )
            if start_evt:
                start_quiz_time = start_evt.get("created_at")
        if end_quiz_time is None and events:
            for e in reversed(events):
                if e.get("event_type") == EventType.end_quiz:
                    end_quiz_time = e.get("created_at")
                    break

        # Derive time_remaining only for timed quizzes
        time_remaining = doc.get("time_remaining")
        if (
            time_remaining is None
            and time_limit_max is not None
            and total_time_spent is not None
        ):
            time_remaining = max(0, int(time_limit_max) - int(total_time_spent))

        set_fields = {}
        # Preserve activity ordering: updated_at = last event timestamp if present
        if doc.get("updated_at") is None:
            updated_at = None
            if events:
                last_event = events[-1]
                updated_at = last_event.get("updated_at") or last_event.get(
                    "created_at"
                )
            if updated_at is None:
                updated_at = doc.get("created_at")
            if updated_at is not None:
                set_fields["updated_at"] = updated_at
        if time_limit_max is not None:
            set_fields["time_limit_max"] = time_limit_max
        if total_time_spent is not None:
            set_fields["total_time_spent"] = round(float(total_time_spent), 2)
        if time_remaining is not None:
            set_fields["time_remaining"] = int(time_remaining)
        if start_quiz_time is not None:
            set_fields["start_quiz_time"] = start_quiz_time
        if end_quiz_time is not None:
            set_fields["end_quiz_time"] = end_quiz_time

        if not set_fields:
            continue
        updates.append(UpdateOne({"_id": sid}, {"$set": set_fields}))

        if len(updates) >= batch_size:
            sessions.bulk_write(updates, ordered=False)
            count += len(updates)
            print(f"Updated {count} sessions...")
            updates = []

    if updates:
        sessions.bulk_write(updates, ordered=False)
        count += len(updates)

    print(f"Backfill complete. Updated {count} sessions.")


if __name__ == "__main__":
    main()
