# PyMongo → Motor Migration Plan

**Date:** 2026-04-01
**Goal:** Replace synchronous PyMongo with async Motor driver so FastAPI can handle concurrent DB calls instead of blocking one worker per operation.
**Impact:** Estimated 5-10x improvement in per-container throughput.

---

## Why This Matters

FastAPI is async, but PyMongo is synchronous. Every `find_one()` or `update_one()` blocks the entire worker thread — nothing else can happen until the DB responds. With 4 workers per container, max concurrency is 4 DB operations at a time.

Motor is the official async MongoDB driver (built on top of PyMongo). It lets FastAPI handle hundreds of concurrent DB calls by yielding control while waiting for responses.

---

## Scope

**38 DB calls across 6 router files** need `await` added.
**1 file** (`database.py`) needs the client swapped.
**1 file** (`requirements.txt`) needs Motor added.
**1 non-async helper** (`quizzes.py:update_quiz_for_backwards_compatibility`) needs to become async.
**Test infrastructure** needs `mongomock-motor` for async-compatible mocking.
**1 migration script** (`scripts/add_marking_scheme_to_questions_without_details.py`) — no changes, stays sync.

---

## Step 1: Update Dependencies

**File:** `quiz-backend/app/requirements.txt`

```diff
- pymongo==4.0.2
+ pymongo>=4.0.2
+ motor>=3.1.0
+ mongomock-motor>=0.0.20
```

> `motor` depends on `pymongo` internally — we keep `pymongo` but relax the pin.
> `mongomock-motor` provides an async mock client for tests.

---

## Step 2: Switch Client in `database.py`

**File:** `quiz-backend/app/database.py`

```python
# BEFORE
from pymongo import MongoClient
client = MongoClient(
    os.getenv("MONGO_AUTH_CREDENTIALS"),
    maxPoolSize=20,
    minPoolSize=5,
    ...
)

# AFTER
from motor.motor_asyncio import AsyncIOMotorClient
client = AsyncIOMotorClient(
    os.getenv("MONGO_AUTH_CREDENTIALS"),
    maxPoolSize=20,
    minPoolSize=5,
    ...
)
```

All connection pool settings (`maxPoolSize`, `minPoolSize`, `maxIdleTimeMS`, etc.) carry over unchanged — Motor uses the same parameters as PyMongo.

---

## Step 3: Update Router Files

The changes are mechanical — add `await` to every DB call and convert cursor materialization.

### Patterns to apply everywhere:

| PyMongo (sync) | Motor (async) |
|---|---|
| `client.quiz.X.find_one(...)` | `await client.quiz.X.find_one(...)` |
| `client.quiz.X.update_one(...)` | `await client.quiz.X.update_one(...)` |
| `client.quiz.X.insert_one(...)` | `await client.quiz.X.insert_one(...)` |
| `client.quiz.X.insert_many(...)` | `await client.quiz.X.insert_many(...)` |
| `list(client.quiz.X.find(...))` | `await client.quiz.X.find(...).to_list(length=None)` |
| `list(client.quiz.X.find(...).sort(...))` | `await client.quiz.X.find(...).sort(...).to_list(length=None)` |
| `list(client.quiz.X.aggregate(...))` | `await client.quiz.X.aggregate(...).to_list(length=None)` |

> **Walrus operator** `if (x := find_one(...)) is not None` works fine with await: `if (x := await find_one(...)) is not None`

### File-by-file changes:

#### `routers/session_answers.py` — 5 calls

| Line | Current | Change |
|------|---------|--------|
| 29 | `client.quiz.sessions.find_one(...)` | Add `await` |
| 72 | `client.quiz.sessions.update_one(...)` | Add `await` |
| 102 | `client.quiz.sessions.find_one(...)` | Add `await` |
| 146 | `client.quiz.sessions.update_one(...)` | Add `await` |
| 182 | `list(client.quiz.sessions.aggregate(...))` | `await ...aggregate(...).to_list(length=None)` |

#### `routers/sessions.py` — 16 calls

| Line | Current | Change |
|------|---------|--------|
| 111 | `client.quiz.sessions.find_one(...)` | Add `await` |
| 139 | `client.quiz.quizzes.find_one(...)` | Add `await` |
| 153 | `list(client.quiz.sessions.find(...))` | `await ...find(...).to_list(length=None)` |
| 222 | `client.quiz.sessions.update_one(...)` | Add `await` |
| 238 | `client.quiz.sessions.update_one(...)` | Add `await` |
| 302 | `client.quiz.sessions.insert_one(...)` | Add `await` |
| 337 | `client.quiz.sessions.find_one(...)` | Add `await` |
| 486 | `client.quiz.quizzes.find_one(...)` | Add `await` |
| 511 | `client.quiz.sessions.update_one(...)` | Add `await` |
| 530 | `client.quiz.sessions.find_one(...)` | Add `await` |
| 533 | `client.quiz.quizzes.find_one(...)` | Add `await` |
| 537 | `client.quiz.sessions.update_one(...)` | Add `await` |
| 563 | `client.quiz.sessions.aggregate(...)` | `await ...aggregate(...).to_list(length=None)` |
| 595 | `client.quiz.sessions.find_one(...)` | Add `await` |
| 603 | `client.quiz.quizzes.find_one(...)` | Add `await` |
| 637 | `client.quiz.questions.find_one(...)` | Add `await` |

#### `routers/quizzes.py` — 8 calls

