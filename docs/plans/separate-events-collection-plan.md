# Separate Events into Their Own Collection

**Date:** 2026-04-01
**Goal:** Remove the growing `events` array from session documents to reduce document size and write contention under load.

---

## Why

Session documents embed an `events` array that grows every 20 seconds per active user (dummy events for timing). For a typical 30-minute quiz:

**Measured from production (session with 53 events, 60 questions):**
| Component | Size | % of doc |
|-----------|------|----------|
| `events` array | ~6 KB | 34% |
| `session_answers` array | ~11 KB | 64% |
| Metadata (user_id, quiz_id, metrics, etc.) | ~0.4 KB | 2% |
| **Total** | **~17 KB** | |

For longer sessions (90+ events), events grow to ~10-12KB, approaching 45% of the document.

Every 20 seconds, each active user's session document gets a `$push` or positional `$set` on the events array. At 10K users, that's 500 event writes/second, each touching a 17KB+ document. Removing events from sessions means these writes touch ~11KB documents instead — reducing WiredTiger cache churn and write amplification.

**The frontend never reads the events array.** Verified by searching the entire frontend codebase — `events` is only used for CSS `pointer-events`. Events are purely a backend concern for timing calculations.

---

## How Events Are Used Today

I traced every reference to `events` in the codebase. There are **3 use patterns**:

### Pattern 1: Timing Logic in `update_session` (PATCH /sessions/{id})

**File:** `sessions.py:350-453`

The endpoint reads `session["events"]` and uses it for:

| What | Lines | How |
|------|-------|-----|
| Check if quiz started | 354-356 | `session["events"][0].get("event_type") == start_quiz` |
| Get last event for timing | 370-373 | `last_event = session["events"][-1]` |
| Get last event index | 387 | `last_event_index = len(session["events"]) - 1` |
| Positional update (dummy coalescing) | 388-391 | `"events." + str(index) + ".updated_at"` |
| In-memory last event update | 394 | `session["events"][-1]["updated_at"] = ...` |
| Append new event | 412-416 | `$push: {"events": new_event_obj}` |
| Initialize events array | 363-368 | `$set: {"events": [new_event_obj]}` |

**Key insight:** The timing logic only ever needs the **last event** (type + timestamps). It never iterates the full array. The only exceptions are:
- `session["events"][0]` — check if first event was start-quiz (but `session.start_quiz_time` already covers this)
- `len(session["events"])` — used to compute the positional index for the last element

### Pattern 2: Session Continuation in `create_session` (POST /sessions)

**File:** `sessions.py:197-261`

When creating a new session, the code checks previous sessions' event state:

| What | Lines | How |
|------|-------|-----|
| Check events exist | 198 | `"events" in last_session` |
| Check no events occurred | 201 | `len(last_session["events"]) == 0` |
| Compare event counts | 206-207 | `len(last_session["events"]) == len(second_last["events"])` |
| Copy events to new session | 261 | `current_session["events"] = last_session.get("events", [])` |

**Key insight:** The continuation logic uses event **counts**, not event content. And it **copies the entire event array** to new sessions — this is expensive and unnecessary if events live in a separate collection.

### Pattern 3: Migration Scripts

| Script | What it does |
|--------|-------------|
| `remove_extra_dummy_events_in_sessions.py` | Finds sessions with >1000 events and squashes consecutive dummies |
| `backfill_time_limits_and_spent.py` | Reads events to compute timing fields for backfill |

These are one-time scripts, not hot paths. They'd need to read from the new collection instead.

---

## Proposed Approach

After analyzing the complexity, there are two viable options. **Option B is recommended** for its balance of impact vs. effort.

### Option A: Full Separation (High complexity)

Move ALL event data to a `session_events` collection. Sessions have zero event data.

```
session_events collection:
{
    _id: ObjectId,
    session_id: "session_123",
    event_type: "dummy-event",
    created_at: datetime,
    updated_at: datetime
}
Index: { session_id: 1, _id: -1 }
```

**Problem:** The `update_session` endpoint currently does a single atomic update on the session (events + timing fields together). With full separation, every event write becomes:
1. Read session (for timing fields) — 1 DB read
2. Read last event from events collection — 1 DB read
3. Write event to events collection — 1 DB write
4. Write timing fields to session — 1 DB write

That's **4 operations instead of 2** per event. For dummy events (every 20s per user), this doubles the DB operation count on the highest-frequency path. This is counterproductive.

