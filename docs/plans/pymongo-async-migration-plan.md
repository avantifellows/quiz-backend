# PyMongo Async Migration Plan

**Date:** 2026-04-01
**Goal:** Replace synchronous PyMongo with PyMongo Async (`pymongo.AsyncMongoClient`) in the FastAPI runtime so MongoDB calls stop blocking the event loop.
**Expected outcome:** Lower request blocking and better concurrency under load. The exact throughput gain is a staging-validation target, not a guaranteed 5-10x outcome, because this codebase still has read-before-write patterns and CPU-heavy scoring paths.

---

## Why This Matters

FastAPI is async, but the current MongoDB access path is synchronous. Every `find_one()` or `update_one()` blocks the worker while the database responds. PyMongo Async keeps the same MongoDB model but exposes awaitable operations so the app can yield control while I/O is in flight.

That said, PyMongo Async only removes the blocking I/O portion of the request path. It does not by itself remove extra reads, aggregation cost, or CPU-bound scoring work already identified elsewhere in the repo. This migration should therefore be treated as a meaningful concurrency improvement whose real impact must be measured after rollout.

---

## Prerequisite

This plan assumes `python-3.12-upgrade-plan.md` (PR 1) has been completed and merged. Specifically, the following must already be done:

- All Lambda/SAM/Mangum traces removed
- Python upgraded to 3.12
- Pydantic v2 migration complete
- All dependencies at exact tested Python 3.12-compatible pins (including a PyMongo version that supports `AsyncMongoClient`)
- Full test suite passing on the new stack

---

## Scope

### In scope

- **Runtime Mongo access**
  - `app/database.py`
  - 38 runtime DB call sites across 6 router files:
    - `app/routers/session_answers.py`
    - `app/routers/sessions.py`
    - `app/routers/quizzes.py`
    - `app/routers/organizations.py`
    - `app/routers/questions.py`
    - `app/routers/forms.py`

- **Shared-client consumers outside routers**
  - `app/scripts/backfill_time_limits_and_spent.py`
  - This is the only non-router file under `app/` that still imports `database.client`, so it must be handled before the shared client is switched to PyMongo Async.

- **Test harness and affected tests**
  - `app/tests/base.py`
  - All `BaseTestCase` consumers:
    - `app/tests/test_quizzes.py`
    - `app/tests/test_questions.py`
    - `app/tests/test_organization.py`
  - All `SessionsBaseTestCase` consumers:
    - `app/tests/test_sessions.py`
    - `app/tests/test_session_answers.py`
  - This includes direct DB setup/assertion calls, the shared `TestClient` bootstrap path, and the PyMongo-specific `Collection` spy test in `test_session_answers.py`.

- **Dependencies and docs**
  - `app/requirements.txt`
  - `README.md`
  - This migration plan document plus any test setup, deployment/runtime, and rollout-validation notes affected by the final design

- **Validation / rollout**
  - ECS/FastAPI service path (testing + production)

### Out of scope for this migration

- Standalone maintenance scripts that already create their own local sync `MongoClient`
- Broader performance work outside the Mongo driver swap
- Reorganizing the repo into separate runtime/test dependency files unless explicitly chosen as follow-up work

### Explicit no-change item

- `app/scripts/add_marking_scheme_to_questions_without_details.py`
  - Remains synchronous and independent because it does not use the shared app client.

---

## Phase 1: Normalize the Database Access Seam

This phase is required before the client swap.

### Current problem

- Routers currently do `from database import client`, which binds the client object at import time.
- `app/tests/base.py` imports `main`, and `main.py` imports routers immediately.
- Rebinding `database.client` later in `BaseTestCase.setUpClass()` would not update already-imported router globals.
- The repo also mixes import styles (`database`, `..database`, `routers`, `..routers`, `schemas`, and other package-relative imports), which can create duplicate module objects and makes test patching brittle.

### Plan

