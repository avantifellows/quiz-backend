# Local Redis Caching Plan

**Date:** 2026-04-10
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
│  │  ~200-460MB peak │   │  128MB limit   │   │
│  │  (measured)      │   │                │   │
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

### ECS Memory Budget — Confirmed

Measured via CloudWatch Container Insights (30-day window ending 2026-04-11):

| Environment | Peak | P99 | P95 | Avg | Min |
|-------------|------|-----|-----|-----|-----|
| **Testing** | 458 MB | 458 MB | 457 MB | 353 MB | 183 MB |
| **Production** | 209 MB | 207 MB | 206 MB | 197 MB | 183 MB |

**Task memory: 2048 MB. Backend peak: 458 MB. Redis hard limit: 128 MB.**

Even at the testing peak, total usage would be ~586 MB — leaving **~1460 MB free** (71% headroom). No task memory increase needed. The current 2048 MB allocation comfortably fits both containers.

---

## What to Cache (and What NOT to)

### Every Read Operation, Classified

#### Quizzes — CACHE (immutable after creation)

No update quiz endpoint exists. The only mutation is `update_quiz_for_backwards_compatibility` — a one-time migration on first read. Before deploying the cache, run a one-time migration script (see "Pre-deployment migration" below) that backfills all legacy quizzes in MongoDB so the runtime fixup becomes a no-op. Every cached quiz read must use the same shared loader; the fixup stays in the loader as a safety net but should never trigger post-migration.

| File | Endpoint / Function | What it reads | Cache? | Key | TTL |
|------|---------------------|---------------|--------|-----|-----|
| `quizzes.py` | `GET /quiz/{id}` handler | Quiz doc | **YES** | `quiz:{id}` | 1h |
| `forms.py` | `GET /form/{id}` handler | Quiz doc (form type) | **YES** | `quiz:{id}` | 1h |
| `sessions.py` | `POST /sessions` handler | Quiz for session setup | **YES** | `quiz:{id}` | 1h |
| `sessions.py` | `PATCH /sessions/{id}` end-quiz handler | Quiz for scoring | **YES** | `quiz:{id}` | 1h |
| `sessions.py` | `GET /sessions/{id}` handler | Quiz for lazy metrics | **YES** | `quiz:{id}` | 1h |
| `sessions.py` | `GET /sessions/{id}/reveal` handler | Quiz for reveal | **YES** | `quiz:{id}` | 1h |

**Impact:** During a 10K user test, the same quiz is read ~30K+ times (session creation + end-quiz + GET session). With caching, warm containers should converge to mostly cache hits, but cold starts can still produce more than one MongoDB read per container until the first cache write completes.

#### Questions — CACHE (immutable after creation)

No update question endpoint exists.

| File | Endpoint / Function | What it reads | Cache? | Key | TTL |
|------|---------------------|---------------|--------|-----|-----|
| `questions.py` | `GET /questions/{id}` handler | Single question | **YES** | `question:{id}` | 1h |
| `sessions.py` | `GET /sessions/{id}/reveal` handler | Single question | **YES** | `question:{id}` | 1h |
| `quizzes.py` | `GET /quiz/{id}` single_page branch | All questions for qset | **YES** | `questions:qset:{qset_id}` | 1h |
| `forms.py` | `GET /form/{id}` single_page branch | All questions for qset | **YES** | `questions:qset:{qset_id}` | 1h |
| `quizzes.py` | `GET /quiz/{id}` OMR branch | Options count aggregation | **YES** | `omr_options:{sha256(sorted_qset_ids_joined_by_: )}` | 1h |
| `forms.py` | `GET /form/{id}` OMR branch | Options count aggregation | **YES** | `omr_options:{sha256(sorted_qset_ids_joined_by_: )}` | 1h |

| `questions.py` | `GET /questions/` paginated handler | Paginated question list | **YES** | `questions:qset:{qset_id}:skip:{normalized_skip}:limit:{normalized_limit_or_all}` | 1h |

> **Implementer note:** The current `GET /questions/` endpoint's 404 branch (checking `to_list()` result against `None`) is unreachable dead code — `to_list()` always returns a list (possibly empty `[]`), never `None`. The cache implementation should match actual runtime behavior (always returns `[]` or a populated list). Do not replicate the unreachable 404 path.

Not cached (write path):
| `quizzes.py` | `POST /quiz` handler (fetch-back after insert) | Fetch-back after insert | **NO** | — | — |

The POST path fetches back just-inserted questions — caching makes no sense.

#### Organizations — CACHE (rarely changes)

| File | Endpoint / Function | What it reads | Cache? | Key | TTL |
|------|---------------------|---------------|--------|-----|-----|
| `organizations.py` | `GET /organizations/authenticate/{key}` handler | Org by API key | **YES** | `cache:{namespace}:org:key:{api_key}` | 5min |

Not cached (write path):
| `organizations.py` | `POST /organizations` handler (create + fetch-back) | Create + fetch-back | **NO** | — | — |

Auth is called on every page load. Short TTL (5 min) since API keys could theoretically be revoked.

#### Sessions — DO NOT CACHE