Session creation also becomes complex — instead of copying an events array, we'd need to bulk-copy event documents or maintain a `last_event`/`event_count` denormalization on the session.

### Option B: Hybrid — Last Event on Session, History Separate (Recommended)

Keep a **denormalized `last_event` and `event_count`** on the session document. Move the full event history to a separate collection for ETL/scripts, but the hot path never reads it.

**Session document (modified):**
```python
{
    "_id": "session_123",
    "user_id": "...",
    "quiz_id": "...",
    "session_answers": [...],
    # Timing fields (already exist)
    "start_quiz_time": datetime,
    "end_quiz_time": datetime,
    "total_time_spent": float,
    "time_remaining": int,
    "time_limit_max": int,
    "has_quiz_ended": bool,
    # NEW: replaces the events array
    "event_count": 53,
    "last_event": {
        "event_type": "dummy-event",
        "created_at": datetime,
        "updated_at": datetime
    },
    # REMOVED: "events": [...]  ← no longer here
}
```

**New `session_events` collection (append-only log):**
```python
{
    "_id": ObjectId,
    "session_id": "session_123",
    "event_type": "dummy-event",
    "created_at": datetime,
    "updated_at": datetime
}
# Index:
{ "session_id": 1, "_id": -1 }
```

**Why this works:**

1. **`update_session` timing logic** — only needs `last_event` (type + timestamps). Currently reads `session["events"][-1]`. Now reads `session["last_event"]`. Same data, no array to traverse.

2. **`has_started` check** — currently checks `session["events"][0]`. Now uses `session["start_quiz_time"]` which is already precomputed and stored.

3. **Dummy event coalescing** — currently does a positional update `events.{index}.updated_at`. Now does `$set: {"last_event.updated_at": ...}`. Simpler and no index math.

4. **New event append** — currently `$push: {"events": new_event_obj}`. Now: `$set: {"last_event": new_event_obj}` on session + `$insert` on `session_events`. Two writes, but the session write is on a much smaller document.

5. **Session creation continuation** — currently checks `len(last_session["events"])`. Now checks `last_session["event_count"]`. No array copying needed — just copy the count and last_event.

6. **Event count increment** — `$inc: {"event_count": 1}` for non-dummy events (dummies just update `last_event.updated_at`, count stays same).

---

## Detailed Code Changes (Option B)

### `sessions.py` — `update_session` (PATCH /sessions/{id})

**Reading last event (line 370):**
```python
# BEFORE
last_event = session["events"][-1] if session.get("events") else None

# AFTER
last_event = session.get("last_event")
```

**has_started check (lines 354-357):**
```python
# BEFORE
has_started = session.get("start_quiz_time") is not None or (
    session.get("events")
    and session["events"][0].get("event_type") == EventType.start_quiz
)

# AFTER
has_started = session.get("start_quiz_time") is not None
```

**First event initialization (lines 363-368):**
```python
# BEFORE
if session["events"] is None:
    session["events"] = [new_event_obj]
    session_update_query["$set"] = {"events": [new_event_obj]}

# AFTER
if last_event is None:
    session_update_query.setdefault("$set", {}).update({
        "last_event": new_event_obj,
        "event_count": 1,
    })
    # Also insert into events collection
    await client.quiz.session_events.insert_one({
        "session_id": session_id, **new_event_obj
    })
```

**Dummy event coalescing (lines 386-398):**
```python
# BEFORE
last_event_index = len(session["events"]) - 1
last_event_update_query = {
    "events." + str(last_event_index) + ".updated_at": new_event_obj["created_at"]
}

# AFTER
session_update_query.setdefault("$set", {}).update({
    "last_event.updated_at": new_event_obj["created_at"]
})
# Update the last event in events collection too
await client.quiz.session_events.update_one(
    {"session_id": session_id},
    {"$set": {"updated_at": new_event_obj["created_at"]}},
    sort=[("_id", -1)]  # most recent
)
```

> Note: `update_one` with sort requires using `find_one_and_update`. Alternative: store the last event's `_id` on the session for direct updates.

**New event append (lines 411-416):**
```python
# BEFORE
session["events"].append(new_event_obj)
session_update_query["$push"] = {"events": new_event_obj}

# AFTER
session_update_query.setdefault("$set", {}).update({
    "last_event": new_event_obj,
})
session_update_query.setdefault("$inc", {}).update({
    "event_count": 1,
})
await client.quiz.session_events.insert_one({
    "session_id": session_id, **new_event_obj
})
```