1. **Standardize on one canonical app module path strategy**
   - Preserve the current top-level module layout used by this repo (`main`, `database`, `routers`, etc.).
   - Use top-level module imports for app modules used by runtime and tests (`database`, `routers`, `schemas`, `settings`, `main`) instead of mixing them with package-relative imports.
   - Do not keep a mix of top-level and package-relative imports for the same app modules.
   - Package restructuring is out of scope for this migration.

   **Test file imports to normalize:**
   - `test_quizzes.py:3`: `from ..routers import quizzes, questions` (relative routers)
   - `test_quizzes.py:5`: `from ..database import client as mongo_client` (relative, aliased)
   - `test_questions.py:2`: `from ..routers import questions` (relative routers)
   - `test_sessions.py:4`: `from ..routers import quizzes, sessions, session_answers` (relative routers)
   - `test_sessions.py:5`: `from ..schemas import EventType` (relative schemas)
   - `test_sessions.py:9`: `from ..database import client as mongo_client` (relative, aliased)
   - `test_session_answers.py:5`: `from database import client as db_client` (absolute, different alias)
   - `test_session_answers.py:7`: `from ..routers import session_answers` (relative routers)
   - `test_session_answers.py:229`: local `from database import client` used for a direct DB assertion; move this to the shared sync admin/test client helper too
   - `app/tests/base.py`: already uses top-level `main` and `routers`; keep routers aligned but stop importing `main`/`app` at module top
   - `test_organization.py`: no app module import normalization needed beyond shared harness usage

2. **Introduce a shared accessor instead of importing the raw client everywhere**
   - Use `get_quiz_db()` as the single accessor used by routers and shared runtime code.
   - Store the shared PyMongo Async client in `database.py` as a module-owned singleton (for example `_client`).
   - Add `init_db()` and `close_db()` helpers in `database.py`; `init_db()` creates the singleton client and `get_quiz_db()` returns `_client[settings.mongo_db_name]` or the equivalent configured DB handle.
   - Update routers and any shared-client consumers to read through that accessor/module seam rather than holding an eagerly bound `client` reference.

3. **Define the PyMongo Async test seam around that accessor**
   - Tests should configure the canonical `database` module seam before creating the FastAPI app or `TestClient`.
   - Tests should use the same `init_db()` / `close_db()` path or an explicitly patched app-owned seam, not a separate router-global client mutation path.
   - Avoid a design that depends on mutating router-level globals after the app has already been imported.
   - Expose the sync admin/test database handle from the shared base test class (for example `self.db`) so direct setup/assertions stop importing `database.client` ad hoc.

4. **Introduce an app factory and remove eager app construction from the test import path**
   - Replace the current eager `app = FastAPI()` construction in `main.py` with a `create_app()` function.
   - `app/tests/base.py` must set test env/database configuration first and only then import `main` or `create_app()`.
   - Move `TestClient` creation in `app/tests/base.py` until after the database seam is configured.
   - Preserve the current runtime export by keeping `app = create_app()` in `main.py`.
   - Keep the deployment entrypoint unchanged (`main:app`) for this migration.
   - If `main.py` keeps `app = create_app()` at module scope, tests must ignore that module-level app object and instantiate their own app only after configuration.
   - A delayed import of `main` is acceptable, but only after the test database configuration is in place.
   - Use this app-factory path as the single supported construction flow for tests and runtime.

This makes the later PyMongo Async migration and test setup predictable.

---

## Phase 2: Handle Shared-Client Consumers Before the Client Swap

### `app/scripts/backfill_time_limits_and_spent.py`

This script is in scope because it imports `database.client` and uses synchronous collection APIs plus `bulk_write`.

**Planned approach:**

- Keep this script synchronous.
- Stop importing the shared app client.
- Give the script its own local sync `MongoClient`, like the other maintenance scripts already do.

This avoids mixing one-off script behavior into the async runtime migration and prevents the repo from breaking the moment `app/database.py` changes to PyMongo Async. No other standalone script under `app/scripts/` should change as part of this migration unless a new shared-client dependency is discovered.

---

## Phase 3: Switch the Shared Runtime Client in `database.py`

