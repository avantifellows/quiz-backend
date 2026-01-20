#!/usr/bin/env python
"""
Backfill script to populate session timing fields:
- time_limit_max (from quiz.time_limit.max)
- start_quiz_time (from the first start-quiz event)
- end_quiz_time (from the last end-quiz event)
- total_time_spent (computed from events; allows incomplete sessions)
- time_remaining (derived: time_limit_max - total_time_spent for timed quizzes)
- updated_at (set to now if missing)

Key behavior:
- Safe to run multiple times; updates only documents missing these fields.
- For untimed quizzes (no time_limit_max), time_remaining is left untouched.
- Uses the same time computation semantics as backend/ETL, including capped gaps for non-dummy events.
"""

import os
from datetime import datetime
from typing import Optional

from pymongo import UpdateOne

import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.append(ROOT)

from database import client  # noqa: E402
from schemas import EventType  # noqa: E402


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
) -> Optional[int]:
    """
    Compute total time spent from events (same as backend logic).
    Returns int seconds (floored) or None.

    Rules:
    - Requires a start-quiz as the first event.
    - Dummy events add (gap since previous event end) + (dummy duration).
    - Non-dummy, non-end events (e.g., resume) add a capped gap: min(gap, 20s).
    - End-quiz adds the full gap since previous event end.
    - If allow_incomplete is False and the session looks in-progress, returns None.
    """
    if not events:
        return None
    first_event = events[0]
    if not first_event or first_event.get("event_type") != EventType.start_quiz:
        return None
    total_time_spent = 0
    previous_event = first_event
    for event in events[1:]:
        if "created_at" not in event or "updated_at" not in event:
            continue
        etype = event.get("event_type")
        if etype == EventType.dummy_event:
            total_time_spent += _time_elapsed_secs(
                event.get("created_at"), previous_event.get("updated_at")
            )
            total_time_spent += _time_elapsed_secs(
                event.get("updated_at"), event.get("created_at")
            )
        elif etype != EventType.end_quiz:
            # Non-dummy, non-end: add a capped gap to avoid over-counting long idle periods.
            gap = _time_elapsed_secs(
                event.get("created_at"), previous_event.get("updated_at")
            )
            total_time_spent += max(0, min(gap, 20))
        elif etype == EventType.end_quiz:
            total_time_spent += _time_elapsed_secs(
                event.get("created_at"), previous_event.get("updated_at")
            )
        previous_event = event
    if total_time_spent == 0 and not allow_incomplete:
        return None
    return int(total_time_spent)


def main():
    db = client.quiz
    sessions = db.sessions
    quizzes = db.quizzes

    query = {
        "$or": [
            {"time_limit_max": {"$exists": False}},
            {"total_time_spent": {"$exists": False}},
            {"time_remaining": {"$exists": False}},
            {"start_quiz_time": {"$exists": False}},
            {"end_quiz_time": {"$exists": False}},
            {"updated_at": {"$exists": False}},
        ]
    }

    updates = []
    batch_size = 500
    count = 0

    for doc in sessions.find(query):
        sid = doc["_id"]
        quiz_id = doc.get("quiz_id")
        events = doc.get("events") or []

        # fetch quiz time_limit.max if available
        time_limit_max = doc.get("time_limit_max")
        if time_limit_max is None and quiz_id:
            quiz = quizzes.find_one({"_id": quiz_id})
            if (
                quiz
                and quiz.get("time_limit")
                and quiz["time_limit"].get("max") is not None
            ):
                time_limit_max = quiz["time_limit"]["max"]

        total_time_spent = doc.get("total_time_spent")
        if total_time_spent is None:
            total_time_spent = compute_time_spent_from_events(
                events, allow_incomplete=True
            )

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

        time_remaining = doc.get("time_remaining")
        if time_limit_max is not None and total_time_spent is not None:
            time_remaining = max(0, int(time_limit_max) - int(total_time_spent))

        set_fields = {}
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
            set_fields["total_time_spent"] = int(total_time_spent)
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
