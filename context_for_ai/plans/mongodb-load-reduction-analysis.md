# MongoDB Load Reduction Analysis & Proposed Solutions

> **Created:** January 4, 2026
> **Status:** Analysis Complete - Pending Review
> **Related:** Load testing observations showing high CPU on MongoDB

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current Architecture Analysis](#current-architecture-analysis)
3. [Identified Bottlenecks](#identified-bottlenecks)
4. [Proposed Solutions](#proposed-solutions)
5. [Implementation Priority Matrix](#implementation-priority-matrix)
6. [Detailed Solution Specifications](#detailed-solution-specifications)

---

## Executive Summary

During load testing with 5,000+ concurrent users, MongoDB CPU utilization becomes the primary bottleneck. Analysis of the quiz-backend code reveals several patterns that contribute to excessive database load:

1. **High-frequency individual updates** - Each answer submission, navigation, and ping results in separate DB operations
2. **Read-before-write pattern** - Most update operations first read the entire session document
3. **Large embedded documents** - Sessions contain embedded `session_answers` arrays and `events` arrays that grow over time
4. **Missing indexes** - Compound queries on `(quiz_id, user_id)` may not be optimally indexed
5. **Frequent dummy events** - 8-second ping intervals cause constant writes per user

### Impact Assessment

| Issue | Estimated DB Load Contribution |
|-------|-------------------------------|
| Individual answer updates | 30% |
| Dummy event pings | 25% |
| Read-before-write pattern | 20% |
| Session creation queries | 15% |
| Question fetching | 10% |

---

## Current Architecture Analysis

### Data Flow During Quiz Taking

```
User Action          | Frontend                    | Backend API              | MongoDB Operations
---------------------|-----------------------------|--------------------------|-----------------------
Page load            | GET /quiz/{id}              | quizzes.find_one()       | 1 read
                     | POST /sessions/             | sessions.find()          | 1 read (sorted, limit 2)
                     |                             | sessions.insert_one()    | 1 write
                     |                             | OR sessions.update_one() | 1 write (if reusing)
Start quiz           | PATCH /sessions/{id}        | sessions.find_one()      | 1 read
                     |                             | sessions.update_one()    | 1 write (push event)
Every 8 seconds      | PATCH /sessions/{id}        | sessions.find_one()      | 1 read
(dummy event)        |                             | sessions.update_one()    | 1 write (update timestamp)
Navigate to Q        | PATCH /session_answers/...  | sessions.find_one()      | 1 read
                     |                             | sessions.update_one()    | 1 write (set visited)
Answer question      | PATCH /session_answers/...  | sessions.find_one()      | 1 read
                     |                             | sessions.update_one()    | 1 write (set answer)
Fetch more Qs        | GET /questions/             | questions.aggregate()    | 1 aggregation
End quiz             | PATCH /sessions/{id}        | sessions.find_one()      | 1 read
                     |                             | sessions.update_one()    | 1 write (metrics, event)
```

### Operations Per User Per Quiz Session (30-minute timed test)

| Operation Type | Frequency | Count (30 min) | DB Operations |
|----------------|-----------|----------------|---------------|
| Dummy events | Every 8s | ~225 | 450 (read + write) |
| Answer submission | ~50 questions | ~50 | 100 (read + write) |
| Navigation | ~100 navigations | ~100 | 200 (read + write) |
| Page reload | ~2 | ~2 | 8 |
| Question fetch | ~5 buckets | ~5 | 5 |

**Total per user: ~763 DB operations for a 30-minute quiz**

**For 5,000 concurrent users: ~3.8 million operations in 30 minutes = ~2,100 ops/second**

---

## Identified Bottlenecks

### 1. Dummy Event Overhead (Critical)

**Location:** `app/routers/sessions.py:222-373`, Frontend ping every 8 seconds

**Problem:**
- Every active user sends a dummy event every 8 seconds
- Each dummy event triggers: `find_one()` + `update_one()` on sessions
- With 5,000 users: 625 reads + 625 writes = 1,250 ops/second just for pings

**Code Evidence:**
```python
# sessions.py:263-277
if (
    new_event == EventType.dummy_event
    and session["events"][-1]["event_type"] == EventType.dummy_event
):
    # Updates timestamp on existing dummy event
    last_event_update_query = {
        "events." + str(last_event_index) + ".updated_at": new_event_obj["created_at"]
    }
```

### 2. Read-Before-Write Pattern (High)

**Location:** `app/routers/session_answers.py:99`, `app/routers/sessions.py:242`

**Problem:**
- Every update operation first reads the entire session document
- Session documents can be large (50+ questions with answers + events array)
- This doubles the DB load for write operations

**Code Evidence:**
```python
# session_answers.py:99
session = client.quiz.sessions.find_one({"_id": session_id})
if session is None:
    # ... error handling

# Then update
result = client.quiz.sessions.update_one({"_id": session_id}, {"$set": setQuery})
```

### 3. Individual Answer Updates (High)

**Location:** `app/routers/session_answers.py:84-155`

**Problem:**
- Each answer submission is a separate API call and DB operation
- No batching capability currently used by frontend
- Each update touches the same session document repeatedly

### 4. Session Creation Query (Medium)

**Location:** `app/routers/sessions.py:87-96`

**Problem:**
- Uses sorted query with limit to find previous sessions
- Requires index scan on `(quiz_id, user_id)` sorted by `_id DESC`
- Called on every page load/refresh

**Code Evidence:**
```python
previous_two_sessions = list(
    client.quiz.sessions.find(
        {
            "quiz_id": current_session["quiz_id"],
            "user_id": current_session["user_id"],
        },
        sort=[("_id", pymongo.DESCENDING)],
        limit=2,
    )
)
```

### 5. Embedded Document Growth (Medium)

**Problem:**
- `events` array grows unbounded during a quiz session
- Each start/resume adds 2 events (actual event + dummy event)
- `session_answers` is fixed but embedded (N questions per session)

---

## Proposed Solutions

### Solution 1: Redis Caching Layer (High Impact)

**Description:** Add Redis as a caching layer for frequently accessed, read-heavy data.

**What to Cache:**
- Quiz data (immutable during quiz)
- Session state for active users
- Organization authentication results

**Impact:** Reduce MongoDB reads by 60-70%

**Complexity:** Medium

**Changes Required:**
- Add Redis client to backend
- Implement cache-aside pattern for quiz fetching
- Store active session state in Redis with TTL
- Sync critical updates back to MongoDB

### Solution 2: Reduce Dummy Event Frequency (High Impact, Low Effort)

**Description:** Increase dummy event interval from 8s to 30-60s.

**Impact:** Reduce dummy event DB operations by 75-87%

**Complexity:** Low

**Changes Required:**
- Frontend: Change `setInterval` from 8000ms to 30000-60000ms
- Backend: Adjust time calculation logic if needed

**Trade-off:** Slightly less precise time tracking, but 8s precision is unnecessary for most quizzes.

### Solution 3: Batch Answer Updates (High Impact)

**Description:** Accumulate answer changes on frontend and send in batches.

**Implementation Options:**

**Option A: Periodic Batching (Every 30 seconds)**
```
Frontend accumulates answers → Sends batch every 30s → Backend bulk update
```

**Option B: Navigation-triggered Batching**
```
Frontend accumulates changes → Sends on question navigation → Backend bulk update
```

**Impact:** Reduce answer update operations by 80-90%

**Complexity:** Medium

**Changes Required:**
- Frontend: Implement answer accumulation buffer
- Frontend: Modify answer submission to use batch endpoint
- Backend: Already has `update-multiple-answers` endpoint at `session_answers.py:14-81`

### Solution 4: Eliminate Read-Before-Write (Medium Impact)

**Description:** Use MongoDB's atomic update operators without pre-fetching.

**Changes Required:**

For `session_answers.py`:
```python
# Instead of:
session = client.quiz.sessions.find_one({"_id": session_id})
# validation...
result = client.quiz.sessions.update_one({"_id": session_id}, {"$set": setQuery})

# Do:
result = client.quiz.sessions.update_one(
    {"_id": session_id, f"session_answers.{position_index}": {"$exists": True}},
    {"$set": setQuery}
)
if result.matched_count == 0:
    raise HTTPException(404, "Session or position not found")
```

For `sessions.py` (dummy events only):
```python
# For dummy events, skip the find_one entirely
result = client.quiz.sessions.update_one(
    {"_id": session_id, "events": {"$exists": True}},
    {"$set": {f"events.{last_event_index}.updated_at": datetime.utcnow()}}
)
```

**Impact:** Reduce read operations by 50% for update-heavy flows

**Complexity:** Medium (requires careful validation logic changes)

### Solution 5: Add Compound Indexes (Medium Impact, Low Effort)

**Description:** Ensure optimal indexes exist for common query patterns.

**Recommended Indexes:**

```javascript
// Sessions collection
db.sessions.createIndex({ "quiz_id": 1, "user_id": 1, "_id": -1 })

// Questions collection (if not exists)
db.questions.createIndex({ "question_set_id": 1, "_id": 1 })
```

**Impact:** Reduce query execution time by 50-80% for index-covered queries

**Complexity:** Low

**Note:** Indexes have write overhead, but sessions are read-heavy enough to benefit.

### Solution 6: Session Event Compression (Low Impact)

**Description:** Instead of pushing events to an array, maintain only the last N events.

**Implementation:**
```python
# Use $slice to keep only last 10 events
session_update_query["$push"] = {
    "events": {
        "$each": [new_event_obj],
        "$slice": -10  # Keep only last 10 events
    }
}
```

**Impact:** Prevent unbounded document growth, faster updates

**Complexity:** Low

**Trade-off:** Lose historical event data (but metrics capture final state anyway)

### Solution 7: Read Replicas for Quiz/Questions (Low-Medium Impact)

**Description:** Use MongoDB read preference for read-heavy collections.

**Implementation:**
```python
# For quiz and questions reads
quiz = client.quiz.quizzes.find_one(
    {"_id": quiz_id},
    read_preference=ReadPreference.SECONDARY_PREFERRED
)
```

**Impact:** Distribute read load across replica set

**Complexity:** Low

**Prerequisite:** MongoDB Atlas M10+ tier with replica set (already in use)

### Solution 8: Separate Events Collection (Future Consideration)

**Description:** Move events to a separate time-series collection.

**Benefits:**
- Smaller session documents
- Better suited for append-only data
- MongoDB time-series collections are optimized for this pattern

**Impact:** Significantly smaller session documents, faster updates

**Complexity:** High (requires data migration, API changes)

---

## Implementation Priority Matrix

| Solution | Impact | Effort | Risk | Priority |
|----------|--------|--------|------|----------|
| S2: Reduce dummy frequency | High | Low | Low | **P0** |
| S5: Add compound indexes | Medium | Low | Low | **P0** |
| S4: Eliminate read-before-write (partial) | Medium | Medium | Medium | **P1** |
| S3: Batch answer updates | High | Medium | Medium | **P1** |
| S6: Event compression | Low | Low | Low | **P1** |
| S1: Redis caching | High | High | Medium | **P2** |
| S7: Read replicas | Medium | Low | Low | **P2** |
| S8: Separate events collection | High | High | High | **P3** |

### Recommended Implementation Order

**Phase 1: Quick Wins (1-2 days)**
1. Increase dummy event interval to 30s (frontend change)
2. Add compound index on sessions `(quiz_id, user_id, _id DESC)`
3. Add event array compression (`$slice: -10`)

**Phase 2: Backend Optimizations (3-5 days)**
1. Optimize dummy event handler to skip `find_one`
2. Add conditional validation to eliminate read-before-write where safe

**Phase 3: Frontend Integration (1 week)**
1. Implement answer batching on frontend
2. Use existing `update-multiple-answers` endpoint
3. Coordinate with dummy event to send batched updates

**Phase 4: Caching Layer (2 weeks)**
1. Add Redis infrastructure (ElastiCache or similar)
2. Cache quiz data with appropriate TTL
3. Consider session state caching for very high load scenarios

---

## Detailed Solution Specifications

### Spec S2: Reduce Dummy Event Frequency

**Frontend Change:**
```typescript
// Current: src/views/Player.vue
window.setInterval(() => {
  if (!state.hasQuizEnded && state.currentQuestionIndex != -1) {
    // Send dummy event
  }
}, 8000);  // Current: 8 seconds

// Proposed: Change to 30 seconds
window.setInterval(() => {
  // ...
}, 30000);  // New: 30 seconds
```

**Backend Consideration:**
- Adjust time_remaining calculation to handle 30s intervals
- Time precision of 30s is acceptable for quiz purposes

**Expected Reduction:**
- Current: 225 dummy events per 30-min quiz
- New: 60 dummy events per 30-min quiz
- **73% reduction in dummy event DB operations**

---

### Spec S5: Compound Index

**MongoDB Shell Command:**
```javascript
// Connect to quiz database
use quiz;

// Create compound index on sessions
db.sessions.createIndex(
  { "quiz_id": 1, "user_id": 1, "_id": -1 },
  { name: "quiz_user_session_lookup", background: true }
);

// Verify with explain
db.sessions.find(
  { quiz_id: "xxx", user_id: "yyy" }
).sort({ _id: -1 }).limit(2).explain("executionStats");
```

**Expected Improvement:**
- Session lookup queries will use index scan instead of collection scan
- Query time reduced from O(n) to O(log n)

---

### Spec S4: Optimized Dummy Event Handler

**Current Code (`sessions.py:263-277`):**
```python
session = client.quiz.sessions.find_one({"_id": session_id})
if session is None:
    raise HTTPException(...)

# ... complex logic ...

update_result = client.quiz.sessions.update_one(
    {"_id": session_id}, session_update_query
)
```

**Optimized Code:**
```python
@router.patch("/{session_id}", response_model=UpdateSessionResponse)
async def update_session(session_id: str, session_updates: UpdateSession):
    new_event = jsonable_encoder(session_updates)["event"]

    # Fast path for dummy events - no read required
    if new_event == EventType.dummy_event:
        result = client.quiz.sessions.update_one(
            {
                "_id": session_id,
                "events": {"$exists": True, "$ne": []},
                "events.-1.event_type": EventType.dummy_event
            },
            {
                "$set": {"events.$[last].updated_at": datetime.utcnow()}
            },
            array_filters=[{"last.event_type": EventType.dummy_event}]
        )

        if result.matched_count == 0:
            # Fallback to regular path if not a simple dummy update
            return await _handle_session_update_with_read(session_id, session_updates)

        return JSONResponse(status_code=status.HTTP_200_OK, content={"time_remaining": None})

    # Regular path for other events
    return await _handle_session_update_with_read(session_id, session_updates)
```

**Note:** This requires careful testing as it changes behavior for edge cases.

---

### Spec S3: Batch Answer Updates (Frontend)

**Frontend Implementation:**
```typescript
// src/services/API/Session.ts

class AnswerBatcher {
  private pendingUpdates: Map<number, UpdateSessionAnswer> = new Map();
  private sessionId: string;
  private flushTimer: number | null = null;

  constructor(sessionId: string) {
    this.sessionId = sessionId;
  }

  // Queue an answer update
  queueUpdate(positionIndex: number, update: UpdateSessionAnswer) {
    this.pendingUpdates.set(positionIndex, update);
    this.scheduleFlush();
  }

  // Schedule a flush after 2 seconds of inactivity
  private scheduleFlush() {
    if (this.flushTimer) clearTimeout(this.flushTimer);
    this.flushTimer = setTimeout(() => this.flush(), 2000);
  }

  // Immediately flush pending updates
  async flush() {
    if (this.pendingUpdates.size === 0) return;

    const updates = Array.from(this.pendingUpdates.entries());
    this.pendingUpdates.clear();

    // Use existing bulk update endpoint
    await SessionAPIService.updateAllSessionAnswers(
      this.sessionId,
      updates.map(([pos, answer]) => [pos, answer])
    );
  }

  // Force flush before quiz end or page unload
  async forceFlush() {
    if (this.flushTimer) clearTimeout(this.flushTimer);
    await this.flush();
  }
}
```

**Integration Points:**
1. Create batcher on session creation
2. Use `queueUpdate()` instead of direct API calls
3. Call `forceFlush()` before end-quiz event
4. Handle page unload with `beforeunload` event

---

## Estimated Impact Summary

| Current State | After Phase 1 | After All Phases |
|---------------|---------------|------------------|
| ~2,100 ops/sec for 5K users | ~1,200 ops/sec | ~400 ops/sec |
| MongoDB CPU: Saturated | MongoDB CPU: Moderate | MongoDB CPU: Low |

**Total expected reduction: 80% fewer database operations**

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Batching causes data loss on crash | Implement localStorage backup + beforeunload flush |
| Reduced dummy frequency affects time tracking | Accept 30s precision (sufficient for quiz use case) |
| Index creation impacts write performance | Create indexes during low-traffic period, use `background: true` |
| Read-before-write removal misses edge cases | Comprehensive testing, gradual rollout |

---

## Appendix: Load Test Configuration for Validation

After implementing changes, validate with the following Locust configuration:

```python
# quiz-http-api/locustfile.py adjustments

# Update wait_time to match new dummy event frequency
wait_time = between(25, 35)  # Match ~30s interval

# Adjust task weights for batching behavior
@task(1)  # Reduce individual answer task weight
def answer_question(self):
    # Batch simulation
    pass

@task(5)  # Add batch submission task
def submit_answer_batch(self):
    # Submit accumulated answers
    pass
```

Run load test targeting:
- 5,000 concurrent users
- 30-minute duration
- Monitor MongoDB metrics:
  - CPU utilization
  - Operations/second
  - Query execution time
  - Connection count

---

*This document should be reviewed with the team before implementation. Consider running load tests before and after each phase to measure actual impact.*
