# Quiz System Performance Bottleneck Analysis & Optimization Plan

**Date:** 2026-04-01
**Context:** Load testing at 10K concurrent users revealed a critical bottleneck. This document traces the issue end-to-end through frontend and backend code with actionable fixes.

---

## The Problem

Under load testing (10K bot users, 10 ECS containers, M10 MongoDB), the system showed:

| Endpoint | Requests | Failure Rate | Median | p95 |
|----------|----------|-------------|--------|-----|
| All endpoints (excl. batch update) | 468,743 | **0.09%** | 67ms | 270ms |
| **PATCH update-multiple-answers** | **8,999** | **54.14%** | **5,200ms** | **14,000ms** |

**87% of all failures came from a single endpoint**: the batch update that fires when a user ends their quiz. Everything else works fine under load.

At 7-8K users the failure rate drops to 24%, and all other endpoints remain healthy. The batch update endpoint is the sole limiting factor preventing the system from scaling beyond ~7K concurrent bot users on M10.

---

## End-to-End Flow: What Happens When a User Ends Their Quiz

### Frontend (Player.vue)

```
1. User clicks "End Test"
2. endTest() builds payload: ALL answers with answer, visited, time_spent, marked_for_review
3. PATCH /session_answers/{sessionId}/update-multiple-answers  ← THE BOTTLENECK
   - Sends array of [position, answer_payload] for every question (e.g., 51 tuples)
   - Frontend has a 4-second timeout (axios)
   - If this fails → show error toast, user must retry manually
4. PATCH /sessions/{sessionId} with event: "end-quiz"
   - Backend computes session metrics (scoring) synchronously
   - If this fails → show error toast, user must retry
5. Fetch metrics (with retry: 3 attempts, 1.2s→2.4s→4.8s backoff)
6. Show scorecard
```

### Backend: Batch Update Endpoint

**File:** `quiz-backend/app/routers/session_answers.py:15-84`

```python
async def update_session_answers_at_specific_positions(session_id, positions_and_answers):
    # STEP 1: Read entire session document
    session = client.quiz.sessions.find_one({"_id": session_id})    # ← BLOCKING READ

    # STEP 2: Validate session exists, answers exist, positions in bounds
    # (iterates through session document)

    # STEP 3: Build flat $set query
    setQuery = {
        f"session_answers.{pos}.{key}": value
        for pos, answer in zip(positions, answers)
        for key, value in answer.items()
    }

    # STEP 4: Execute atomic update
    result = client.quiz.sessions.update_one({"_id": session_id}, {"$set": setQuery})  # ← BLOCKING WRITE
```

### Backend: End-Quiz Event

**File:** `quiz-backend/app/routers/sessions.py:322-524`

```python
async def update_session(session_id, session_updates):
    # STEP 1: Read entire session document
    session = client.quiz.sessions.find_one({"_id": session_id})    # ← BLOCKING READ

    # STEP 2: If end-quiz event:
    #   a. Read quiz document
    quiz = client.quiz.quizzes.find_one({"_id": session["quiz_id"]})  # ← BLOCKING READ
    #   b. Compute metrics synchronously (iterates all questions)
    session_metrics = compute_session_metrics(session, quiz)          # ← CPU-BOUND

    # STEP 3: Write metrics + end state back
    client.quiz.sessions.update_one({"_id": session_id}, {"$set": {...}})  # ← BLOCKING WRITE
```

---

## Root Causes (Ranked by Impact)

### 1. Synchronous PyMongo on Async FastAPI (HIGH IMPACT)

**File:** `quiz-backend/app/requirements.txt` → `pymongo==4.0.2`
**File:** `quiz-backend/app/database.py`

FastAPI is async, but PyMongo is synchronous. Every `find_one()` and `update_one()` **blocks the entire worker thread**. With 4 Uvicorn workers per container:

- Each worker can handle only 1 DB operation at a time
- If a query takes 100ms, that worker is blocked for 100ms
- Max throughput per container: ~40 requests/sec (4 workers × 10 ops/sec)
- At 10K users generating ~1,300 RPS across 10 containers → **130 RPS per container** needed, but only ~40 achievable

### 2. Unnecessary Read-Before-Write (HIGH IMPACT)

Both the batch update and end-quiz endpoints do a full `find_one()` before the `update_one()`. For the batch update, this read is used only for validation (session exists, answers exist, positions in bounds). But MongoDB's `update_one()` already returns `matched_count` which tells you if the document was found.

**Current:** 2 DB operations per batch update (read + write)
**Optimal:** 1 DB operation per batch update (write only)

This doubles the load on MongoDB for every end-quiz flow.

### 3. Large Embedded Documents (MEDIUM IMPACT)

Sessions embed everything: answers, events, metrics. A typical session document for a 51-question, 30-minute quiz:

- `session_answers`: 51 embedded documents (~5KB)
- `events`: ~90 dummy events at 20s intervals (~9KB)
- `metrics`: nested qset_metrics (~2KB)
- **Total: ~20-30KB per session document**

Every `update_one()` must locate and update this large document. Under concurrent writes from thousands of users, this creates I/O pressure on M10's 512MB WiredTiger cache.