| File | Endpoint / Function | Why not |
|------|---------------------|---------|
| `sessions.py` | `GET /sessions/preflight` handler | Session state changes every 20s (dummy events) |
| `sessions.py` | `POST /sessions` handler | Needs latest session state for continuation logic |
| `sessions.py` | `PATCH /sessions/{id}` handler | Updates session — must read fresh |
| `sessions.py` | `GET /sessions/{id}` handler | Session data changes frequently |
| `sessions.py` | `GET /user/{id}/quiz-attempts` handler | Aggregation across all user sessions |
| `sessions.py` | `GET /sessions/{id}/reveal` handler | Reads session for answer validation |
| `session_answers.py` | `PATCH /session_answers/...` handlers | Updates answers — must validate fresh |
| `session_answers.py` | `GET /session_answers/...` handler | Reads specific answer |

Sessions are the hottest data in the system and change on every answer update and every 20-second dummy event. Caching would cause stale reads.

### Route-Behavior Compatibility Rules

- Preserve current `omr_mode=true` semantics exactly on both `/quiz/{id}` and `/form/{id}`. Today that query parameter forces OMR shaping even when the stored metadata is not `QuizType.omr`, and the cache refactor must not change that behavior.
- Keep cached values canonical. Request parameters such as `omr_mode`, `single_page_mode`, `include_answers`, and reveal-specific formatting must continue to shape the response only after the cache read.
- Preserve current `/form/{id}` visibility behavior exactly. `/form` responses currently return `correct_answer` and `solution` data by default, so quiz-specific answer-hiding helpers must not be applied to form responses unless the current form route already does that.
- Preserve the current `/questions` behavior where `skip=None` and `skip=0` are equivalent, `limit=None` and `limit=0` are equivalent, and an empty list response (`200` with `[]`) is a valid result.
- `/organizations/authenticate/{api_key}` uses the raw API key in cache keys and logs. This is acceptable for this project. API key logging in `POST /organizations` and `GET /authenticate` is pre-existing and out of scope for the caching work.
- Invalid org-auth responses should no longer echo the submitted API key. Preserve the `404` status, but return a generic detail such as `organization not found`. *(This is a bundled non-cache security improvement, accepted for simplicity. Call it out in the PR description.)*
- If OMR rendering needs an option-count entry for a `question_set_id` and the keyed aggregation result does not contain it, treat that as a server-side data error: log the missing `question_set_id`, return `500`, and do not cache or reuse a broken OMR result.

---

## Cache Contract

Redis stores canonical database documents or explicitly defined intermediate query results only. It does not store route-specific response payloads.

What this means in practice:

- `cache:{namespace}:quiz:{id}` stores the canonical quiz document after backwards-compatibility fixup, before request-specific shaping.
- `cache:{namespace}:question:{id}` stores the canonical question document before `include_answers` sanitization.
- `cache:{namespace}:questions:qset:{id}` stores the full sorted question list for single-page quiz/form reads.
- `cache:{namespace}:questions:qset:{id}:skip:{normalized_skip}:limit:{normalized_limit_or_all}` stores normalized paginated question lists; cached empty arrays are valid hits, not misses.
- `cache:{namespace}:omr_options:{sha256(sorted_qset_ids_joined_by_: )}` stores intermediate query results as a map keyed by `question_set_id`, never as a positional array.
- `cache:{namespace}:org:key:{api_key}` stores the organization document for auth lookups.
- Sessions and session answers remain out of scope.

All request-dependent transforms must happen after cache read, against a request-local object:

- `include_answers`
- `display_solution`
- single-page formatting
- reveal formatting
- OMR shaping / option padding

The route contract must stay behavior-compatible with the current API:

- `omr_mode=true` still forces OMR shaping from request inputs, even when quiz/form metadata is not OMR.
- `/form/{id}` keeps its current answer/solution visibility semantics and must not inherit quiz answer-hiding behavior from shared loaders.
- `/questions` cache lookups must use canonicalized pagination inputs and must treat cached `[]` as a successful hit.
- Single-page quiz/form reads must use the full-list qset key (`questions:qset:{id}`), while `/questions?qset_id=...` must use the normalized paginated key.
- OMR option-count lookups must fail closed: if a required `question_set_id` key is absent from the keyed result map, log it, return `500`, and skip caching that broken result.
- Shared cache loaders may return `None` for not-found data, but they must not replace route-specific `404` details or validation branches with one generic cache-layer `HTTPException`.

This prevents one route from caching a mutated payload that breaks another route using the same source document.

---

## Invalidation Strategy

**The good news: almost no invalidation needed.**

| Data | Mutation Pattern | Invalidation Rule |
|------|-----------------|-------------------|
| Quizzes | Created once, never updated | TTL only (1 hour). No explicit invalidation. |
| Questions | Created once, never updated | TTL only (1 hour). No explicit invalidation. |
| Organizations | Created once, never updated | TTL only (5 minutes). No explicit invalidation. |
| Sessions | Updated constantly | Not cached. |

There are no update/delete endpoints for quizzes, questions, or organizations in the API. The data is effectively immutable once created for normal API traffic, so TTL-based eviction is sufficient there.

**Maintenance scripts:** direct MongoDB rewrite scripts are outside that API immutability guarantee. This plan standardizes on versioned cache keys for those operations. Every cache key must include `cache:{namespace}:...`, where `CACHE_NAMESPACE` is an app env var managed by Terraform. After any script that modifies quizzes, questions, or organizations, operators must bump `CACHE_NAMESPACE` before resuming traffic that depends on cached reads. Do not rely on per-task flushes across ECS tasks.