| Line | Current | Change |
|------|---------|--------|
| 70 | `quiz_collection.update_one(...)` inside non-async `update_quiz_for_backwards_compatibility` | Make function `async`, add `await`, update call site to `await` |
| 103 | `client.quiz.questions.insert_many(...)` | Add `await` |
| 116 | `client.quiz.questions.aggregate(...)` | `await ...aggregate(...).to_list(length=None)` |
| 124 | `client.quiz.questions.aggregate(...)` | `await ...aggregate(...).to_list(length=None)` |
| 145 | `client.quiz.quizzes.insert_one(...)` | Add `await` |
| 172 | `quiz_collection.find_one(...)` (walrus) | Add `await` inside walrus |
| 201-205 | `list(client.quiz.questions.find(...).sort(...))` | `await ...find(...).sort(...).to_list(length=None)` |
| 235-257 | `list(client.quiz.questions.aggregate(...))` | `await ...aggregate(...).to_list(length=None)` |

**Special case:** `update_quiz_for_backwards_compatibility` (line 33) is a non-async helper that calls `update_one`. It must become `async def` and its call site (line 192) must use `await`.

#### `routers/organizations.py` — 4 calls

| Line | Current | Change |
|------|---------|--------|
| 32 | `client.quiz.organization.find_one(...)` | Add `await` |
| 34 | `client.quiz.organization.insert_one(...)` | Add `await` |
| 43 | `client.quiz.organization.find_one(...)` | Add `await` |
| 63 | `client.quiz.organization.find_one(...)` (walrus) | Add `await` inside walrus |

#### `routers/questions.py` — 2 calls

| Line | Current | Change |
|------|---------|--------|
| 21 | `client.quiz.questions.find_one(...)` (walrus) | Add `await` inside walrus |
| 55 | `list(client.quiz.questions.aggregate(...))` | `await ...aggregate(...).to_list(length=None)` |

#### `routers/forms.py` — 3 calls

| Line | Current | Change |
|------|---------|--------|
| 26 | `quiz_collection.find_one(...)` (walrus) | Add `await` inside walrus |
| 53-57 | `list(client.quiz.questions.find(...).sort(...))` | `await ...find(...).sort(...).to_list(length=None)` |
| 83-105 | `list(client.quiz.questions.aggregate(...))` | `await ...aggregate(...).to_list(length=None)` |

---

## Step 4: Update `import pymongo` Usage

`sessions.py` imports `pymongo` directly for `pymongo.DESCENDING`. This stays valid — Motor is built on PyMongo, and sort constants come from the `pymongo` package.

```python
import pymongo  # ← keep this, DESCENDING constant still comes from here
```

---

## Step 5: Update Tests

**Current setup:** Tests use `mongoengine` with `mongomock://` URI, which patches PyMongo's `MongoClient` to use an in-memory mock.

**Problem:** Motor's `AsyncIOMotorClient` is not patched by mongomock.

**Solution:** Use `mongomock-motor` package which provides `AsyncMongoMockClient`.

**File:** `quiz-backend/app/tests/base.py`

```python
# BEFORE
from mongoengine import connect, disconnect

class BaseTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        connect("mongoenginetest", host="mongomock://127.0.0.1:8000")
        cls.client = TestClient(app)

# AFTER
from unittest.mock import patch
from mongomock_motor import AsyncMongoMockClient

class BaseTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mock_client = AsyncMongoMockClient()
        cls.patcher = patch("database.client", cls.mock_client)
        cls.patcher.start()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()
```

> `FastAPI.TestClient` runs async endpoints synchronously via `anyio` — this works with `mongomock-motor` out of the box.

**Test files that directly use `client.quiz.*`** (for test setup/assertions):
- `tests/test_quizzes.py` — lines 247, 254, 337, 339, 345 (5 calls)
- `tests/test_sessions.py` — lines 105, 137, 171, 704 (4 calls)

These are sync test functions calling the DB directly for setup — they need to use the mock client but don't need `await` since `mongomock-motor` supports sync access on its mock collections for test convenience. Verify this works; if not, switch these to use API calls instead of direct DB manipulation.

---

## Step 6: No Changes Needed

**Migration script** (`scripts/add_marking_scheme_to_questions_without_details.py`):
- Standalone script, not a web endpoint
- Can import its own sync `MongoClient` independently
- No changes required

**Dockerfile** — no changes. Motor is a pure Python package, no native dependencies.

**Terraform / deployment** — no changes.

---

## Execution Order

1. **Add `motor` and `mongomock-motor` to `requirements.txt`**
2. **Update `database.py`** — swap client
3. **Update `tests/base.py`** — swap test mock
4. **Update router files** — one at a time, run tests after each:
   - `organizations.py` (4 calls, simplest file — good to validate pattern)
   - `questions.py` (2 calls)
   - `forms.py` (3 calls)
   - `session_answers.py` (5 calls)
   - `quizzes.py` (8 calls, includes async helper conversion)
   - `sessions.py` (16 calls, largest and most complex)
5. **Run full test suite** after each file
6. **Deploy to staging, run load test** to verify improvement

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| `mongomock-motor` doesn't support all aggregation operators | Run tests early (step 4). If specific operators fail, mock those tests individually |
| Missed `await` causes `coroutine was never awaited` error | These are runtime errors that show up immediately in tests — easy to catch |
| Motor cursor behavior differs from PyMongo | All cursor usages are converted to `.to_list()` — no lazy iteration patterns in the codebase |
| Script in `scripts/` breaks | Script is independent, keeps its own sync client — no impact |
| Tests that directly mutate DB via `client.quiz.*` break | Verify `mongomock-motor` supports sync access in tests; fallback to API-based setup if needed |

---

## Rollback Plan

If issues arise in production:
1. Revert `database.py` to `MongoClient` (one line change)
2. Revert `requirements.txt`
3. Remove `await` from all DB calls (mechanical, but touches many files)

Since Motor is a drop-in replacement with the same query syntax, the rollback is straightforward. The only difference is `await` and `.to_list()`.