### 4. Frontend 4-Second Timeout (MEDIUM IMPACT)

**File:** `quiz-frontend/src/services/API/RootClient.ts`

```typescript
const client = axios.create({
    timeout: 4000,  // 4 seconds
});
```

Under load, the batch update takes 5-14 seconds (p50-p95). The frontend times out at 4 seconds, treating it as a failure — but the backend may still complete the write. This creates:
- False failures from the user's perspective
- Potential duplicate writes on retry
- Ghost sessions where answers are saved but end-quiz never fires

### 5. Connection Pool Configuration (LOW-MEDIUM IMPACT)

**File:** `quiz-backend/app/database.py`

```python
client = MongoClient(
    maxPoolSize=20,   # per worker process
    minPoolSize=5,
)
```

With 4 Uvicorn workers per container: 80 connections per container.
With 10 containers: 800 total connections.
M10 Atlas limit: ~1,500 connections.

Not the primary bottleneck, but contributes to contention under peak load.

---

## Optimization Recommendations

### P0: Quick Wins (1-2 days, no architecture changes)

#### 1. Remove Read-Before-Write in Batch Update

**File:** `quiz-backend/app/routers/session_answers.py`

**Current (lines 29-72):**
```python
session = client.quiz.sessions.find_one({"_id": session_id})  # unnecessary read
# ... validation ...
result = client.quiz.sessions.update_one({"_id": session_id}, {"$set": setQuery})
```

**Proposed:**
```python
# Build setQuery directly (skip validation — MongoDB handles atomically)
setQuery = {
    f"session_answers.{pos}.{key}": value
    for pos, answer in zip(positions, input_session_answers)
    for key, value in answer.items()
}
setQuery["updated_at"] = datetime.utcnow()

result = client.quiz.sessions.update_one({"_id": session_id}, {"$set": setQuery})
if result.matched_count == 0:
    raise HTTPException(status_code=404, detail=f"session {session_id} not found")
```

**Impact:** Cuts MongoDB operations in half for this endpoint. One fewer network roundtrip per end-quiz.

#### 2. Increase Frontend Timeout for End-Quiz

**File:** `quiz-frontend/src/services/API/RootClient.ts` or per-request override

For the batch update and end-quiz calls specifically, increase timeout:
```typescript
// In SessionAPIService methods for end-quiz flow:
const response = await apiClient().patch(url, payload, { timeout: 15000 }); // 15s for end-quiz
```

**Impact:** Eliminates false timeout failures. Under load, the backend often completes in 5-9 seconds — the 4-second timeout was causing "failures" for requests that would have succeeded.

---

### P1: Medium Effort (1-2 weeks)

#### 3. Migrate from PyMongo to Motor (Async Driver)

**Files:** `quiz-backend/app/database.py`, all files in `routers/`

Replace `pymongo` with `motor` (async MongoDB driver for Python):

```python
# database.py
from motor.motor_asyncio import AsyncIOMotorClient

client = AsyncIOMotorClient(
    os.getenv("MONGO_AUTH_CREDENTIALS"),
    maxPoolSize=20,
    minPoolSize=5,
)

# In routers:
session = await client.quiz.sessions.find_one({"_id": session_id})  # non-blocking
result = await client.quiz.sessions.update_one(...)                   # non-blocking
```

**Impact:** This is the single highest-impact change. Currently, each PyMongo call blocks the entire worker thread. With Motor, FastAPI can handle concurrent requests while waiting for MongoDB responses. Expected 5-10x improvement in per-container throughput.

**Effort:** Every `client.quiz.*.find_one()`, `update_one()`, `find()`, `insert_one()` call across all routers needs `await`. It's a mechanical change but touches many files.

#### 4. Separate Events into Their Own Collection

**Current:** Events are embedded in the session document as an array that grows every 20 seconds.

**Proposed:**
```python
# New collection: session_events
{
    "_id": ObjectId,
    "session_id": "session_123",
    "event_type": "dummy-event",
    "created_at": datetime
}

# Index:
db.session_events.createIndex({ "session_id": 1, "created_at": -1 })
```

**Impact:** Session documents become ~50% smaller (no events array). Smaller documents = faster reads and writes, less WiredTiger cache pressure. The events are write-heavy (every 20s per user) but almost never read — perfect candidate for separation.

#### 5. Cache Quiz Documents

**File:** `quiz-backend/app/routers/sessions.py` (end-quiz path)

Quiz documents are immutable during a test. They're fetched on every end-quiz event to compute metrics:
```python
quiz = client.quiz.quizzes.find_one({"_id": session["quiz_id"]})
```

Add an in-memory or Redis cache:
```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_quiz(quiz_id: str):
    return client.quiz.quizzes.find_one({"_id": quiz_id})
```

Or with Redis for multi-container consistency:
```python
quiz = redis_client.get(f"quiz:{quiz_id}")
if not quiz:
    quiz = client.quiz.quizzes.find_one({"_id": quiz_id})
    redis_client.setex(f"quiz:{quiz_id}", 3600, json.dumps(quiz))
```

**Impact:** Eliminates one MongoDB read per end-quiz event. At 10K users all ending quizzes = 10K fewer reads.