**Orphaned keys after namespace bump:** After a namespace bump (e.g., `v1` → `v2`), orphaned keys under the old prefix remain in Redis until TTL expiry or LRU eviction. No manual flush is needed — the 64MB `allkeys-lru` policy handles cleanup automatically. Operators should expect a brief coexistence period (up to 1 hour, the longest TTL) where both old and new keys are present, but orphaned keys receive zero reads and will be the first evicted under memory pressure.

**Edge case:** `update_quiz_for_backwards_compatibility` mutates a quiz on first read. Currently only `GET /quiz/{id}` calls this fixup — `/form` and session routes never trigger it. The shared cached loader would change that behavior by running the fixup for all routes, which would introduce database writes on paths that currently have none.

**Resolution (Option C — pre-deployment migration):** Write a one-time migration script (similar to the existing scripts in `app/scripts/`) that runs `update_quiz_for_backwards_compatibility` on every quiz document in production MongoDB. Deploy and run this script before the caching code goes live. After migration, all quizzes will already have `max_questions_allowed_to_attempt`, `title`, and `marking_scheme` fields on their question sets, so the runtime fixup becomes a no-op.

The fixup function stays in the shared loader as a safety net for any quizzes created between migration and deployment, but it should never trigger in normal operation. Move the fixup into a neutral module outside routers (for example `app/services/quiz_fixups.py`) so the shared loader does not import router code. If the fixup write-back is not acknowledged, preserve current behavior: return `500` and do not cache the quiz.

**Confirmation — session routes are behavior-neutral under the shared loader:** Switching `sessions.py` quiz reads (`POST /sessions`, `PATCH /sessions` scoring, `GET /sessions` lazy metrics, `GET /sessions` reveal) to the shared cached loader is behavior-neutral because: (a) post-migration, the backwards-compatibility fixup is always a no-op, and (b) the fields the fixup adds (`max_questions_allowed_to_attempt`, `title`, `marking_scheme`) are either unused by session creation logic or produce identical values to the existing fallback code in `compute_session_metrics`. No session endpoint behavior changes as a result of this switch.

### Pre-deployment migration script: `app/scripts/backfill_quiz_backwards_compat.py`

This script must:

1. Connect to the target MongoDB (using `MONGO_AUTH_CREDENTIALS` env var).
2. Iterate all quiz documents in the `quizzes` collection.
3. For each quiz, run the same logic as `update_quiz_for_backwards_compatibility`: add `max_questions_allowed_to_attempt`, `title`, and `marking_scheme` to any question set missing them.
4. Write the updated quiz back with `update_one`.
5. Log progress (count of updated vs already-compatible quizzes).
6. Be idempotent — safe to run multiple times.

Run this script against production before deploying the cache-aware application code. Verify completion by spot-checking a sample of previously-unfixed quizzes.

---

## Cache Key Design

```
cache:{namespace}:quiz:{quiz_id}                              → canonical quiz document after fixup (JSON)
cache:{namespace}:question:{question_id}                      → canonical question document (JSON)
cache:{namespace}:questions:qset:{question_set_id}            → all questions for a set, sorted (JSON array)
cache:{namespace}:omr_options:{sha256(sorted_qset_ids_joined_by_: )}   → OMR options count result (JSON object keyed by question_set_id)
cache:{namespace}:questions:qset:{qset_id}:skip:{normalized_skip}:limit:{normalized_limit_or_all}  → paginated questions for a set (JSON array)
cache:{namespace}:org:key:{api_key}     → organization document (JSON)
```

Normalization rules:

- For `/questions`, normalize falsey `skip` to `0`.
- For `/questions`, normalize falsey `limit` to the literal token `all`.
- Cache hits must be determined by Redis value presence (`data is not None`), not Python truthiness, so `[]` remains a valid hit.
- For OMR aggregation, route code must read option counts by `question_set_id`; it must not depend on list position.
- Prefix every key with `cache:{namespace}:`, where `namespace` comes from `CACHE_NAMESPACE`.
- OMR cache keys use SHA-256 over sorted qset IDs to keep keys short. Org-auth keys use the raw API key directly — this is acceptable because Redis runs as a localhost-only sidecar inside each ECS task and is not network-accessible from outside the container.

---

## Implementation

### New file: `quiz-backend/app/cache.py`

