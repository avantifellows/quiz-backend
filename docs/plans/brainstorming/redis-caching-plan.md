# Local Redis Caching Plan

**Date:** 2026-04-01
**Goal:** Add a local Redis sidecar to each ECS container and cache immutable/slow-changing data to eliminate redundant MongoDB reads under load.

---

## Architecture

```
ECS Task (1 vCPU, 2GB RAM)
┌─────────────────────────────────────────────┐
│                                             │
│  ┌─────────────────┐   ┌────────────────┐   │
│  │  quiz-backend    │   │  Redis 7       │   │
│  │  (Python/FastAPI)│──▶│  (sidecar)     │   │
│  │  4 Uvicorn       │   │  localhost:6379│   │
│  │  workers         │   │  64MB memory   │   │
│  │  ~1920MB         │   │  ~128MB limit  │   │
│  └─────────────────┘   └────────────────┘   │
│                                             │
└─────────────────────────────────────────────┘
```

**Why local (not shared) Redis:**
- Zero network latency — localhost only (~0.1ms vs 1-5ms to ElastiCache)
- No shared infrastructure to manage or pay for
- Cache failure is isolated to one container
- Acceptable tradeoff: each container warms its own cache independently. During a 10K user test on 10 containers, the same quiz gets cached 10 times (once per container). That's fine — even a large quiz doc is ~180KB, so 10 copies = ~1.8MB total across the fleet.

### Actual Production Document Sizes

Measured from `quiz-prod-m10` (14,128 quizzes, 790,003 questions):

| Document | Min | Typical | Max | Notes |
|----------|-----|---------|-----|-------|
| Quiz | ~2 KB | ~45 KB | ~186 KB | Size scales with question count. A 51-question quiz is ~90-180KB. |
| Question | ~350 B | ~500 B | ~15 KB | Most are 400-1500 bytes. Large ones have images or many options. |
| Organization | ~200 B | ~200 B | ~200 B | Tiny documents. |

**64MB Redis capacity:**
- ~350 large quizzes (186KB each) — but typically only 1-5 are active during a test
- ~130,000 typical questions (500B each) — more than enough for any single test
- In practice, a 10K user test against a single quiz uses <1MB of cache

---

## What to Cache (and What NOT to)

### Every Read Operation, Classified

#### Quizzes — CACHE (immutable after creation)

No update quiz endpoint exists. The only mutation is `update_quiz_for_backwards_compatibility` — a one-time migration on first read. Cache AFTER this fixup runs.

| File | Line | Endpoint | What it reads | Cache? | Key | TTL |
|------|------|----------|---------------|--------|-----|-----|
| `quizzes.py` | 172 | GET /quiz/{id} | Quiz doc | **YES** | `quiz:{id}` | 1h |
| `forms.py` | 26 | GET /form/{id} | Quiz doc (form type) | **YES** | `quiz:{id}` | 1h |
| `sessions.py` | 139 | POST /sessions | Quiz for session setup | **YES** | `quiz:{id}` | 1h |
| `sessions.py` | 486 | PATCH /sessions/{id} (end-quiz) | Quiz for scoring | **YES** | `quiz:{id}` | 1h |
| `sessions.py` | 533 | GET /sessions/{id} | Quiz for lazy metrics | **YES** | `quiz:{id}` | 1h |
| `sessions.py` | 603 | GET /sessions/{id}/reveal | Quiz for reveal | **YES** | `quiz:{id}` | 1h |

**Impact:** During a 10K user test, the same quiz is read ~30K+ times (session creation + end-quiz + GET session). With caching: 1 DB read + ~30K cache hits per container.

#### Questions — CACHE (immutable after creation)

No update question endpoint exists.

| File | Line | Endpoint | What it reads | Cache? | Key | TTL |
|------|------|----------|---------------|--------|-----|-----|
| `questions.py` | 21 | GET /questions/{id} | Single question | **YES** | `question:{id}` | 1h |
| `sessions.py` | 637 | GET /sessions/{id}/reveal | Single question | **YES** | `question:{id}` | 1h |
| `quizzes.py` | 201 | GET /quiz/{id} (single_page) | All questions for qset | **YES** | `questions:qset:{qset_id}` | 1h |
| `forms.py` | 54 | GET /form/{id} (single_page) | All questions for qset | **YES** | `questions:qset:{qset_id}` | 1h |
| `quizzes.py` | 236 | GET /quiz/{id} (OMR) | Options count aggregation | **YES** | `omr_options:{qset_ids_hash}` | 1h |
| `forms.py` | 84 | GET /form/{id} (OMR) | Options count aggregation | **YES** | `omr_options:{qset_ids_hash}` | 1h |

Not cached (write path):
| `quizzes.py` | 116,124 | POST /quiz | Fetch-back after insert | **NO** | — | — |
| `questions.py` | 55 | GET /questions/?qset_id=... | Paginated question list | **NO** | — | — |