---

### P2: Larger Changes (2-4 weeks)

#### 6. Async Metrics Computation

Currently, `compute_session_metrics()` runs synchronously inside the end-quiz request handler. Under load, this creates a CPU bottleneck.

**Option A: Background task**
```python
from fastapi import BackgroundTasks

@router.patch("/{session_id}")
async def update_session(session_id, session_updates, background_tasks: BackgroundTasks):
    if new_event == EventType.end_quiz:
        # Mark quiz as ended immediately
        await client.quiz.sessions.update_one(
            {"_id": session_id},
            {"$set": {"has_quiz_ended": True, "end_quiz_time": datetime.utcnow()}}
        )
        # Compute metrics in background
        background_tasks.add_task(compute_and_store_metrics, session_id)
        return {"status": "ended", "metrics": None}  # Frontend retries for metrics
```

**Option B: Separate metrics endpoint**
- End-quiz just marks the session as ended
- Frontend polls a dedicated `GET /sessions/{id}/metrics` endpoint
- Backend computes lazily on first request, caches result

**Impact:** End-quiz response time drops from 500ms+ to ~50ms. Frontend already has retry logic for delayed metrics (3 attempts with exponential backoff), so this works seamlessly.

#### 7. Chunk the Batch Update on Frontend

Instead of sending all 51 answers in one request, chunk into smaller batches:

**File:** `quiz-frontend/src/views/Player.vue` (endTest function)

```typescript
async function endTest() {
    const CHUNK_SIZE = 15;
    const allAnswers = buildAllAnswerPayloads(); // existing logic

    // Send in parallel chunks
    const chunks = [];
    for (let i = 0; i < allAnswers.length; i += CHUNK_SIZE) {
        chunks.push(allAnswers.slice(i, i + CHUNK_SIZE));
    }

    const results = await Promise.all(
        chunks.map(chunk =>
            SessionAPIService.updateSessionAnswersAtSpecificPositions(state.sessionId, chunk)
        )
    );

    if (results.some(r => r.status !== 200)) {
        // handle partial failure
        return;
    }

    // Then send end-quiz event
    await SessionAPIService.updateSession(state.sessionId, { event: eventType.END_QUIZ });
}
```

**Impact:** Each chunk is a smaller MongoDB update (~15 fields vs 51). Reduces per-request document write size and WiredTiger cache pressure. Parallel execution means total time is roughly the same as a single chunk.

**Trade-off:** More HTTP requests but each is lighter on the database.

---

## Expected Impact Summary

| Fix | Effort | MongoDB Ops Reduction | Latency Improvement | Failure Rate Impact |
|-----|--------|----------------------|---------------------|-------------------|
| Remove read-before-write | 1 hour | 50% on batch update | 30-40% on batch update | Significant |
| Increase frontend timeout | 30 min | - | - | Eliminates false failures |
| PyMongo → Motor | 1-2 weeks | - | 5-10x container throughput | Major |
| Separate events collection | 3-5 days | - | 30-40% on all session ops | Moderate |
| Cache quiz documents | 1-2 days | 1 read per end-quiz | 20-30% on end-quiz | Minor |
| Async metrics computation | 3-5 days | - | 80-90% on end-quiz response | Significant |
| Chunk batch update | 2-3 days | - | Reduces peak write size | Moderate |

**Implementing P0 fixes alone (remove read + increase timeout) should bring the batch update failure rate from 54% to under 10% at 10K users.** Adding Motor (P1) would likely push it under 1%.

> **Note on indexes:** Compound indexes on sessions (`{quiz_id: 1, user_id: 1}` and `{quiz_id: 1, user_id: 1, _id: -1}`) already exist on both production and staging clusters (created directly in Atlas). These were not in the application code, but they are present and covering the critical session lookup queries. No index changes needed.

---

## Files to Modify

| Priority | File | Change |
|----------|------|--------|
| P0 | `quiz-backend/app/routers/session_answers.py` | Remove `find_one()`, use `matched_count` |
| P0 | `quiz-frontend/src/services/API/RootClient.ts` | Increase timeout for end-quiz calls |
| P1 | `quiz-backend/app/database.py` | Switch to Motor async client |
| P1 | `quiz-backend/app/routers/*.py` | Add `await` to all DB calls |
| P1 | `quiz-backend/app/requirements.txt` | Replace `pymongo` with `motor` |
| P1 | `quiz-backend/app/models.py` | Separate Event model into own collection |
| P1 | `quiz-backend/app/routers/sessions.py` | Cache quiz lookups |
| P2 | `quiz-backend/app/routers/sessions.py` | Background task for metrics |
| P2 | `quiz-frontend/src/views/Player.vue` | Chunk endTest batch update |

---

## Test Data for Reference

**Load test results (2026-04-01):**
- 10K users, 10 containers, M10: 54% batch update failure rate, 0.09% on everything else
- 7-8K users, 7-8 containers, M10: 24% batch update failure rate, 0.003% on everything else
- Full reports: `cc-test-reports/2026-04-01-10k-m10-load-test.md` and `2026-04-01-7k-8k-m10-load-test.md`