```python
import json
import time
import redis.asyncio as redis
from fastapi.encoders import jsonable_encoder
from logger_config import get_logger
from settings import get_cache_settings

logger = get_logger()

redis_client = None
_last_error_log_ts = 0.0
_last_connect_attempt_ts = 0.0


def _cache_settings():
    return get_cache_settings()


async def init_cache():
    await _ensure_cache_client(force=True)


async def _close_old_client(old_client):
    """Close an old Redis client, suppressing errors to avoid masking the caller's context."""
    if old_client is not None:
        try:
            await old_client.aclose()
        except Exception:
            pass


async def _ensure_cache_client(force: bool = False):
    global redis_client, _last_connect_attempt_ts
    settings = _cache_settings()
    if not settings.cache_enabled:
        old_client = redis_client
        redis_client = None
        await _close_old_client(old_client)
        return None
    if redis_client is not None and not force:
        return redis_client

    now = time.time()
    if not force and now - _last_connect_attempt_ts < 5:
        return None
    _last_connect_attempt_ts = now

    old_client = redis_client
    try:
        candidate = redis.Redis.from_url(
            settings.redis_url,
            max_connections=settings.redis_max_connections,
            decode_responses=True,
        )
        await candidate.ping()
        redis_client = candidate
        await _close_old_client(old_client)
        return redis_client
    except Exception as e:
        redis_client = None
        await _close_old_client(old_client)
        if _should_log_cache_error():
            logger.warning(
                f"event=cache op=connect result=error family=system detail=redis_unavailable error={type(e).__name__}"
            )
        return None


async def close_cache():
    if redis_client is not None:
        await redis_client.aclose()


def _should_log_cache_error() -> bool:
    global _last_error_log_ts
    now = time.time()
    if now - _last_error_log_ts > 60:
        _last_error_log_ts = now
        return True
    return False


def cache_key(family: str, *parts: str) -> str:
    """Build a namespaced cache key, e.g. cache:v1:quiz:abc123."""
    settings = _cache_settings()
    return f"cache:{settings.cache_namespace}:{family}:{':'.join(parts)}"


def cache_family(key: str) -> str:
    """Extract the family segment from a full cache key for log grouping.
    e.g. 'cache:v1:quiz:abc123' → 'quiz'."""
    parts = key.split(":")
    return parts[2] if len(parts) > 2 else "unknown"


def cache_key_ref(key: str) -> str:
    """Return a short reference for a cache key, suitable for log output."""
    return key


async def cache_get(key: str):
    """Return cached JSON data, or None on miss / disabled cache / Redis failure."""
    client = await _ensure_cache_client()
    if client is None:
        return None
    try:
        data = await client.get(key)
        if data is not None:
            return json.loads(data)
    except Exception as e:
        global redis_client
        old_client = redis_client
        redis_client = None
        await _close_old_client(old_client)
        if _should_log_cache_error():
            logger.warning(
                f"event=cache op=get result=error family={cache_family(key)} key_ref={cache_key_ref(key)} error={type(e).__name__}"
            )
    return None


async def cache_set(key: str, value, ttl_seconds: int = 3600):
    """Write JSON-safe canonical data into Redis. Never raise to request handlers."""
    client = await _ensure_cache_client()
    if client is None:
        return
    try:
        payload = json.dumps(jsonable_encoder(value))
        await client.setex(key, ttl_seconds, payload)
    except Exception as e:
        global redis_client
        old_client = redis_client
        redis_client = None
        await _close_old_client(old_client)
        if _should_log_cache_error():
            logger.warning(
                f"event=cache op=set result=error family={cache_family(key)} key_ref={cache_key_ref(key)} error={type(e).__name__}"
            )
```

**Key design decisions:**

- Cache operations never raise exceptions into request handlers. If Redis is down, the app falls back to direct MongoDB reads and preserves correctness.
- App startup is not the only chance to connect to Redis. Startup init is best-effort, and later cache operations lazily retry connection establishment with rate-limited logging.
- Cache writes use `jsonable_encoder()` first so ObjectIds, datetimes, and Pydantic-backed payloads follow the app's existing serialization rules.
- Cache settings are loaded lazily inside functions/startup via `get_cache_settings()`, matching the existing repo rule for env-backed settings.
- Cache errors are logged in a rate-limited way to avoid warning floods when Redis is unavailable.
- Cache logs and metrics use raw org API keys in cache keys and log output. This is acceptable for this project — Redis is localhost-only and not network-accessible.
- The implementation should track cache hit/miss/error signals via in-memory counters (per family), logged periodically as a summary line (e.g., every 60 seconds): `event=cache_stats family=quiz hits=142 misses=3 errors=0`. Do not log on every individual cache hit or miss — under load (10K user test), per-event logging would produce tens of thousands of lines. Error logging stays per-event but rate-limited via `_should_log_cache_error()`.
- Make `setup_logger()` idempotent before relying on cache log counts operationally; duplicated handlers would otherwise distort hit/miss/error telemetry.

### Shared loader pattern

Use shared cached loaders instead of route-local `find_one()` calls for canonical data:

```python
async def get_cached_quiz(quiz_id: str) -> dict | None:
    if (quiz := await cache_get(cache_key("quiz", quiz_id))) is not None:
        return quiz

    db = get_quiz_db()
    quiz = await db.quizzes.find_one({"_id": quiz_id})
    if quiz is None:
        return None

    await apply_quiz_backwards_compatibility_fixup(quiz_id, quiz)
    await cache_set(cache_key("quiz", quiz_id), quiz, ttl_seconds=3600)
    return quiz
```

Every cached quiz read in `quizzes.py`, `forms.py`, and `sessions.py` should use this shared loader so all routes see the same fixed canonical quiz. The shared cache module must not import router code; the legacy fixup belongs in a neutral helper/service module.
If the fixup database write is not acknowledged, the loader should preserve current behavior by raising `500` and skipping the cache write.
Routes must still apply `omr_mode`, `single_page_mode`, `include_answers`, and reveal-specific shaping after the cache read, preserving current request semantics exactly.
The shared loader owns database reads, cache-aside behavior, and fixups; each route still owns its current not-found message, quiz-vs-form validation, and other route-specific HTTP semantics.

### Usage pattern in routers

```python
from copy import deepcopy
from cache import get_cached_quiz

# Example: route-specific shaping happens after cache read
async def get_quiz_response(quiz_id, include_answers: bool):
    quiz = await get_cached_quiz(quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail=f"quiz with id {quiz_id} not found")
    quiz = deepcopy(quiz)  # defensive: currently json.loads() returns fresh dicts, but protects against future in-memory L1 cache layers
    if not include_answers:
        _hide_answers_in_quiz_in_place(quiz)
    return quiz
```

### Concrete OMR pipeline changes