The POST path fetches back just-inserted questions — caching makes no sense. The paginated GET is a low-traffic API endpoint, not in the hot path.

#### Organizations — CACHE (rarely changes)

| File | Line | Endpoint | What it reads | Cache? | Key | TTL |
|------|------|----------|---------------|--------|-----|-----|
| `organizations.py` | 63 | GET /organizations/authenticate/{key} | Org by API key | **YES** | `org:key:{api_key}` | 5min |

Not cached (write path):
| `organizations.py` | 32,43 | POST /organizations | Create + fetch-back | **NO** | — | — |

Auth is called on every page load. Short TTL (5 min) since API keys could theoretically be revoked.

#### Sessions — DO NOT CACHE

| File | Line | Endpoint | Why not |
|------|------|----------|---------|
| `sessions.py` | 111 | GET /sessions/preflight | Session state changes every 20s (dummy events) |
| `sessions.py` | 153 | POST /sessions | Needs latest session state for continuation logic |
| `sessions.py` | 337 | PATCH /sessions/{id} | Updates session — must read fresh |
| `sessions.py` | 530 | GET /sessions/{id} | Session data changes frequently |
| `sessions.py` | 563 | GET /user/{id}/quiz-attempts | Aggregation across all user sessions |
| `sessions.py` | 595 | GET /sessions/{id}/reveal | Reads session for answer validation |
| `session_answers.py` | 29,102 | PATCH /session_answers/... | Updates answers — must validate fresh |
| `session_answers.py` | 182 | GET /session_answers/... | Reads specific answer |

Sessions are the hottest data in the system and change on every answer update and every 20-second dummy event. Caching would cause stale reads.

---

## Invalidation Strategy

**The good news: almost no invalidation needed.**

| Data | Mutation Pattern | Invalidation Rule |
|------|-----------------|-------------------|
| Quizzes | Created once, never updated | TTL only (1 hour). No explicit invalidation. |
| Questions | Created once, never updated | TTL only (1 hour). No explicit invalidation. |
| Organizations | Created once, never updated | TTL only (5 minutes). No explicit invalidation. |
| Sessions | Updated constantly | Not cached. |

There are no update/delete endpoints for quizzes, questions, or organizations in the API. The data is effectively immutable once created. TTL-based eviction is sufficient.

**Edge case:** `update_quiz_for_backwards_compatibility` mutates a quiz on first read. Solution: cache the quiz AFTER this function runs, so the cached version includes the fix.

---

## Cache Key Design

```
quiz:{quiz_id}                              → full quiz document (JSON)
question:{question_id}                      → single question document (JSON)
questions:qset:{question_set_id}            → all questions for a set, sorted (JSON array)
omr_options:{sorted_qset_ids_joined_by_:}   → OMR options count result (JSON array)
org:key:{api_key}                           → organization document (JSON)
```

---

## Implementation

### New file: `quiz-backend/app/cache.py`

```python
import os
import json
import redis.asyncio as redis
from logger_config import get_logger

logger = get_logger()

# Connect to local Redis sidecar (localhost:6379)
# Falls back gracefully if Redis is unavailable
_redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
_pool = redis.ConnectionPool.from_url(_redis_url, max_connections=10)
redis_client = redis.Redis(connection_pool=_pool)


async def cache_get(key: str):
    """Get from cache. Returns None on miss or Redis failure."""
    try:
        data = await redis_client.get(key)
        if data is not None:
            return json.loads(data)
    except Exception as e:
        logger.warning(f"Cache read failed for {key}: {e}")
    return None


async def cache_set(key: str, value, ttl_seconds: int = 3600):
    """Set in cache. Silently fails if Redis is unavailable."""
    try:
        await redis_client.setex(key, ttl_seconds, json.dumps(value))
    except Exception as e:
        logger.warning(f"Cache write failed for {key}: {e}")
```

**Key design decision:** Cache operations never raise exceptions. If Redis is down, the app falls back to direct MongoDB reads — same as today. This makes the cache purely additive with zero risk.

### Usage pattern in routers

```python
from cache import cache_get, cache_set

# Example: quiz read with caching
async def get_quiz(quiz_id):
    # Try cache first
    quiz = await cache_get(f"quiz:{quiz_id}")
    if quiz is not None:
        return quiz

    # Cache miss — read from MongoDB
    quiz = await client.quiz.quizzes.find_one({"_id": quiz_id})
    if quiz is None:
        raise HTTPException(404)

    # Cache for next time
    await cache_set(f"quiz:{quiz_id}", quiz, ttl_seconds=3600)
    return quiz
```

### Dependency note: Motor migration