### `sessions.py` — `create_session` (POST /sessions)

**Event count checks (lines 197-210):**
```python
# BEFORE
"events" in last_session
len(last_session["events"]) == 0
len(last_session["events"]) == len(second_last_session["events"])

# AFTER
last_session.get("event_count", 0) == 0
last_session.get("event_count", 0) == second_last_session.get("event_count", 0)
```

**Event copying (line 261):**
```python
# BEFORE
current_session["events"] = last_session.get("events", [])

# AFTER
current_session["event_count"] = last_session.get("event_count", 0)
current_session["last_event"] = last_session.get("last_event", None)
# No need to copy event documents — they stay linked to the original session_id
# The new session starts its own event history from this point
```

### `models.py` — Session model

```python
# BEFORE
events: List[Event] = []

# AFTER
event_count: int = 0
last_event: Optional[Event] = None
```

### Migration scripts

Both scripts (`remove_extra_dummy_events_in_sessions.py`, `backfill_time_limits_and_spent.py`) need to read from `session_events` collection instead of `session.events`. These are one-time scripts and can be updated when needed.

---

## Data Migration

Existing sessions have the `events` array. New sessions will have `event_count` + `last_event`. We need a migration to:

1. **Backfill `event_count` and `last_event`** on existing sessions
2. **Copy events to `session_events` collection** (for script compatibility)
3. **Remove `events` array from sessions** (to reclaim space)

```python
# Migration script (run once)
for session in db.sessions.find({"events": {"$exists": True}}):
    events = session.get("events") or []
    if events:
        # Insert events into new collection
        event_docs = [{"session_id": session["_id"], **e} for e in events]
        db.session_events.insert_many(event_docs)
    
    # Update session with denormalized fields
    db.sessions.update_one(
        {"_id": session["_id"]},
        {
            "$set": {
                "event_count": len(events),
                "last_event": events[-1] if events else None,
            },
            "$unset": {"events": ""}
        }
    )
```

**Estimated migration time:** Depends on session count. Can be done in batches with `bulk_write`.

---

## Expected Impact

| Metric | Before | After |
|--------|--------|-------|
| Session document size (53 events, 60 questions) | ~17 KB | ~11 KB (-34%) |
| Session document size (90 events, 51 questions) | ~22 KB | ~12 KB (-45%) |
| Dummy event write (every 20s/user) | `$set` on 17-22KB doc | `$set` on 11-12KB doc + small insert |
| WiredTiger cache pressure | Full session on every event write | Smaller session + tiny event doc |
| Session read for batch update / GET | Includes full event history | No events (34-45% smaller) |

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Dummy coalescing needs `find_one_and_update` for last event | Store `last_event_id` on session for direct updates. Or accept one extra read — it's a small document. |
| Migration on large session collection is slow | Run in batches during off-peak. Mark migrated sessions with a flag to allow incremental migration. |
| Old sessions without `last_event` field | Code checks `session.get("last_event")` with fallback. Migration backfills all. |
| ETL reads events from sessions | ETL needs updating to read from `session_events` collection. Can be done before or after migration. |
| Two writes per event (session + events collection) | The session write is much smaller, and the events insert is a tiny document. Net win under load. |

---

## Execution Order

1. **Motor migration** (prerequisite — need async for concurrent event writes)
2. **Create `session_events` collection + index** in both clusters
3. **Update `models.py`** — add `event_count`, `last_event`; remove `events`
4. **Update `sessions.py`** — rewrite event handling in `update_session` and `create_session`
5. **Run data migration** — backfill existing sessions, copy events to new collection
6. **Update migration scripts** to read from `session_events`
7. **Update ETL** if it reads events from sessions
8. **Deploy and test**

---

## Alternative: Projection-Only Approach (Simpler)

If the full separation feels too risky, a simpler alternative: just **exclude events from session reads that don't need them** using MongoDB projections.

```python
# For batch update, GET session, etc. — exclude events
session = await client.quiz.sessions.find_one(
    {"_id": session_id},
    {"events": 0}  # don't load events
)

# For update_session — load everything (status quo)
session = await client.quiz.sessions.find_one({"_id": session_id})
```

**Impact:** Reduces read size for ~70% of session reads by 34-45%. Zero schema changes, zero migration, minimal code change. Doesn't help with write amplification though — event pushes still touch the full document.

This could be a quick win now, with full separation done later if needed.