The current OMR aggregation pipeline in both `quizzes.py` and `forms.py` drops `_id` (which is the `question_set_id`) in its final `$project` stage, making results position-dependent. Four changes must be made together in both files:

**1. Pipeline change — keep `_id` in the final projection:**

```python
# BEFORE (current — drops _id, results are positional):
{"$project": {"_id": 0, "options_count_per_set": 1}}

# AFTER (keep _id so results are keyed by question_set_id):
{"$project": {"_id": 1, "options_count_per_set": 1}}
```

**2. Result transformation — convert list to dict keyed by `question_set_id`:**

```python
# BEFORE:
options_count_across_sets = await cursor.to_list(length=None)

# AFTER:
raw_options_list = await cursor.to_list(length=None)
options_count_across_sets = {
    item["_id"]: item["options_count_per_set"] for item in raw_options_list
}
```

**3. Consumption code — access by `question_set_id` key, not position index:**

```python
# BEFORE (positional — fragile if MongoDB returns results in different order):
options_count_per_set = options_count_across_sets[question_set_index]["options_count_per_set"]

# AFTER (keyed — order-independent):
question_set_id = question_set["_id"]
if question_set_id not in options_count_across_sets:
    logger.error(f"OMR option count missing for question_set_id={question_set_id}")
    raise HTTPException(status_code=500, detail="OMR data integrity error")
options_count_per_set = options_count_across_sets[question_set_id]
```

**4. Error handling — fail closed on missing keys:**

If a required `question_set_id` is absent from the dict, this is a server-side data error. Log the missing `question_set_id`, return `500`, and do not cache or reuse the broken OMR result. This error path does not exist in the current code (positional access would raise `IndexError` instead, which is caught as a generic 500).

These four changes apply identically to both `get_quiz` in `quizzes.py` and `get_form` in `forms.py`.

**Implementation note — eliminate OMR duplication:** The OMR aggregation pipeline and consumption code in `quizzes.py` (lines ~239-278) and `forms.py` (lines ~83-122) are near-identical (only log message strings differ). Before applying the four changes above, extract the shared OMR pipeline + consumption logic into a common helper (e.g., in `cache.py` or a new `app/services/omr.py`), called by both `quizzes.py` and `forms.py`. This eliminates the divergence risk entirely — the four changes are then made once in the helper, not duplicated across two files. If extraction is deferred, both files must be changed atomically in the same commit, with a test asserting both routes produce identical OMR output for the same quiz input.

### Dependency note: Async driver

The app uses `pymongo 4.16.0` with native `AsyncMongoClient` — fully async. The `redis.asyncio` client integrates directly with the existing async/await patterns. No migration needed.

### Settings and lifecycle changes

- Add cache config to `app/settings.py` via a dedicated settings model:
  - `CACHE_ENABLED` (default `false` for local dev and CI unless Redis is explicitly provisioned)
  - `REDIS_URL` (default `redis://localhost:6379/0`)
  - `REDIS_MAX_CONNECTIONS` (small bounded pool, e.g. `10`)
  - `CACHE_NAMESPACE` (default `v1`; bump this during maintenance-script invalidation or incompatible cache-shape changes)
- Follow the existing `get_mongo_settings()` pattern: add `CacheSettings` plus `get_cache_settings()`, and only call it inside functions/startup, never at module import time.
- Redis is an optional performance dependency. Redis initialization must be best-effort, must never fail app startup, and must degrade to cache-off behavior if Redis is unavailable; MongoDB remains the only startup-gating dependency.
- Initialize the Redis client during app startup only in that best-effort mode, allow lazy reconnect during later cache operations, and close it during app shutdown alongside MongoDB cleanup in `app/main.py`.
- Document these env vars in `docs/ENV.md` and add local Redis startup instructions to `README.md`.
- Local development stays cache-off by default. To test caching locally, run a pinned Redis image and export cache env vars explicitly, for example:

```bash
docker run --rm -p 6379:6379 redis:7.2.5-alpine
export CACHE_ENABLED=true
export REDIS_URL=redis://localhost:6379/0
export REDIS_MAX_CONNECTIONS=10
export CACHE_NAMESPACE=v1
```

- Keep `/health` as an app health endpoint only; treat Redis as an optional performance dependency, with availability surfaced through cache metrics/logs rather than ALB health failure.
- `REDIS_MAX_CONNECTIONS` is per Uvicorn worker process. With the current `uvicorn --workers 4` container model, `10` per process means up to `40` Redis connections per ECS task. That effective per-task budget should remain the reference number in rollout and capacity checks. The `redis_client` module-level global in `cache.py` is naturally per-worker after Uvicorn's fork, matching the existing `database.py` pattern — lifespan `init_cache()`/`close_cache()` runs once per worker process.
- `.env.example` should include safe local defaults for the cache settings so it matches the README and `docs/ENV.md`:
  - `CACHE_ENABLED="false"`
  - `REDIS_URL="redis://localhost:6379/0"`
  - `REDIS_MAX_CONNECTIONS="10"`
  - `CACHE_NAMESPACE="v1"`

---

## Infrastructure Changes

### Terraform: Add Redis sidecar to task definition

**Files:** `terraform/testing/ecs.tf`, `terraform/prod/ecs.tf`

Add a second container to the task definition's `container_definitions`:

```json
{
  "name": "redis",
  "image": "redis:7.2.5-alpine",
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
      "awslogs-group": "${aws_cloudwatch_log_group.quiz_backend.name}",
      "awslogs-region": "${var.aws_region}",
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
- Reuse the existing Terraform-managed ECS log group by default, with a separate `redis` stream prefix. Only add a second log group if operations explicitly want isolated retention/filtering.
- Do not add an app-container dependency on Redis reaching `HEALTHY`. Redis remains an optional performance dependency, so app startup must continue even when the Redis container is slow, unhealthy, or absent; correctness still depends only on MongoDB plus lazy reconnect in application code.
- Add cache env vars to the app container in both `terraform/testing/ecs.tf` and `terraform/prod/ecs.tf`:
  - `CACHE_ENABLED=false` for the first rollout
  - `REDIS_URL=redis://localhost:6379/0`
  - `REDIS_MAX_CONNECTIONS=10`
  - `CACHE_NAMESPACE=v1`
- Treat cache env vars as Terraform-owned only. Do not toggle cache settings by editing the live ECS task definition or console-managed env vars, because the deploy workflow reuses the active task definition revision.
- The deploy workflows only swap the app image into the current ECS task definition revision, so Terraform must land the sidecar and app env wiring first. Code deployment cannot be the step that introduces the new task-definition shape.
- Add a pre-deploy workflow guard in both ECS deploy workflows that fails unless the active task definition already contains the Redis sidecar plus `CACHE_ENABLED`, `REDIS_URL`, `REDIS_MAX_CONNECTIONS`, and `CACHE_NAMESPACE`.

**Memory budget:** Current task memory is `2048` MB, and the measured production/testing peaks above already show sufficient headroom for the Redis sidecar. Rollout can proceed without raising task memory. Re-check memory under cache-enabled testing load as a confirmation step, and only raise `var.task_memory` if new measurements contradict the current evidence.

### Required rollout sequence for the first Redis-ready task definition

Because `main` and `release` auto-deploy after CI and the deploy workflows reuse the active ECS task definition revision, the first rollout must happen in this exact order per environment:

1. Apply Terraform first to add the Redis sidecar and all cache env vars with `CACHE_ENABLED=false`.
2. Verify the active ECS task definition revision now contains the Redis sidecar plus `CACHE_ENABLED`, `REDIS_URL`, `REDIS_MAX_CONNECTIONS`, and `CACHE_NAMESPACE`.
3. Only after step 2 is complete, merge or enable the deploy-workflow guard that checks for that task-definition shape.
4. Deploy the cache-aware application code while `CACHE_ENABLED=false`.
5. Enable caching later through Terraform-managed env changes only.

The workflow guard must not be introduced before step 2 is complete in the target environment, or the next normal auto-deploy can fail before infrastructure is ready.

### Post-deploy validation checklist

Required validation is different for the infra-only rollout and the later cache-enabled rollout:

- Infra-only rollout (`CACHE_ENABLED=false`):
  - Verify the active ECS task definition contains the Redis sidecar and all required cache env vars.
  - Verify running tasks show both containers and the Redis container reports healthy.
  - Verify application requests still succeed with caching disabled.
- Cache-enabled rollout:
  - Call at least one cacheable read endpoint twice against the deployed environment.
  - Confirm cache telemetry or logs show at least one miss followed by one hit, or equivalent read/write activity for that cache family.
  - Verify application correctness still matches uncached behavior while Redis remains outside `/health`.

### Python dependencies

**File:** `quiz-backend/app/requirements.txt`

```diff
+ redis==5.2.1
```

> The `redis` package includes `redis.asyncio` since v4.2.0. No separate `aioredis` needed.
> Pin the ECS sidecar image to `redis:7.2.5-alpine` (or a digest-pinned equivalent) rather than a floating major tag.

---

## Files to Modify

| File | Change |
|------|--------|
| `app/cache.py` | **NEW** — Redis client, shared cached loaders, lazy settings reads, lazy reconnect, versioned cache-key helpers, degraded-mode logging, and cache metrics/log events |
| `app/requirements.txt` | Add `redis==5.2.1` |
| `app/settings.py` | Add `CacheSettings`, `get_cache_settings()`, `CACHE_ENABLED`, `REDIS_URL`, `REDIS_MAX_CONNECTIONS`, `CACHE_NAMESPACE`, and related helpers |
| `app/services/quiz_fixups.py` | **NEW** — move backwards-compatibility quiz fixup out of router code so shared loaders depend on a neutral module |
| `app/scripts/backfill_quiz_backwards_compat.py` | **NEW** — one-time migration script to backfill all legacy quizzes with `max_questions_allowed_to_attempt`, `title`, and `marking_scheme`. Run against production before deploying cache-aware code. |
| `app/main.py` | Initialize and close the Redis client in lifespan hooks |
| `app/logger_config.py` | Make logger setup idempotent before using cache log counts or log-derived metrics operationally. Add an early-return guard: `logger = logging.getLogger("quizenginelogger"); if logger.handlers: return logger` at the top of `setup_logger()` to prevent duplicate handlers from distorting cache telemetry. |
| `app/routers/quizzes.py` | Replace direct quiz reads with shared cached quiz loader. Keep response shaping after cache read, preserve current `omr_mode=true` semantics, and read OMR option counts by `question_set_id` key rather than position. |
| `app/routers/forms.py` | Replace direct quiz reads with shared cached quiz loader. Keep single-page and OMR shaping after cache read, preserve current `omr_mode=true` semantics, preserve current answer/solution visibility behavior, and read OMR option counts by `question_set_id` key rather than position. **forms.py must NOT apply `_hide_answers_in_quiz_in_place` or `_clear_solutions_in_place` to the cached quiz data.** The `include_answers` parameter and answer-hiding helpers are quiz-specific. Forms always return answers and solutions — this is the current behavior and must be preserved. |
| `app/routers/sessions.py` | Replace cached quiz/question reads with shared loaders while keeping session reads uncached. |
| `app/routers/questions.py` | Cache canonical question docs and normalized qset query results, treat cached empty lists as hits, then apply `include_answers` shaping after cache read. |
| `app/routers/organizations.py` | Wrap the `find_one` in the `GET /organizations/authenticate/{key}` handler with cache (org auth). |
| `docs/ENV.md` | Document cache env vars, local/test defaults, and local Redis startup steps |
| `README.md` | Add local Redis instructions for cache-enabled development/testing |
| `.env.example` | Add cache env vars with safe local defaults and keep caching disabled by default |
| `app/tests/...` | Add cache-enabled integration coverage, Redis reset fixtures, and env setup before `create_app()` |
| `.github/workflows/ci.yml` | Keep the default suite cache-off and add a Redis-backed cache integration job |
| `.github/workflows/deploy_ecs_testing.yml` | Add a pre-deploy task-definition verification step for the Redis sidecar and cache env vars |
| `.github/workflows/deploy_ecs_prod.yml` | Add a pre-deploy task-definition verification step for the Redis sidecar and cache env vars |
| `terraform/testing/ecs.tf` | Add Redis sidecar container definition plus app-container cache env vars |
| `terraform/prod/ecs.tf` | Add Redis sidecar container definition plus app-container cache env vars |