This plan assumes the Motor (async) migration is done first. The cache client uses `redis.asyncio` which requires async/await. If Motor isn't done yet, two options:
1. Use sync `redis` client instead (adds another blocking call — less ideal)
2. Do Motor migration first, then add caching

**Recommended: Motor first, then caching.**

---

## Infrastructure Changes

### Terraform: Add Redis sidecar to task definition

**Files:** `terraform/testing/ecs.tf`, `terraform/prod/ecs.tf`

Add a second container to the task definition's `container_definitions`:

```json
{
  "name": "redis",
  "image": "redis:7-alpine",
  "essential": false,
  "portMappings": [
    {
      "containerPort": 6379,
      "protocol": "tcp"
    }
  ],
  "memory": 128,
  "memoryReservation": 64,
  "command": ["redis-server", "--maxmemory", "64mb", "--maxmemory-policy", "allkeys-lru"],
  "healthCheck": {
    "command": ["CMD", "redis-cli", "ping"],
    "interval": 30,
    "timeout": 5,
    "retries": 3,
    "startPeriod": 10
  },
  "logConfiguration": {
    "logDriver": "awslogs",
    "options": {
      "awslogs-group": "/ecs/quiz-backend-redis",
      "awslogs-region": "ap-south-1",
      "awslogs-stream-prefix": "redis"
    }
  }
}
```

**Key settings:**
- `essential: false` — if Redis crashes, the app keeps running (falls back to direct DB reads)
- `maxmemory 64mb` — bounded memory usage
- `maxmemory-policy allkeys-lru` — evicts least recently used keys when full
- `memory: 128` hard limit, `memoryReservation: 64` soft limit

**Memory budget:** Current task has 2048MB. App uses ~1920MB (4 Uvicorn workers). Redis gets 128MB hard limit. Total: 2048MB — fits within existing allocation.

### Python dependencies

**File:** `quiz-backend/app/requirements.txt`

```diff
+ redis>=5.0.0
```

> The `redis` package includes `redis.asyncio` since v4.2.0. No separate `aioredis` needed.

---

## Files to Modify

| File | Change |
|------|--------|
| `app/cache.py` | **NEW** — Redis client + get/set helpers |
| `app/requirements.txt` | Add `redis>=5.0.0` |
| `app/routers/quizzes.py` | Wrap `find_one` at line 172 with cache (quiz). Wrap aggregations at lines 201, 236 with cache (questions, OMR options). |
| `app/routers/forms.py` | Wrap `find_one` at line 26 with cache (quiz). Wrap at lines 54, 84 with cache (questions, OMR options). |
| `app/routers/sessions.py` | Wrap `find_one` for quiz reads at lines 139, 486, 533, 603 with cache. Wrap question read at line 637 with cache. |
| `app/routers/questions.py` | Wrap `find_one` at line 21 with cache (question). |
| `app/routers/organizations.py` | Wrap `find_one` at line 63 with cache (org auth). |
| `terraform/testing/ecs.tf` | Add Redis sidecar container definition |
| `terraform/prod/ecs.tf` | Add Redis sidecar container definition |

---

## Expected Impact

| Metric | Before | After |
|--------|--------|-------|
| Quiz reads from MongoDB (10K user test) | ~30,000+ per container | ~1 per container (rest from cache) |
| Question reads from MongoDB | Proportional to quiz views | ~1 per unique question per container |
| Org auth reads from MongoDB | Every page load | ~1 per 5 minutes per API key per container |
| MongoDB read load during end-quiz spike | 10K quiz reads + 10K session reads | 10K session reads only (quiz cached) |
| Cache hit latency | N/A | ~0.1ms (localhost Redis) |
| Failure mode if Redis dies | N/A | Transparent fallback to MongoDB (no user impact) |

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Redis crash takes down the app | `essential: false` — ECS keeps the app running. Cache helpers swallow exceptions. |
| Stale cache serves wrong data | Data is immutable (no update endpoints). 1-hour TTL limits staleness window for any edge case. |
| Redis memory pressure | `maxmemory 64mb` + `allkeys-lru` eviction. Quiz docs are ~50-100KB each; 64MB holds ~600+ quizzes. |
| Container cold start (no cache) | First request per quiz/question hits MongoDB, then cache is warm. Under load testing, warmup happens in the first few seconds. |
| Serialization overhead | JSON encode/decode adds ~0.5ms. Still 10-50x faster than a MongoDB read over the network. |
| Tests need Redis | Cache helpers return None on connection failure → tests work without Redis (cache is just always "miss"). Alternatively, mock `cache.redis_client` in test setup. |

---

## Execution Order

1. Motor migration (prerequisite — async Redis client needs async app)
2. Add `redis` to requirements.txt
3. Create `cache.py` module
4. Add caching to router files (one at a time, test after each)
5. Update Terraform with Redis sidecar
6. Deploy to testing, run load test
7. Deploy to production