**File:** `app/database.py`

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
from pymongo import AsyncMongoClient
from settings import Settings
_client = None


def get_configured_db_name():
    return Settings().mongo_db_name


def init_db():
    global _client
    if _client is None:
        _client = AsyncMongoClient(
            os.getenv("MONGO_AUTH_CREDENTIALS"),
            maxPoolSize=20,
            minPoolSize=5,
            ...
        )


def get_quiz_db():
    if _client is None:
        raise RuntimeError("Database client is not initialized")
    return _client[get_configured_db_name()]


async def close_db():
    global _client
    if _client is not None:
        await _client.close()
        _client = None
```

All existing pool and timeout settings should be reviewed and carried over intentionally. PyMongo Async uses PyMongo's connection options, and rollout validation must confirm behavior on ECS.

The important constraint is that `MONGO_DB_NAME` must be resolved after runtime/test configuration is set, not frozen into a module-level constant during import.

### Chosen lifecycle and configuration design

- Do **not** keep creating the shared client at module import time.
- Create one `AsyncMongoClient` per process during FastAPI startup and close it during shutdown, using the `lifespan` async context manager (not the deprecated `@app.on_event("startup")` / `@app.on_event("shutdown")` API).
- Reuse that singleton through `get_quiz_db()`, instead of importing a module-global `client` directly inside routers.
- Keep the shared client in the `database.py` module-owned singleton created by `init_db()` and closed by `close_db()`.
- Close the client in the `lifespan` context manager's teardown (after `yield`). ECS is the only runtime now.
- Add a `MONGO_DB_NAME` setting and use it in both the async runtime client and the sync test/admin client.
  - Runtime default can remain `quiz` for backwards compatibility.
  - Test setup must override it to a safe test database name such as `quiz_test`.
  - Read the effective DB name during `init_db()`, `get_quiz_db()`, or via an explicit configure/settings function after test env setup; do **not** freeze it at module import time.
  - If configuration is centralized through `app/settings.py`, add the field there and have `database.py` read from the same source instead of duplicating environment parsing.
  - Document it in `docs/ENV.md` and local test setup instructions.
  - Add a test-harness guard that refuses writes or cleanup if the effective DB name resolves to `quiz`.

```python
# Lifespan integration with create_app()
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    init_db()
    yield
    await close_db()

def create_app():
    app = FastAPI(lifespan=lifespan)
    # ... middleware, routers ...
    return app