---

## Expected Impact

| Metric | Before | After |
|--------|--------|-------|
| Quiz reads from MongoDB (10K user test) | ~30,000+ per container | After warm-up, mostly cache hits. Cold starts can still cause `1+` Mongo reads per container for a hot quiz key because the plan uses plain cache-aside without single-flight locking. |
| Question reads from MongoDB | Proportional to quiz views | After warm-up, mostly cache hits per unique question / qset key per container. |
| Org auth reads from MongoDB | Every page load | At most one refresh per TTL window per API-key lookup per container, plus occasional concurrent cold misses. |
| MongoDB read load during end-quiz spike | 10K quiz reads + 10K session reads | Session reads remain unchanged. Quiz reads should drop sharply after warm-up but will not be perfectly single-read on cold cache. |
| Cache hit latency | N/A | ~0.1ms (localhost Redis) |
| Failure mode if Redis dies | N/A | Correctness preserved via fallback to MongoDB, with degraded performance surfaced through cache hit/miss/error metrics and degraded-mode logs |

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Redis crash takes down the app | `essential: false` — ECS keeps the app running. Cache helpers swallow exceptions. |
| Route-specific payload shaping pollutes shared cache entries | Cache canonical docs / intermediate query results only. Apply `include_answers`, `display_solution`, single-page, reveal, and OMR shaping after cache read. |
| Legacy quiz fixup behaves differently across routes | Route all cached quiz reads through one shared loader that runs backwards-compatibility fixup on cache miss before writing to Redis. |
| Stale cache serves wrong data | API writes are immutable, but maintenance scripts can rewrite cached collections directly. Require a `CACHE_NAMESPACE` bump after such scripts run; do not rely on the 1-hour TTL or per-task flushes for maintenance operations. |
| Redis memory pressure | `maxmemory 64mb` + `allkeys-lru` eviction. Quiz docs are ~50-100KB each; 64MB holds ~600+ quizzes. |
| Container cold start (no cache) | Expect concurrent cold misses. Accept this initially, measure during load test, and add stampede protection only if warm-up amplification is material. |
| Redis-down logs become noisy | Add `CACHE_ENABLED`, rate-limited degraded-mode logging, cache hit/miss/error metrics or structured log counters. |
| OMR option counts get attached to the wrong question set or silently disappear | Cache OMR aggregation results as a map keyed by `question_set_id`, update route code to read by key instead of list position, and fail with `500` if a required keyed row is missing. |
| Serialization mismatch | Serialize cache payloads with `jsonable_encoder()` before `json.dumps()`. Keep sessions and session answers out of cache scope. |
| Redis sidecar exits mid-task | If the Redis sidecar exits within a running task, it does not restart — Fargate has no per-container restart policy. That task runs uncached until replaced by a new deployment or scaling event. Cache hit-rate drops for that task will be visible in the periodic `cache_stats` log. Monitor Redis container exit status to trigger task replacement if prolonged cache-less operation is undesirable. |
| Tests miss cache-enabled regressions | Run normal tests with `CACHE_ENABLED=false`, and add a dedicated Redis-backed integration path with cache reset between tests. |

---

## Testing Strategy

Use a real Redis test service for cache-enabled integration coverage. Mocking is acceptable for narrow unit tests, but the primary cache verification path should exercise actual Redis semantics.

Required coverage:

- Cache miss then cache hit for `GET /quiz/{id}`, `GET /form/{id}`, `GET /questions/{id}`, and reveal routes.
- Cross-route sequencing where one route warms a canonical cache entry and another route reads the same cached data with a different response shape.
- Behavior-compatibility assertions that `omr_mode=true` still forces OMR shaping for quiz/form routes even when stored metadata is not `QuizType.omr`.
- Dedicated `/form/{id}` compatibility tests for normal, `single_page_mode=true`, and `omr_mode=true` reads, proving cached and uncached responses preserve the current answer/solution visibility behavior.
- Shape-sensitive assertions for:
  - `/questions/{id}?include_answers=true`
  - `/quiz/{id}` with and without answer/solution hiding
  - form single-page mode
  - reveal formatting
  - OMR shaping / option padding
- `/questions` key normalization tests proving `skip=None` and `skip=0` share the same cache key, `limit=None` and `limit=0` share the same cache key, and cached `[]` is treated as a hit.
- OMR cache-shape tests proving cached option counts are stored/read as a map by `question_set_id`, not a positional list.
- OMR missing-row tests proving a missing keyed `question_set_id` produces a controlled `500`, logs the missing key, and does not cache a broken result.
- Legacy quiz first-read behavior through a non-`/quiz` path, proving the shared cached quiz loader performs backwards-compatibility fixup consistently.
- `CACHE_ENABLED=false` behavior and Redis-failure behavior, proving correctness falls back to MongoDB while error logging remains rate-limited.
- Org-auth tests proving cache hit/miss behavior works correctly for API key lookups.

Test harness rules:

- Keep the existing default suite runnable without Redis by setting `CACHE_ENABLED=false`.
- Add a dedicated cache-enabled base fixture/class that sets `CACHE_ENABLED=true`, `REDIS_URL=redis://localhost:6379/0`, `REDIS_MAX_CONNECTIONS=10`, and `CACHE_NAMESPACE=test` before importing `create_app()` or constructing `TestClient`. Concrete example using the existing test base class pattern:

```python
class CacheEnabledBaseTestCase(BaseTestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["CACHE_ENABLED"] = "true"
        os.environ["REDIS_URL"] = "redis://localhost:6379/0"
        os.environ["CACHE_NAMESPACE"] = "test"
        super().setUpClass()  # triggers create_app() with cache env vars already set
```
- Add cache-test seed helpers that insert quizzes/questions/organizations without calling cached read routes. Keep helpers like `post_and_get_quiz()` for non-cache tests if still useful, but do not use them in cache hit/miss assertions.
- Add cache reset between tests (`FLUSHDB`, key prefix isolation, or equivalent fixture teardown).
- Flush Redis before and after each cache-enabled test case so cached empties, org-auth entries, and shared quiz loaders do not leak across tests.
- Add a separate cache-enabled integration target in CI and local test tooling that provisions Redis explicitly.

CI requirements:

- Keep the current Mongo-backed `pytest` pass as the default cache-off job with `CACHE_ENABLED=false`.
- Add a second CI job (or explicit second test target) that provisions Redis `7.2.5-alpine`, sets:
  - `MONGO_AUTH_CREDENTIALS=mongodb://localhost:27017`
  - `MONGO_DB_NAME=quiz_test`
  - `CACHE_ENABLED=true`
  - `REDIS_URL=redis://localhost:6379/0`
  - `REDIS_MAX_CONNECTIONS=10`
  - `CACHE_NAMESPACE=ci`
- Run the Redis-backed cache integration tests in that second job so cache-on behavior is verified without making the entire suite depend on Redis.

---

## Execution Order

1. Add `CacheSettings` / `get_cache_settings()`, cache env documentation, and local Redis instructions (`CACHE_ENABLED`, `REDIS_URL`, `REDIS_MAX_CONNECTIONS`, `CACHE_NAMESPACE`).
2. Write and run the `backfill_quiz_backwards_compat.py` migration script against both testing and production MongoDB to backfill all legacy quizzes. Verify completion before proceeding.
3. Create `cache.py` with lifecycle hooks, lazy settings reads, versioned key helpers, lazy reconnect, shared loaders, `jsonable_encoder()` writes, and degraded-mode observability.
4. Refactor cached quiz reads to use the shared loader, then add question / qset / OMR / org caching while preserving current route semantics exactly, especially `omr_mode=true`, route-owned `404` behavior, and the org-auth contract.
5. Normalize `/questions` pagination keys, treat cached empty arrays as hits, and store OMR aggregation results as a map keyed by `question_set_id`.
6. Add cache-off tests plus Redis-backed cache integration tests, update CI with a dedicated Redis-enabled job, and ensure all cache env vars are set before `create_app()`.
7. Update Terraform for both environments to add the Redis sidecar and app-container cache env vars, with `CACHE_ENABLED=false` on the first infrastructure rollout. Do not add a startup dependency that requires Redis to be `HEALTHY` before the app can start.
8. Apply Terraform first in the target environment and verify the active ECS task definition revision now contains both the Redis sidecar and the full cache env wiring.
9. Only after step 8 succeeds, add or enable the deploy-workflow guard that checks for the Redis-ready task definition shape.
10. Deploy the application code against that Redis-ready task definition while caching remains disabled, then run the infra-only post-deploy validation checklist.
11. When enabling caching, do it through Terraform-managed env changes only; verify the effective per-task Redis connection budget (`4 workers x REDIS_MAX_CONNECTIONS=10 = 40`), then run the cache-enabled post-deploy validation checklist and confirm miss/hit telemetry.
12. After any maintenance script that rewrites quizzes/questions/organizations, bump `CACHE_NAMESPACE` before resuming traffic that depends on cached reads.
13. Measure ECS memory headroom and cache hit/miss/error signals under representative load in testing as a confirmation step, then repeat the same Terraform-first sequence for production.