```
- Make connection-pool settings environment-configurable while keeping the current values as defaults.
  - Planned config surface: `MONGO_MAX_POOL_SIZE` default `20`, `MONGO_MIN_POOL_SIZE` default `5`.
  - Preserve the existing timeout/retry options unless rollout validation shows a need to change them.
  - For this migration, keep these pool-size vars optional and default-only; document them in `docs/ENV.md` as optional overrides and defer Terraform wiring unless post-rollout tuning is needed.

This phase should happen only after:

- the canonical import/accessor seam is in place
- the shared-client backfill script has been decoupled from `database.client`

---

## Phase 4: Update Runtime Router Files

The runtime router inventory remains mostly correct. The changes are still mostly mechanical: add `await` to DB operations and convert cursor materialization to `.to_list(length=None)`.

Routes should read the database handle through `get_quiz_db()` and then access collections from that handle (for example `db = get_quiz_db(); await db.sessions.find_one(...)`).

### Patterns to apply everywhere

| Current pattern | Planned pattern |
|---|---|
| `client.quiz.X.find_one(...)` | `db = get_quiz_db(); await db.X.find_one(...)` |
| `client.quiz.X.update_one(...)` | `db = get_quiz_db(); await db.X.update_one(...)` |
| `client.quiz.X.insert_one(...)` | `db = get_quiz_db(); await db.X.insert_one(...)` |
| `client.quiz.X.insert_many(...)` | `db = get_quiz_db(); await db.X.insert_many(...)` |
| `list(client.quiz.X.find(...))` | `db = get_quiz_db(); await db.X.find(...).to_list(length=None)` |
| `list(client.quiz.X.find(...).sort(...))` | `db = get_quiz_db(); await db.X.find(...).sort(...).to_list(length=None)` |
| `list(client.quiz.X.aggregate(...))` | `db = get_quiz_db(); await db.X.aggregate(...).to_list(length=None)` |

> **Walrus operator** `if (x := find_one(...)) is not None` becomes `if (x := await find_one(...)) is not None`

> **Note:** Line numbers below are as of the current commit and should be re-verified before execution, especially if PR 1's Pydantic v2 changes (e.g., `.parse_obj()` -> `.model_validate()` in `sessions.py`) shift router file line numbers.

### File-by-file runtime changes

#### `routers/session_answers.py` -- 5 calls

| Line | Current | Change |
|------|---------|--------|
| 92 | `list(client.quiz.sessions.aggregate(pipeline))` | `await db.sessions.aggregate(pipeline).to_list(length=None)` |
| 137 | `client.quiz.sessions.update_one(...)` | Add `await` |
| 187 | `client.quiz.sessions.find_one(...)` | Add `await` |
| 231 | `client.quiz.sessions.update_one(...)` | Add `await` |
| 267 | `list(client.quiz.sessions.aggregate(pipeline))` | `await db.sessions.aggregate(pipeline).to_list(length=None)` |

#### `routers/sessions.py` -- 16 calls

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

#### `routers/quizzes.py` -- 8 calls

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

**Special case:** `update_quiz_for_backwards_compatibility` must become `async def`, and its call site must use `await`.

#### `routers/organizations.py` -- 4 calls

| Line | Current | Change |
|------|---------|--------|
| 32 | `client.quiz.organization.find_one(...)` | Add `await` |
| 34 | `client.quiz.organization.insert_one(...)` | Add `await` |
| 43 | `client.quiz.organization.find_one(...)` | Add `await` |
| 63 | `client.quiz.organization.find_one(...)` (walrus) | Add `await` inside walrus |

#### `routers/questions.py` -- 2 calls

| Line | Current | Change |
|------|---------|--------|
| 21 | `client.quiz.questions.find_one(...)` (walrus) | Add `await` inside walrus |
| 55 | `list(client.quiz.questions.aggregate(...))` | `await ...aggregate(...).to_list(length=None)` |

#### `routers/forms.py` -- 3 calls

| Line | Current | Change |
|------|---------|--------|
| 26 | `quiz_collection.find_one(...)` (walrus) | Add `await` inside walrus |
| 53-57 | `list(client.quiz.questions.find(...).sort(...))` | `await ...find(...).sort(...).to_list(length=None)` |
| 83-105 | `list(client.quiz.questions.aggregate(...))` | `await ...aggregate(...).to_list(length=None)` |

### `import pymongo` usage

`sessions.py` currently imports `pymongo` for `pymongo.DESCENDING`. Keeping `pymongo` installed remains valid and intentional after the runtime migration.

---

## Phase 5: Redesign the Test Strategy for PyMongo Async

### Current state to describe accurately

- Tests currently call `mongoengine.connect(..., host="mongomock://...")`.
- The application under test does **not** use `mongoengine` for its runtime database access.
- The app talks directly to `database.client`, so the future PyMongo Async test setup is a design change, not a drop-in replacement of one mock package with another.

### Planned test strategy

1. **Continue using real MongoDB as the primary backend for the existing test suite**
   - The current suite already runs as integration-style testing against a real MongoDB service in CI (not mongomock, despite the `CLAUDE.md` claim -- see Phase 6 docs note).
   - Do not switch the whole suite to a mock async Mongo backend as part of this migration.

2. **Remove `mongoengine` and `mongomock` as one of the first steps in this phase**
   - These are confirmed no-ops: the `mongoengine.connect(...)` in `base.py` doesn't affect any test outcomes.
   - Remove both packages from `requirements.txt` and remove the `mongoengine.connect(...)` / `mongoengine.disconnect()` calls from `base.py`.

3. **Use the canonical database seam from Phase 1**
   - Configure the database seam before constructing the app via `create_app()` and before creating `TestClient`.
   - Avoid depending on router-global `client` rebinding or import-order side effects.

4. **Add a separate sync PyMongo admin/test client for setup and assertions**
   - Tests should stop using the shared runtime client directly for setup and verification.
   - Introduce one sync PyMongo admin/test client that points at the same configured MongoDB test database used by the app (`MONGO_DB_NAME`).
   - Use that admin client for direct `find_one`, `insert_one`, `update_one`, cleanup, and fixture setup where API-level setup is not preferable.
   - Route that handle through the shared base class (for example `self.db`) so test files stop importing `database.client` locally.
   - This keeps direct DB assertions simple while the app itself moves to PyMongo Async.

5. **Use a lifespan-aware `TestClient` pattern**
   - `BaseTestCase.setUpClass()` should configure `MONGO_DB_NAME` to a safe test DB name, create the sync admin/test client, then import `main`/`create_app`, construct the app, and enter the `TestClient` context manager.
   - Keep the context-managed `TestClient` open per test class for startup cost, but make database cleanup per-test for isolation.
   - Do not instantiate `TestClient(app)` without entering the context manager, because lifespan startup/shutdown must run for `init_db()` / `close_db()`.
   - `BaseTestCase.setUp()` should clear the configured test database before seeding fixtures, and `tearDown()` should clear it again after each test.
   - The cleanup helpers must refuse to run if the effective DB name is `quiz`.
   - `tearDownClass()` should exit the `TestClient` context so `close_db()` runs, then close the sync admin/test client explicitly.
   - Add a focused harness test or assertion that lifespan teardown closes the async app client and that sync admin cleanup does not rely on process exit.

6. **Expand the affected test inventory based on shared test harness usage**
   - `app/tests/base.py`
   - `app/tests/test_quizzes.py`
   - `app/tests/test_questions.py`
   - `app/tests/test_organization.py`
   - `app/tests/test_sessions.py`
   - `app/tests/test_session_answers.py`
   - `app/tests/test_forms.py` (new focused route tests to cover the migrated forms router)
   - `app/tests/test_scoring.py` is not DB-harness scope, but it must be included in full-suite verification because Python 3.12 and dependency upgrades can affect it.
   - Treat all `BaseTestCase` and `SessionsBaseTestCase` consumers as in scope for migration and verification, even if their DB usage is indirect through the shared harness.

7. **Rewrite the PyMongo-specific spy test**
   - `app/tests/test_session_answers.py` contains a spy pattern tied to `pymongo.collection.Collection`.
   - Preferred replacement: a behavioral API test that verifies the visible outcome.
   - If a call-level assertion is still necessary, patch only a narrow seam owned by the app (for example the accessor/collection seam introduced in Phase 1).
   - Do **not** patch driver internals directly after the migration.

### Test files with known direct DB usage

- `app/tests/test_quizzes.py`
- `app/tests/test_sessions.py`
- `app/tests/test_session_answers.py` (including the local `from database import client` import around the exact-length assertion path)

### Forms route coverage to add explicitly

The migration plan should not leave `app/routers/forms.py` as the only migrated router without direct route coverage. Add focused tests for `/form/{form_id}` covering:

- normal form retrieval
- non-form 404 behavior
- single-page mode
- OMR / options-count aggregation path

This broader test blast radius should be treated as first-class migration work, not a small cleanup after the runtime code is done.

> **Chosen cleanup policy:** use per-test cleanup for local isolation, while keeping the expensive `TestClient`/client startup at class scope. Cleanup must use the configured test database only. Do not call cleanup against the default `quiz` database in local or CI test flows.

---

## Phase 6: Documentation Updates

The migration is not done until the repo documentation matches the new runtime and test behavior.

### Required documentation changes

- Update `README.md`
  - Replace the current test instructions so they match the real-Mongo integration-test setup and the new app/test bootstrap path
  - Document any new test bootstrap assumptions, including the separate sync admin/test client pattern

- Update deployment/runtime documentation
  - Document `MONGO_DB_NAME` in `docs/ENV.md`, including runtime default and safe test override
  - Document `MONGO_MAX_POOL_SIZE` and `MONGO_MIN_POOL_SIZE` in `docs/ENV.md` as optional overrides with defaults matching current behavior

- Update rollout validation notes
  - Document that `/health` is not a DB-backed smoke check
  - Document DB-backed staging smoke validation as a required manual migration runbook step for now, separate from CI/CD liveness checks
  - Include test-data namespacing and cleanup expectations for create organization, create quiz, create session, and submit/update session answer flows

- Update `CLAUDE.md`
  - Correct "Tests use mongomock" -- tests actually run against real MongoDB in CI
  - Update testing section to reflect the new PyMongo Async test bootstrap

- Update any developer notes affected by the chosen database seam, app factory, or test bootstrap strategy
  - Treat `context_for_ai/plans/` as historical planning context unless a file there is still linked from active docs
  - After the cleanup, run the active-doc grep from PR 1 and resolve any remaining hits outside explicitly historical paths

- Keep this migration plan document aligned with the final implementation choices

### Done criteria for docs

- A developer can read the README and run the intended test flow without reverse-engineering the new harness
- A developer can read the README and understand the ECS-only deployment path plus DB-backed smoke expectations
- The dependency note about test-only packages in runtime artifacts is documented if the single-file requirements approach is retained

---

## Phase 7: Rollout and Validation

### Runtime scope for rollout

- ECS/FastAPI service path (testing + production): **in scope**

### Required validation

1. **Local / CI verification**
   - Focused test coverage for each migrated router area
   - Include explicit regression tests for `UpdateSessionAnswer` omitted-field and explicit-`null` semantics
   - Include the new focused `forms` route tests
   - Explicit validation of the rewritten test harness
   - Validation that the decoupled backfill script still runs with its local sync client
   - Keep automated tests on the real MongoDB-backed CI path
   - Docker image build verification for the ECS path
   - Local container-start smoke: run the built image with required env vars and hit `/health`

2. **DB-backed staging smoke validation**
   - Do not rely only on `/health`, because it does not touch MongoDB
   - For this migration, DB-backed staging validation is a required manual runbook step after ECS deploy, not an automated CI/CD workflow change yet
   - ECS deployment validation should exercise at least one DB-backed read path and one DB-backed write path after deploy
   - Use clearly namespaced migration-smoke test data and clean it up after the smoke run
   - Prefer simple end-to-end smoke flows such as:
     - create organization
     - create quiz
     - create session
     - submit/update session answer

3. **ECS-specific validation**
   - Verify connection pooling behavior, error rate, and request concurrency under representative load
   - Verify Python 3.12 runtime behavior in the Docker container

4. **Performance validation**
   - Measure before/after behavior in staging or load testing
   - Treat any concurrency/throughput gain as an observed outcome, not a headline assumption

---

## Execution Order

Do **not** swap `database.py` first and then try to repair the repo around it. Use phases that keep the repo workable throughout the migration.

1. **Normalize the database access seam (Phase 1)**
   - Standardize app module imports, not only database imports
   - Introduce `get_quiz_db()`, `init_db()`, and `close_db()` in the top-level `database` module
   - Add `create_app()`, keep `app = create_app()` in `main.py`, and move test app construction after seam configuration with delayed `main` import in the harness

2. **Handle shared-client consumers outside routers (Phase 2)**
   - Move `app/scripts/backfill_time_limits_and_spent.py` to its own local sync client

3. **Migrate runtime code in one coherent pass (Phase 3 + 4)**
   - Update `database.py` to use `pymongo.AsyncMongoClient`
   - Add `MONGO_DB_NAME` handling for runtime and tests without import-time freezing
   - Update the 6 router files
   - Introduce `lifespan` context manager for PyMongo Async client creation and shutdown

4. **Migrate affected tests (Phase 5)**
   - Update `app/tests/base.py`
   - Use a context-managed `TestClient` so lifespan startup/shutdown runs
   - Introduce the separate sync admin/test client and shared `self.db`-style helper
   - Apply the per-test cleanup policy with the `quiz`-DB safety guard
   - Update all `BaseTestCase` / `SessionsBaseTestCase` consumers as needed
   - Rewrite the PyMongo-specific spy test
   - Add focused `forms` route coverage

5. **Update documentation (Phase 6)**
   - README, deployment/runtime notes, and rollout validation notes

6. **Run verification and rollout validation (Phase 7)**
   - Focused local/CI validation first, including Docker build packaging checks
   - Then DB-backed staging checks for ECS
   - Then any load/performance comparison work

This order is designed to avoid a broken middle state. The database seam comes first so the runtime swap and test migration have a stable foundation.

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Router tests still bind the old client object | Normalize imports, add `create_app()`, and configure the seam before app/TestClient construction |
| `MONGO_DB_NAME` is read too early and tests target the wrong DB | Resolve the DB name after env/test configuration, not at module import, and refuse writes/cleanup when it resolves to `quiz` |
| Shared-client script breaks when `database.py` becomes async | Move `app/scripts/backfill_time_limits_and_spent.py` to its own local sync `MongoClient` first |
| Direct DB test helpers break after the runtime client becomes PyMongo Async | Move tests to a separate sync PyMongo admin/test client against the same configured DB before relying on PyMongo Async in app code |
| Test harness bypasses lifespan startup/shutdown | Use context-managed `TestClient` and assert teardown closes the async app client |
| Tests pollute each other locally through shared DB state | Use per-test cleanup with a shared class-level client/app context, and keep cleanup scoped to the configured test DB only |
| PyMongo-specific spy tests do not translate to the async runtime seam | Rewrite those tests around behavior or narrow app-owned seam patch points, not driver internals |
| One migrated router (`forms.py`) ships without direct route coverage | Add focused `forms` route tests as part of the test-harness migration |
| Runtime artifacts now include test-only packages | Document the decision explicitly until dependencies are split |
| Packaging or import cleanup accidentally changes deployment entrypoints | Preserve the current top-level module layout plus `main:app` export throughout the migration |
| Performance improvement is smaller than expected | Treat the benefit as a hypothesis and measure staging/load-test results rather than assuming a fixed multiplier |

---

## Done Criteria

- Shared runtime Mongo access uses `pymongo.AsyncMongoClient` through the normalized database seam
- The normalized runtime seam is the top-level `database` module with `get_quiz_db()` plus shared `init_db()` / `close_db()` lifecycle helpers
- FastAPI app construction uses `create_app()` with `lifespan` context manager for PyMongo Async client initialization/shutdown
- `main.py` exports `app = create_app()` for the ECS deployment entrypoint
- `MONGO_DB_NAME` is implemented and used by both the async runtime client and sync test/admin client without import-time freezing, and test cleanup guards reject the default `quiz` DB
- `app/scripts/backfill_time_limits_and_spent.py` no longer depends on the shared runtime client
- Affected tests pass with real MongoDB as the primary backend, a separate sync admin/test client for setup/assertion, and per-test cleanup for local isolation
- All `BaseTestCase` / `SessionsBaseTestCase` consumers have been verified under the new harness
- Focused route coverage exists for the migrated forms router
- Full-suite verification includes `app/tests/test_scoring.py`
- The PyMongo-specific test logic has been rewritten to use behavior checks or narrow app-owned seams
- Dependency choices are pinned and documented after the Python 3.12 compatibility spike selects the exact PyMongo Async and framework/test stack pins
- README/test instructions match the final setup
- Deployment/runtime docs reflect ECS-only deployment and `docs/ENV.md` documents `MONGO_DB_NAME` plus optional pool-size overrides
- Local Docker validation includes both image build success and a container-start `/health` smoke
- Required manual DB-backed staging validation has been completed for ECS with namespaced test data and cleanup
