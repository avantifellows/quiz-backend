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

This plan assumes `docs/plans/archive/python-3.12-upgrade-plan.md` (PR 1) has been completed and merged. Specifically, the following must already be done:

- All Lambda/SAM/Mangum traces removed
- Python upgraded to 3.12
- Pydantic v2 migration complete
- All dependencies at exact tested Python 3.12-compatible pins (including a PyMongo version that supports `AsyncMongoClient`)
- Full test suite passing on the new stack

## Driver Version Gate

This migration does **not** proceed on the current `pymongo==4.12.1` pin.

- The target driver pin for this plan is `pymongo==4.16.0` (latest stable, released 2026-01-07). Note: `4.13.0` is the first GA release of the async API, but it has two known async-specific bugs — `ServerSelectionTimeoutError` with timeouts on `AsyncMongoClient` (fixed in 4.13.1) and event-loop blocking during new connection creation (fixed in 4.13.2). Additionally, `4.15.1` (released 2025-09-16) fixes a `ServerSelectionTimeoutError` bug that occurs specifically when `AsyncMongoClient` is used with **uvicorn, FastAPI, or uvloop** — the exact deployment stack of this project (FastAPI + Uvicorn with 4 workers on ECS). Using any version older than `4.15.1` would cause intermittent timeout errors in production on this stack. The `4.16.0` pin is the latest stable version and includes all known async fixes. The project's current `dnspython==2.7.0` pin satisfies 4.16.0's requirement of `>=2.6.1`.
- Before Phase 1 starts, `app/requirements.txt` and any related dependency notes must be updated to the same exact target pin.
- All implementation notes, test validation, and rollout validation in this document assume that exact target pin unless this plan is explicitly revised first.
- If project constraints prevent moving from `4.12.1` to `4.16.0`, the absolute minimum acceptable version is `4.15.1` (first release fixing the uvicorn/FastAPI `ServerSelectionTimeoutError` bug). Do not implement the async migration on any version older than `4.15.1`.
- **MongoDB server version compatibility:** Before Phase 1 starts, verify that the MongoDB server versions used in CI (currently MongoDB 5.0 via `supercharge/mongodb-github-action@1.12.1`) and production (Atlas cluster) are compatible with `pymongo==4.16.0` async features. PyMongo 4.16.x is expected to work with MongoDB 5.0+, but this should be confirmed rather than assumed. Document the minimum required MongoDB server version. If the production Atlas cluster is on an older version, upgrade it before proceeding.

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
    - `app/tests/test_pydantic_v2_compat.py`
  - All `SessionsBaseTestCase` consumers:
    - `app/tests/test_sessions.py`
    - `app/tests/test_session_answers.py`
  - Import-normalization-only test scope:
    - `app/tests/test_pyobjectid.py`
  - This includes direct DB setup/assertion calls, the shared `TestClient` bootstrap path, the PyMongo-specific `Collection` spy test in `test_session_answers.py`, and the existing forms-route coverage currently living in `test_pydantic_v2_compat.py`.

- **Import-root contract**
  - `pytest.ini`
  - This file is in scope because `pythonpath = app` is part of the chosen top-level import strategy under pytest.

- **Dependencies and docs**
  - `app/requirements.txt`
  - `.env.example`
  - `README.md`
  - `docs/ENV.md`
  - `CLAUDE.md`
  - `docs/pymongo-async-staging-smoke.md` (new)
  - This migration plan document plus any test setup, deployment/runtime, and rollout-validation notes affected by the final design

- **Deployment config ownership for Mongo settings**
  - `terraform/testing/ecs.tf`
  - `terraform/prod/ecs.tf`
  - `terraform/testing/variables.tf`
  - `terraform/prod/variables.tf`
  - `terraform/testing/terraform.tfvars.example`
  - `terraform/prod/terraform.tfvars.example`
  - `terraform/testing/terraform.tfvars`
  - `terraform/prod/terraform.tfvars`
  - These files are in scope because `MONGO_DB_NAME` must become the authoritative DB selector in ECS and Terraform examples instead of relying on a DB name embedded in the URI path. Both `variables.tf` files must declare `variable "mongo_db_name" { type = string }` so that `ecs.tf` can reference `var.mongo_db_name`. Both real `terraform.tfvars` files (which are committed to git) must also receive appropriate `mongo_db_name` values (`quiz` for prod, the current DB name for testing), or the variable must be declared with `default = "quiz"` to prevent interactive prompts during `terraform apply`.

- **CI workflow**
  - `.github/workflows/ci.yml`
  - This file is in scope because CI should set an explicit safe test DB override (`MONGO_DB_NAME=quiz_test`) even though the test harness remains responsible for forcing a safe DB name before app construction.

- **Validation / rollout**
  - ECS/FastAPI service path (testing + production)

### Out of scope for this migration

- Standalone maintenance scripts that already create their own local sync `MongoClient`
- Broader performance work outside the Mongo driver swap
- Reorganizing the repo into separate runtime/test dependency files unless explicitly chosen as follow-up work
- Standardizing every legacy maintenance script on `MONGO_DB_NAME`; for this migration, that setting is required only for the migrated runtime path, the test harness, and the in-scope backfill script

### Explicit no-change item

- `app/scripts/add_marking_scheme_to_questions_without_details.py`
  - Remains synchronous and independent because it does not use the shared app client.
  - It may continue using its current hardcoded `quiz` database selection during this migration.
  - If Mongo config is later standardized across all maintenance scripts, that follow-up must be handled separately from this async runtime migration.

---

## Phase 1: Normalize the Database Access Seam

This phase is required before the client swap.

### Current problem

- Routers currently do `from database import client`, which binds the client object at import time.
- `app/tests/base.py` imports `main`, and `main.py` imports routers immediately.
- Rebinding `database.client` later in `BaseTestCase.setUpClass()` would not update already-imported router globals.
- The repo also mixes import styles (`database`, `..database`, `routers`, `..routers`, `schemas`, and other package-relative imports), which can create duplicate module objects and makes test patching brittle.

### Plan

**Phase 1 invariant before any async client swap work:** importing the top-level `database` module must be side-effect free. No dotenv loading, no client creation, and no DB-name resolution may happen during module import.

1. **Standardize on one canonical app module path strategy**
   - Preserve the current top-level module layout used by this repo (`main`, `database`, `routers`, etc.).
   - Use top-level module imports for app modules used by runtime and tests (`main`, `database`, `routers`, `schemas`, `settings`, `models`, `services`, `logger_config`) instead of mixing them with package-relative imports.
   - Treat `pytest.ini` as part of this contract and keep `pythonpath = app` aligned with the chosen top-level import strategy.
   - Do not keep a mix of top-level and package-relative imports for the same app modules.
   - Explicitly ban mixed import pairs such as `main` / `app.main`, `database` / `app.database`, `routers` / `app.routers`, `models` / `app.models`, `services` / `app.services`, and `logger_config` / `app.logger_config` after this migration. Note: `services` and `logger_config` already use consistent imports today, but including them in the ban list prevents future drift.
   - Add a lightweight enforcement step for that contract: a `local` hook in `.pre-commit-config.yaml` (grep-style check) should fail if banned mixed-root imports reappear. Pre-commit is preferred over a CI step because it gives immediate developer feedback and the project already uses pre-commit hooks. The CI step in Phase 6 can remain as defense-in-depth. Phase 7 verification should include a one-time explicit grep confirming the banned pairs are gone from active code/tests.
   - Package restructuring is out of scope for this migration.

   **Test file imports to normalize:**
   - `test_quizzes.py:3`: `from ..routers import quizzes, questions` (relative routers)
   - `test_quizzes.py:5`: `from ..database import client as mongo_client` (relative, aliased)
   - `test_pydantic_v2_compat.py:17`: `from ..routers import ...` (relative router import)
   - `test_pydantic_v2_compat.py:18`: `from ..database import client` (relative database import)
   - Note: `test_pydantic_v2_compat.py:19` (`from settings import Settings`) is already in canonical top-level style and needs no change
   - `test_questions.py:2`: `from ..routers import questions` (relative routers)
   - `test_sessions.py:4`: `from ..routers import quizzes, sessions, session_answers` (relative routers)
   - `test_sessions.py:5`: `from ..schemas import EventType` (relative schemas)
   - `test_sessions.py:9`: `from ..database import client as mongo_client` (relative, aliased)
   - `test_session_answers.py:5`: `from database import client as db_client` (absolute, different alias)
   - `test_session_answers.py:7`: `from ..routers import session_answers` (relative routers)
   - `test_session_answers.py:229`: local `from database import client` used for a direct DB assertion; move this to the shared sync admin/test client helper too
   - `test_pyobjectid.py`: `from ..models import ...` and `from ..main import app` should move to canonical top-level imports
   - `app/tests/base.py`: already uses top-level `main` and `routers`; keep routers aligned but stop importing `main`/`app` at module top. Note: `from routers import quizzes, sessions, organizations` (line 6) is safe to keep at module scope after Phase 1's side-effect-free invariant is applied, because routers will import `get_quiz_db` (a function reference) rather than triggering client creation at import time.
   - `test_organization.py`: no app module import normalization needed beyond shared harness usage

2. **Introduce a shared accessor instead of importing the raw client everywhere**
   - Use `get_quiz_db()` as the single accessor used by routers and shared runtime code.
   - Store the shared PyMongo Async client in `database.py` as a module-owned singleton (for example `_client`).
   - Add `init_db()` and `close_db()` helpers in `database.py`; `init_db()` creates the singleton client and `get_quiz_db()` returns `_client[settings.mongo_db_name]` or the equivalent configured DB handle.
   - Update routers and any shared-client consumers to read through that accessor/module seam rather than holding an eagerly bound `client` reference.
   - Treat removal of direct `.quiz` access in runtime code as an explicit migration task, not incidental cleanup.

3. **Define the PyMongo Async test seam around that accessor**
   - Tests should configure the canonical `database` module seam before creating the FastAPI app or `TestClient`.
   - Tests should use the same `init_db()` / `close_db()` path or an explicitly patched app-owned seam, not a separate router-global client mutation path.
   - Avoid a design that depends on mutating router-level globals after the app has already been imported.
   - Expose the sync admin/test database handle from the shared base test class (for example `self.db`) so direct setup/assertions stop importing `database.client` ad hoc.

4. **Introduce an app factory and remove eager app construction from the test import path**
   - Replace the current eager `app = FastAPI()` construction in `main.py` with a `create_app()` function.
   - `create_app()` owns FastAPI construction, middleware registration, router inclusion, and `/health` registration; no app setup should remain attached to a legacy module-global app object.
   - `logger = setup_logger()` at `main.py:10` can remain at module scope since it has no database dependency and does not need to move into `create_app()`.
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
- Read Mongo credentials and the effective DB name through the chosen lazy Mongo configuration seam instead of using `client.quiz`.
- **Line-number inventory for shared-client usage:**
  - Line 32: `from database import client` (the import to remove)
  - Line 109: `db = client.quiz` (hardcodes the database name)
  - Lines 110–111: `sessions = db.sessions; quizzes = db.quizzes` (derive collections from the hardcoded `db`)
- Preserve the current operational behavior while changing only the client source: keep `allowDiskUse=True`, `batch_size = 500`, and `bulk_write(..., ordered=False)` unless a separate follow-up intentionally revisits script performance semantics.
- Run it through the same explicit local env bootstrap flow used for local tests (for example `set -a; source .env; set +a; python app/scripts/backfill_time_limits_and_spent.py`), because `database.py` will no longer load `.env` implicitly.

This avoids mixing one-off script behavior into the async runtime migration and prevents the repo from breaking the moment `app/database.py` changes to PyMongo Async. No other standalone script under `app/scripts/` should change as part of this migration unless a new shared-client dependency is discovered.

> **`sys.path` note:** After removing the `database` import, the backfill script still imports `from schemas import EventType`, which requires the existing `sys.path` manipulation (lines 26–30) to remain in place. Either keep the path manipulation for that import, or ensure the script is always run from the `app/` directory. Resolving this `EventType` dependency more cleanly (e.g., inlining the enum values) is optional follow-up work, not required for this migration.

---

## Phase 3: Switch the Shared Runtime Client in `database.py`

**File:** `app/database.py`

> **Note:** The BEFORE block below is a simplified illustration of the key change, not a full representation of `app/database.py`. The actual file also contains `import os` (line 1), conditional dotenv loading (lines 4–10), and a `RuntimeError` check if credentials are not set (lines 12–16). These are intentionally removed in the AFTER version because `settings.py` takes over configuration ownership. Read the actual `app/database.py` before implementing.

```python
# BEFORE (simplified — see note above)
from pymongo import MongoClient
client = MongoClient(
    os.getenv("MONGO_AUTH_CREDENTIALS"),
    maxPoolSize=20,
    minPoolSize=5,
    ...
)

# AFTER
from pymongo import AsyncMongoClient
from settings import get_mongo_settings
_client = None


def get_configured_db_name():
    return get_mongo_settings().mongo_db_name


async def init_db():
    global _client
    if _client is None:
        mongo_settings = get_mongo_settings()
        _client = AsyncMongoClient(
            mongo_settings.mongo_auth_credentials,
            # Connection Pool Settings
            maxPoolSize=mongo_settings.mongo_max_pool_size,
            minPoolSize=mongo_settings.mongo_min_pool_size,
            # Timeout Settings
            maxIdleTimeMS=30000,
            connectTimeoutMS=5000,
            serverSelectionTimeoutMS=5000,
            # Reliability Settings
            retryWrites=True,
            retryReads=True,
        )
        await _client.admin.command("ping")


def get_quiz_db():
    if _client is None:
        raise RuntimeError("Database client is not initialized")
    return _client[get_configured_db_name()]


async def close_db():
    global _client
    if _client is not None:
        await _client.close()  # AsyncMongoClient.close() is a coroutine (unlike sync MongoClient.close())
        _client = None
```

All 7 existing connection settings must be carried over explicitly (as shown in the AFTER block above): `maxPoolSize`, `minPoolSize`, `maxIdleTimeMS`, `connectTimeoutMS`, `serverSelectionTimeoutMS`, `retryWrites`, `retryReads`. PyMongo Async uses PyMongo's connection options, and rollout validation must confirm behavior on ECS. Consider making `connectTimeoutMS` and `serverSelectionTimeoutMS` env-configurable (like pool sizes) since they control how fast the app fails when MongoDB is unreachable; this can be deferred to post-rollout tuning if not needed immediately.

The important constraint is that `MONGO_DB_NAME` must be resolved after runtime/test configuration is set, not frozen into a module-level constant during import.

### Chosen configuration ownership

- Mongo configuration lives in `app/settings.py`.
- Keep the existing general `Settings` model for current non-Mongo values such as `subset_size`.
- Add a dedicated lazy Mongo configuration path in `app/settings.py`, for example a separate `MongoSettings` model plus `get_mongo_settings()` helper.
- Put `mongo_auth_credentials`, `mongo_db_name`, `mongo_max_pool_size`, and `mongo_min_pool_size` on that dedicated Mongo settings path, not on the existing general `Settings` model.
- `app/database.py` must stop loading dotenv or owning environment bootstrap. Environment setup belongs to local shells, startup scripts, CI, and ECS.
- `python-dotenv` remains in `app/requirements.txt` after this migration because 7 standalone maintenance scripts in `app/scripts/` still use it. Removing it or splitting into separate runtime/scripts dependency files is out of scope for this migration.
- Read env-backed Mongo settings only inside runtime functions such as `init_db()`, `get_quiz_db()`, or sync test/admin client helpers.
- `get_mongo_settings()` should not cache env-backed Mongo values during this migration. If caching is introduced later, tests must explicitly clear that cache before app construction and before sync admin/test client setup.
- Do not create `MongoSettings()` or call `get_mongo_settings()` at module scope anywhere in runtime code, tests, or scripts.
- Existing module-scope `Settings()` usage for non-Mongo fields can remain if needed, because it will no longer carry Mongo values.
- This choice keeps unrelated module-scope `Settings()` users out of scope for this migration while still protecting `MONGO_DB_NAME` and connection settings from import-time freezing.
- The async runtime client is created only during app lifespan startup, after configuration is already in place.
- Authoritative DB-selection rule for this migration: the application chooses the database via `MONGO_DB_NAME` in every environment, and `MONGO_AUTH_CREDENTIALS` is only the connection/auth URI.
- ECS task definitions in `terraform/testing/ecs.tf` and `terraform/prod/ecs.tf` must inject `MONGO_DB_NAME` explicitly alongside `MONGO_AUTH_CREDENTIALS`.
- Terraform URI examples should stop embedding environment-specific DB names in the URI path; use cluster/auth URIs there and set the DB name separately via `MONGO_DB_NAME` to avoid split ownership.
- `README.md`, `.env.example`, `docs/ENV.md`, and `docs/pymongo-async-staging-smoke.md` must all describe the same rule instead of treating the URI path as the source of truth.

### Chosen local env bootstrap ownership

- Keep env loading outside application code; do not replace `database.py` dotenv loading with a second hidden bootstrap mechanism.
- Supported local test and script flows should explicitly source `.env` before execution when env vars are not already exported.
- Document concrete examples in `README.md` and script notes, such as:
  - `set -a; source .env; set +a; pytest`
  - `set -a; source .env; set +a; python app/scripts/backfill_time_limits_and_spent.py`
- Existing shell wrappers such as `startServerMac.sh` and `startServerLinux.sh` can remain valid examples for local server startup, but they are not the bootstrap mechanism for tests.
- CI and ECS continue to inject env explicitly rather than depending on `.env` files.

### Chosen lifecycle and configuration design

- Do **not** keep creating the shared client at module import time.
- Create one `AsyncMongoClient` per process during FastAPI startup and close it during shutdown, using the `lifespan` async context manager (not the deprecated `@app.on_event("startup")` / `@app.on_event("shutdown")` API).
- Lifespan startup should be fail-fast: after constructing `AsyncMongoClient`, immediately run a simple connectivity check such as `await _client.admin.command("ping")`.
- If that startup connectivity check fails because of bad credentials, DNS, or network reachability, app startup should fail instead of deferring the error to the first DB-backed request.
- Reuse that singleton through `get_quiz_db()`, instead of importing a module-global `client` directly inside routers.
- Keep the shared client in the `database.py` module-owned singleton created by `init_db()` and closed by `close_db()`.
- Close the client in the `lifespan` context manager's teardown (after `yield`). ECS is the only runtime now.
- Add a `MONGO_DB_NAME` setting and use it in both the async runtime client and the sync test/admin client.
  - Runtime default can remain `quiz` for backwards compatibility.
  - Test setup must override it to a safe test database name such as `quiz_test`.
  - Read the effective DB name during `init_db()`, `get_quiz_db()`, or via an explicit configure/settings function after test env setup; do **not** freeze it at module import time.
  - `database.py`, sync test/admin helpers, and the shared-client backfill script should all read the DB name from the same lazy Mongo settings source instead of duplicating environment parsing.
  - Legacy standalone maintenance scripts outside this migration may continue using hardcoded `quiz`; standardizing them on `MONGO_DB_NAME` is follow-up work, not part of this plan.
  - Document it in `docs/ENV.md` and local test setup instructions.
  - Add a test-harness guard that refuses writes or cleanup if the effective DB name resolves to `quiz`.

```python
# Lifespan integration with create_app()
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    await init_db()
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

The runtime router inventory remains mostly correct. The changes are still mostly mechanical: add `await` to DB operations and convert cursor materialization to the PyMongo Async pattern verified against the chosen target pin (`pymongo==4.16.0`).

Routes should read the database handle through `get_quiz_db()` and then access collections from that handle (for example `db = get_quiz_db(); await db.sessions.find_one(...)`).
As part of this phase, every direct `.quiz` access in runtime code must be removed and replaced with the configured DB handle returned by `get_quiz_db()`.

### Patterns to apply everywhere

| Current pattern | Planned pattern |
|---|---|
| `client.quiz.X.find_one(...)` | `db = get_quiz_db(); await db.X.find_one(...)` |
| `client.quiz.X.update_one(...)` | `db = get_quiz_db(); await db.X.update_one(...)` |
| `client.quiz.X.insert_one(...)` | `db = get_quiz_db(); await db.X.insert_one(...)` |
| `client.quiz.X.insert_many(...)` | `db = get_quiz_db(); await db.X.insert_many(...)` |
| `list(client.quiz.X.find(...))` | `db = get_quiz_db(); await db.X.find(...).to_list(length=None)` |
| `list(client.quiz.X.find(...).sort(...))` | `db = get_quiz_db(); await db.X.find(...).sort(...).to_list(length=None)` |
| `list(client.quiz.X.aggregate(...))` | `db = get_quiz_db(); cursor = await db.X.aggregate(...); await cursor.to_list(length=None)` |
| `{x for x in client.quiz.X.aggregate(...)}` (direct iteration over aggregate cursor) | `db = get_quiz_db(); cursor = await db.X.aggregate(...); results = await cursor.to_list(length=None)` then build the comprehension from `results`. Alternatively, `async for item in cursor` is valid if you don't want to materialize the full list. |

> **Walrus operator** `if (x := find_one(...)) is not None` becomes `if (x := await find_one(...)) is not None`
>
> **Walrus + aggregate + list combo** (`questions.py:55`): `if (questions := list(client.quiz.questions.aggregate(pipeline))) is not None:` requires a multi-step transformation because `aggregate()` is a coroutine:
> ```python
> # BEFORE
> if (questions := list(client.quiz.questions.aggregate(pipeline))) is not None:
>
> # AFTER
> cursor = await db.questions.aggregate(pipeline)
> questions = await cursor.to_list(length=None)
> if questions is not None:  # always True (list() never returns None), preserved for behavior compatibility
> ```
> The walrus operator cannot be preserved here because the transformation splits into two awaited statements. The `is not None` check is always True but can be kept for behavior compatibility.

> **Critical async/sync distinction for PyMongo Async methods:**
> - `find()` is **NOT a coroutine** — it returns an `AsyncCursor` directly without `await`. Do NOT write `cursor = await db.X.find(filter)`.
> - `sort()`, `skip()`, `limit()` are **regular (non-async) chainable methods** on `AsyncCursor` — no `await` needed.
> - `aggregate()` **IS a coroutine** — you MUST `await` it to get the cursor: `cursor = await db.X.aggregate(pipeline)`.
> - `to_list()`, `find_one()`, `insert_one()`, `update_one()`, `insert_many()`, `update_many()` are all **async** and need `await`.
>
> The pattern `await db.X.find(...).to_list(length=None)` is correct because Python evaluates it as `await (db.X.find(...).to_list(length=None))` — the `await` applies to `to_list()`, not to `find()`. The two-step aggregate pattern (`cursor = await db.X.aggregate(...); await cursor.to_list(...)`) uses `await` differently because `aggregate()` itself is a coroutine.

> **Aggregate note:** Before merging, confirm the exact `aggregate(...)` async contract against the chosen `pymongo==4.16.0` pin in a focused test/spike and then use that verified pattern consistently across all migrated routes. Do not carry over sync `list(...)` assumptions into the async rewrite.

> **Behavior-preservation note:** Keep existing query behavior intact during the async rewrite, including `find_one(..., sort=[...])`, `find(..., sort=[...], limit=2)`, and the current successful empty-list response semantics for `questions.py` collection reads.

> **Note:** Line numbers below are as of the current commit and should be re-verified before execution, especially if PR 1's Pydantic v2 changes (e.g., `.parse_obj()` -> `.model_validate()` in `sessions.py`) shift router file line numbers.

### File-by-file runtime changes

#### `routers/session_answers.py` -- 5 calls

| Line | Current | Change |
|------|---------|--------|
| 92 | `list(client.quiz.sessions.aggregate(pipeline))` | `cursor = await db.sessions.aggregate(pipeline)` then `await cursor.to_list(length=None)` |
| 137 | `client.quiz.sessions.update_one(...)` | Add `await` |
| 187 | `client.quiz.sessions.find_one(...)` | Add `await` |
| 231 | `client.quiz.sessions.update_one(...)` | Add `await` |
| 267 | `list(client.quiz.sessions.aggregate(pipeline))` | `cursor = await db.sessions.aggregate(pipeline)` then `await cursor.to_list(length=None)` |

#### `routers/sessions.py` -- 16 calls

| Line | Current | Change |
|------|---------|--------|
| 111 | `client.quiz.sessions.find_one(...)` | Add `await` |
| 139 | `client.quiz.quizzes.find_one(...)` | Add `await` |
| 153 | `list(client.quiz.sessions.find(...))` | `await ...find(...).to_list(length=None)` |
| 224 | `client.quiz.sessions.update_one(...)` | Add `await` |
| 240 | `client.quiz.sessions.update_one(...)` | Add `await` |
| 304 | `client.quiz.sessions.insert_one(...)` | Add `await` |
| 339 | `client.quiz.sessions.find_one(...)` | Add `await` |
| 488 | `client.quiz.quizzes.find_one(...)` | Add `await` |
| 513 | `client.quiz.sessions.update_one(...)` | Add `await` |
| 532 | `client.quiz.sessions.find_one(...)` | Add `await` |
| 535 | `client.quiz.quizzes.find_one(...)` | Add `await` |
| 539 | `client.quiz.sessions.update_one(...)` | Add `await` |
| 565 | `client.quiz.sessions.aggregate(...)` | `cursor = await ...aggregate(...)` then `await cursor.to_list(length=None)` |
| 597 | `client.quiz.sessions.find_one(...)` | Add `await` |
| 605 | `client.quiz.quizzes.find_one(...)` | Add `await` |
| 639 | `client.quiz.questions.find_one(...)` | Add `await` |

#### `routers/quizzes.py` -- 8 calls

| Line | Current | Change |
|------|---------|--------|
| 70 | `quiz_collection.update_one(...)` inside non-async `update_quiz_for_backwards_compatibility` | Make function `async def`, add `await` to `update_one`, replace `quiz_collection` parameter with internal `get_quiz_db()` call |
| 192 | `update_quiz_for_backwards_compatibility(quiz_collection, quiz_id, quiz)` (call site) | Add `await`, remove `quiz_collection` argument: `await update_quiz_for_backwards_compatibility(quiz_id, quiz)` |
| 103 | `client.quiz.questions.insert_many(...)` | Add `await` |
| 116 | `client.quiz.questions.aggregate(...)` | `cursor = await ...aggregate(...)` then `await cursor.to_list(length=None)` |
| 124 | `client.quiz.questions.aggregate(...)` | `cursor = await ...aggregate(...)` then `await cursor.to_list(length=None)` |
| 145 | `client.quiz.quizzes.insert_one(...)` | Add `await` |
| 172 | `quiz_collection.find_one(...)` (walrus) | Add `await` inside walrus |
| 201-205 | `list(client.quiz.questions.find(...).sort(...))` | `await ...find(...).sort(...).to_list(length=None)` |
| 235-257 | `list(client.quiz.questions.aggregate(...))` | `cursor = await ...aggregate(...)` then `await cursor.to_list(length=None)` |

**Special case:** `update_quiz_for_backwards_compatibility` must become `async def`, and its call site must use `await`.

**Note:** Remove the `quiz_collection = client.quiz.quizzes` assignment at line 170 and replace with `db = get_quiz_db()`. Similarly, `update_quiz_for_backwards_compatibility` currently takes a collection as a parameter — update it to call `get_quiz_db()` internally instead.

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
| 55 | `list(client.quiz.questions.aggregate(...))` | `cursor = await ...aggregate(...)` then `await cursor.to_list(length=None)` |

#### `routers/forms.py` -- 3 calls

**Note:** Remove the `quiz_collection = client.quiz.quizzes` assignment at line 24 and replace with `db = get_quiz_db()`.

| Line | Current | Change |
|------|---------|--------|
| 26 | `quiz_collection.find_one(...)` (walrus) | After variable rename (line 24 → `db = get_quiz_db()`), becomes `await db.quizzes.find_one(...)` inside walrus |
| 53-57 | `list(client.quiz.questions.find(...).sort(...))` | `await ...find(...).sort(...).to_list(length=None)` |
| 83-105 | `list(client.quiz.questions.aggregate(...))` | `cursor = await ...aggregate(...)` then `await cursor.to_list(length=None)` |

### `import pymongo` usage

`sessions.py` currently imports `pymongo` for `pymongo.DESCENDING`. Keeping `pymongo` installed remains valid and intentional after the runtime migration.

---

## Phase 5: Redesign the Test Strategy for PyMongo Async

### Landability rule

- Phase 3, Phase 4, and Phase 5 must land together as one coherent runtime-plus-harness change set after the seam work in Phases 1 and 2 is complete.
- No mergeable intermediate state may switch runtime code to `AsyncMongoClient` while the old harness/import path is still in place.
- A temporary compatibility seam is not part of the current plan. If implementation later proves one is required, stop and update this plan before merging that approach.

### Current state to describe accurately

- The current suite already runs against a real MongoDB service; it is not a mongomock-based test stack.
- The application under test still talks directly to `database.client` today, so the PyMongo Async test harness work is a seam redesign, not a mock-library swap.
- The current harness clears collections from the default `quiz` database, which makes the configured test-DB override plus safety guard a required part of this migration.

### Planned test strategy

1. **Continue using real MongoDB as the primary backend for the existing test suite**
   - The current suite already runs as integration-style testing against a real MongoDB service in CI.
   - Do not switch the whole suite to a mock async Mongo backend as part of this migration.

2. **Use the canonical database seam from Phase 1**
   - Configure the database seam before constructing the app via `create_app()` and before creating `TestClient`.
   - Avoid depending on router-global `client` rebinding or import-order side effects.

3. **Add a separate sync PyMongo admin/test client for setup and assertions**
   - Tests should stop using the shared runtime client directly for setup and verification.
   - Introduce one sync PyMongo admin/test client that points at the same configured MongoDB test database used by the app (`MONGO_DB_NAME`).
   - Use that admin client for direct `find_one`, `insert_one`, `update_one`, cleanup, and fixture setup where API-level setup is not preferable.
   - Route that handle through the shared base class (for example `self.db`) so test files stop importing `database.client` locally.
   - Treat every direct `.quiz` access in shared test code and direct-DB assertions as in scope for removal or isolation behind that helper.
   - This keeps direct DB assertions simple while the app itself moves to PyMongo Async.

4. **Use a lifespan-aware `TestClient` pattern**
   - `BaseTestCase.setUpClass()` should configure `MONGO_DB_NAME` to a safe test DB name, create the sync admin/test client, then import `main`/`create_app`, construct the app, and enter the `TestClient` context manager.
   - The test harness owns this safety requirement even outside CI: it must force a safe non-`quiz` database name before app construction rather than relying on ambient shell state.
   - Keep the context-managed `TestClient` open per test class for startup cost, but make database cleanup per-test for isolation.
   - Do not instantiate `TestClient(app)` without entering the context manager, because lifespan startup/shutdown must run for `init_db()` / `close_db()`.
   - `BaseTestCase.setUp()` should clear the configured test database before seeding fixtures, and `tearDown()` should clear it again after each test.
   - The cleanup helpers must refuse to run if the effective DB name is `quiz`.
   - `tearDownClass()` should exit the `TestClient` context so `close_db()` runs, then close the sync admin/test client explicitly.
   - Add a focused harness test or assertion that lifespan teardown closes the async app client and that sync admin cleanup does not rely on process exit.

5. **Normalize fixture paths as part of the harness cleanup**
   - Remove the repo-root-CWD assumption from fixture loading while `app/tests/base.py` and related tests are being rewritten.
   - Load fixture files from paths derived from the test file location (for example `Path(__file__).resolve().parent / "dummy_data" / ...`) instead of `open("app/tests/...")`.
   - Treat this as part of the required harness stabilization work, not optional polish.
   - **Full inventory of repo-root-relative fixture loads (16 occurrences across 4 files):**

     | File | Occurrences | Lines |
     |------|------------|-------|
     | `app/tests/base.py` | 8 | 22, 30, 38, 46, 54, 62, 70, 78 |
     | `app/tests/test_pydantic_v2_compat.py` | 3 | 334, 504, 552 |
     | `app/tests/test_sessions.py` | 3 | 194, 429, 446 |
     | `app/tests/test_scoring.py` | 2 | 9, 42 |

   - Note: `test_scoring.py` is not in DB-harness scope, but its 2 fixture path lines must be included in this normalization pass — the fixture path fix is independent of DB harness work and trivial to apply.

6. **Expand the affected test inventory based on shared test harness usage**
   - `app/tests/base.py`
   - `app/tests/test_quizzes.py`
   - `app/tests/test_questions.py`
   - `app/tests/test_organization.py`
   - `app/tests/test_pydantic_v2_compat.py`
   - `app/tests/test_sessions.py`
   - `app/tests/test_session_answers.py`
   - `app/tests/test_pyobjectid.py` for import normalization and app-factory alignment
   - `app/tests/test_scoring.py` is not DB-harness scope, but it must be included in full-suite verification because Python 3.12 and dependency upgrades can affect it.
   - Treat all `BaseTestCase` and `SessionsBaseTestCase` consumers as in scope for migration and verification, even if their DB usage is indirect through the shared harness.

7. **Drop the PyMongo-specific spy test**
   - `app/tests/test_session_answers.py` contains `test_batch_update_uses_aggregate_not_find_one`, which patches `pymongo.collection.Collection` to verify the code uses `aggregate()` instead of `find_one()`.
   - **Recommended action: drop this test entirely.** The aggregate-over-find_one choice is an internal optimization locked in by the route code itself. Both methods produce identical visible output, so a behavioral replacement test cannot meaningfully distinguish them. The performance benefit of using `aggregate` is real but does not need a unit-test guard.
   - After migration, patching `pymongo.collection.Collection` would not work because the runtime uses `AsyncCollection`, making the test broken regardless.
   - Do **not** patch driver internals directly after the migration.

### Test file DB call inventory

These direct DB calls must be migrated to use `self.db` (the sync admin/test client) instead of importing `database.client` directly. Total: **24 lines** (20 direct DB calls + 4 `addCleanup` lambdas).

| Test File | Direct DB Calls | Lines |
|-----------|----------------|-------|
| `app/tests/test_quizzes.py` | 5 | 247, 254, 337, 339, 345 |
| `app/tests/test_sessions.py` | 4 | 105, 137, 171, 704 |
| `app/tests/test_session_answers.py` | 5 direct + 4 `addCleanup` lambdas | 239, 247, 250, 262, 270, 282, 290, 374, 384 (line 229 is a local import, not a DB call). Direct DB calls at lines 239, 247, 262, 282, 374. `addCleanup` lambdas at lines 250, 270, 290, 384. |
| `app/tests/test_pydantic_v2_compat.py` | 5 | 204, 431, 434, 481, 484 |
| `app/tests/base.py` | 1 | 17 (`db = mongo_client.quiz`) |
| **Total** | **24** | |

> **Note:** Line numbers are as of the current commit and should be re-verified before execution, as with the router inventory.

> **`addCleanup` removal note:** The 4 `addCleanup` lambdas in `test_session_answers.py` (lines 250, 270, 290, 384) delete individual session documents after specific tests. With the new per-test `setUp()`/`tearDown()` cleanup that drops entire collections, these `addCleanup` calls become redundant dead code. They should be **removed** rather than migrated to the new `self.db` handle. (MongoDB silently handles operations on dropped collections, so they wouldn't cause errors — just confusion for future readers.)

### Forms route coverage to keep explicit

The migration plan should not describe forms coverage as missing from scratch. Direct form endpoint coverage already exists in `app/tests/test_pydantic_v2_compat.py`, and that coverage should remain in place for this migration while the harness is updated. Verify `/form/{form_id}` coverage for:

- normal form retrieval
- non-form 404 behavior
- single-page mode
- OMR / options-count aggregation path

Adding a dedicated `app/tests/test_forms.py` can be treated as optional follow-up cleanup if the team later wants cleaner test organization, but it is not required to complete this migration.

> **Chosen cleanup policy:** use per-test cleanup for local isolation, while keeping the expensive `TestClient`/client startup at class scope. Cleanup must use the configured test database only. Do not call cleanup against the default `quiz` database in local or CI test flows.

---

## Phase 6: Documentation Updates

The migration is not done until the repo documentation matches the new runtime and test behavior.

### Required documentation changes

- Update `README.md`
  - Replace the current test instructions so they match the real-Mongo integration-test setup and the new app/test bootstrap path
  - Correct the ECS env-var guidance to say runtime values such as `MONGO_AUTH_CREDENTIALS` are injected through Terraform ECS task-definition environment configuration, not GitHub repository environments
  - Document any new test bootstrap assumptions, including the separate sync admin/test client pattern
  - Add concrete `MONGO_DB_NAME` examples that distinguish local runtime default from local test override (`quiz_test`)
  - Add explicit local command examples that source `.env` before running `pytest` or the in-scope backfill script, because application code no longer loads dotenv implicitly

- Update deployment/runtime documentation
  - Add `MONGO_DB_NAME` to `.env.example` and show a concrete safe test value example (`quiz_test`)
  - Document `MONGO_DB_NAME` in `docs/ENV.md`, including runtime default and safe test override
  - Document `MONGO_MAX_POOL_SIZE` and `MONGO_MIN_POOL_SIZE` in `docs/ENV.md` as optional overrides with defaults matching current behavior
  - Keep `MONGO_AUTH_CREDENTIALS` documented there as part of the same Settings-owned Mongo config surface
  - Update `docs/ENV.md` to remove the stale GitHub-repository-environments wording and replace it with Terraform/ECS task-definition ownership for runtime env injection
  - Make the examples explicit about where they apply: local runtime default, local test override, and CI test override
  - Update Terraform/ECS examples in the docs so the URI no longer carries the environment-specific DB name; `MONGO_DB_NAME` is the authoritative selector
  - Update `terraform/testing/ecs.tf`, `terraform/prod/ecs.tf`, `terraform/testing/terraform.tfvars.example`, and `terraform/prod/terraform.tfvars.example` to match that ownership rule
  - Declare `variable "mongo_db_name" { type = string }` in both `terraform/testing/variables.tf` and `terraform/prod/variables.tf` so that `ecs.tf` can reference `var.mongo_db_name` without an undeclared-variable error
  - Update the real `terraform/testing/terraform.tfvars` and `terraform/prod/terraform.tfvars` files with appropriate `mongo_db_name` values (`quiz` for prod, the current DB name for testing); these files are committed to git and a missing value would cause `terraform apply` to prompt interactively or fail in CI/CD
  - State plainly that legacy standalone maintenance scripts outside this migration may still target hardcoded `quiz` until follow-up cleanup standardizes them

- Update rollout validation notes
  - Create `docs/pymongo-async-staging-smoke.md` as the required destination for the staging smoke checklist and cleanup steps
  - Document that `/health` is not a DB-backed smoke check
  - Document DB-backed staging smoke validation as a required manual migration runbook step for now, separate from CI/CD liveness checks
  - Document that process startup should fail fast if the Mongo connectivity check during lifespan startup cannot `ping` the server
  - Include test-data namespacing and cleanup expectations for create organization, create quiz, create session, and submit/update session answer flows

- Update CI workflow configuration
  - Set `MONGO_DB_NAME=quiz_test` explicitly in `.github/workflows/ci.yml`
  - Add the lightweight mixed-import-root enforcement check chosen in Phase 1 if that check is implemented in CI rather than pre-commit
  - Keep this as defense in depth; the harness must still force a safe test DB name before app construction when tests run outside CI

- Update `CLAUDE.md`
  - Keep the existing real-Mongo testing description
  - Update the testing section only with the new PyMongo Async bootstrap, app-factory, and test-harness details that remain true after implementation

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
   - Verify the existing forms route coverage path in `test_pydantic_v2_compat.py` under the migrated harness
   - Explicit validation of the rewritten test harness
   - Explicit validation that app startup fails fast when Mongo connectivity cannot be established during lifespan startup
   - Validation that the decoupled backfill script still runs with its local sync client
   - Keep automated tests on the real MongoDB-backed CI path
   - Docker image build verification for the ECS path is a required manual validation step for this migration unless a later workflow change is added
   - Local container-start smoke is also a manual validation step for now: run the built image with required env vars and hit `/health`
   - CI workflow changes in this migration are limited to the safe `MONGO_DB_NAME` override plus the lightweight import-root enforcement check if chosen; do not describe DB-backed smoke or Docker validation as already automated

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
   - Check the effective Mongo connection budget across `uvicorn workers x ECS tasks x pool settings`, and explicitly re-evaluate whether `MONGO_MIN_POOL_SIZE=5` should remain unchanged after rollout
   - **Connection pool budget math** (verify against the Atlas tier's connection limit before rollout):
     - Per task: 4 Uvicorn workers x 20 maxPoolSize = **80 max connections**
     - Per task: 4 Uvicorn workers x 5 minPoolSize = **20 min connections**
     - At min scale (1 ECS task): 20–80 connections
     - At max scale (10 ECS tasks): **200–800 connections**
     - If the Atlas cluster's connection limit is below 800, tune `MONGO_MAX_POOL_SIZE` and `MONGO_MIN_POOL_SIZE` down before rollout to stay safely within limits
   - Verify Python 3.12 runtime behavior in the Docker container

4. **Performance validation**
   - Measure before/after behavior in staging or load testing
   - Treat any concurrency/throughput gain as an observed outcome, not a headline assumption

---

## Execution Order

Do **not** swap `database.py` first and then try to repair the repo around it. Use phases that keep the repo workable throughout the migration.

1. **Normalize the database access seam (Phase 1)**
   - Standardize app module imports, not only database imports
   - Keep `pytest.ini` aligned with the top-level import strategy
   - Introduce `get_quiz_db()`, `init_db()`, and `close_db()` in the top-level `database` module
   - Introduce the dedicated lazy Mongo settings/helper seam in `app/settings.py` so Mongo env is never captured by existing module-scope `Settings()` usage
   - Add `create_app()`, keep `app = create_app()` in `main.py`, and move test app construction after seam configuration with delayed `main` import in the harness
   - Add the lightweight import-root enforcement check or verification command before moving on to the async swap

2. **Handle shared-client consumers outside routers (Phase 2)**
   - Move `app/scripts/backfill_time_limits_and_spent.py` to its own local sync client
   - Document and use the explicit local env bootstrap flow for tests and scripts instead of hidden dotenv loading in `database.py`

3. **Land the runtime swap, router rewrite, and harness rewrite together (Phases 3 + 4 + 5)**
   - Update `database.py` to use `pymongo.AsyncMongoClient`
   - Use the driver-gate target `pymongo==4.16.0`; do not implement the async swap on any version older than `4.15.1`
   - Add `MONGO_DB_NAME` handling for runtime, tests, the in-scope backfill script, ECS task definitions, and Terraform/doc examples without import-time freezing
   - Declare `variable "mongo_db_name" { type = string }` in `terraform/testing/variables.tf` and `terraform/prod/variables.tf`; set the value in both real `terraform.tfvars` files alongside the `ecs.tf` container_definitions update
   - Update the 6 router files
   - Update `app/tests/base.py`
   - Use a context-managed `TestClient` so lifespan startup/shutdown runs
   - Introduce the separate sync admin/test client and shared `self.db`-style helper
   - Apply the per-test cleanup policy with the `quiz`-DB safety guard
   - Normalize fixture paths so test data loading no longer depends on repo-root CWD
   - Update all `BaseTestCase` / `SessionsBaseTestCase` consumers as needed
   - Update `test_pydantic_v2_compat.py` and `test_pyobjectid.py` as part of the harness/import cleanup scope
   - Drop the PyMongo-specific spy test (`test_batch_update_uses_aggregate_not_find_one`)
   - Remove the 4 redundant `addCleanup` lambdas in `test_session_answers.py` (lines 250, 270, 290, 384) rather than migrating them
   - Keep forms route coverage explicit during verification, whether it remains in `test_pydantic_v2_compat.py` or is later relocated
   - Introduce `lifespan` context manager for PyMongo Async client creation, fail-fast connectivity verification, and shutdown
   - Treat this as one merge boundary; do not land runtime async changes without the harness rewrite in the same coherent PR/change set

4. **Update documentation (Phase 6)**
   - README, `.env.example`, `docs/ENV.md`, `CLAUDE.md`, and `docs/pymongo-async-staging-smoke.md`
   - Make `MONGO_DB_NAME` the documented authoritative DB selector everywhere and remove stale GitHub-environments wording from `docs/ENV.md`

5. **Update CI configuration**
   - Set `MONGO_DB_NAME=quiz_test` in `.github/workflows/ci.yml` while keeping the harness-owned safety override
   - Add the import-root enforcement check here if Phase 1 chose a CI-based guard instead of pre-commit
   - Do not add new DB-backed deploy smoke or Docker validation automation in this migration

6. **Run verification and rollout validation (Phase 7)**
   - Focused local/CI validation first, including manual Docker build packaging checks
   - Then DB-backed staging checks for ECS
   - Then any load/performance comparison work

This order is designed to avoid a broken middle state. The database seam comes first so the runtime swap and test migration have a stable foundation.

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| The repo starts implementation without deciding the async-ready driver pin | Gate the work on `pymongo==4.16.0` being selected consistently in `app/requirements.txt`, this plan, and rollout notes; otherwise defer the migration. The absolute minimum acceptable version is `4.15.1` (fixes a uvicorn/FastAPI-specific `ServerSelectionTimeoutError` bug) |
| Router tests still bind the old client object | Normalize imports, add `create_app()`, and configure the seam before app/TestClient construction |
| `MONGO_DB_NAME` is read too early and tests target the wrong DB | Resolve the DB name after env/test configuration, not at module import, and refuse writes/cleanup when it resolves to `quiz` |
| Adding Mongo fields to the existing `Settings` model causes import-time freezing through existing module-scope `Settings()` calls | Keep Mongo config on a separate lazy `MongoSettings` / `get_mongo_settings()` path and forbid module-scope creation of Mongo settings objects. As a lightweight guard, add a code comment on the `Settings` class stating it must not contain Mongo fields (those belong on `MongoSettings`), and add a simple test assertion that no field on `Settings` starts with `mongo_` |
| CI or local test runs silently use the wrong DB name | Keep the test harness responsible for forcing a safe non-`quiz` DB name before app construction, and also set `MONGO_DB_NAME=quiz_test` explicitly in `.github/workflows/ci.yml` |
| Removing `database.py` dotenv loading breaks local tests or the in-scope backfill script | Document and use explicit shell-based env bootstrap for local pytest and script execution rather than hidden application-side loading |
| Mixed import roots keep duplicate module objects alive | Normalize all relevant app imports (`main`, `database`, `routers`, `schemas`, `settings`, `models`, `services`, `logger_config`), keep `pytest.ini` aligned with the top-level import contract, and add a lightweight enforcement check so mixed roots do not drift back in. Note: `services` and `logger_config` already use consistent top-level imports with no mixed-import variants, but they are included in the enforcement list for completeness |
| Shared-client script breaks when `database.py` becomes async | Move `app/scripts/backfill_time_limits_and_spent.py` to its own local sync `MongoClient` first |
| Direct DB test helpers break after the runtime client becomes PyMongo Async | Move tests to a separate sync PyMongo admin/test client against the same configured DB before relying on PyMongo Async in app code |
| Some runtime or test code stays hard-coded to `.quiz` | Treat removal or isolation of every direct `.quiz` access as an explicit migration task across runtime code, tests, and the backfill script |
| Test harness bypasses lifespan startup/shutdown | Use context-managed `TestClient` and assert teardown closes the async app client |
| ECS service starts successfully even when MongoDB is unreachable | Run a fail-fast Mongo `ping` during lifespan startup so bad credentials, DNS, or network reachability stop startup immediately |
| Tests pollute each other locally through shared DB state | Use per-test cleanup with a shared class-level client/app context, and keep cleanup scoped to the configured test DB only |
| Fixture reads fail when tests are invoked from a different working directory | Normalize fixture loading to file-relative paths as part of the harness rewrite instead of depending on repo-root CWD |
| PyMongo-specific spy tests do not translate to the async runtime seam | Drop `test_batch_update_uses_aggregate_not_find_one` — the aggregate-over-find_one choice is an internal optimization locked in by the route code and does not need a driver-level test guard |
| Forms coverage is accidentally lost during harness migration | Keep the existing `/form/{form_id}` coverage explicit in verification and only relocate it if a follow-up cleanup is chosen intentionally |
| Runtime artifacts now include test-only packages | Document the decision explicitly until dependencies are split |
| Packaging or import cleanup accidentally changes deployment entrypoints | Preserve the current top-level module layout plus `main:app` export throughout the migration |
| Performance improvement is smaller than expected | Treat the benefit as a hypothesis and measure staging/load-test results rather than assuming a fixed multiplier |

---

## Done Criteria

- The exact async migration target is pinned to `pymongo==4.16.0`; this migration is not shipped on any version older than `4.15.1` (and must not use `pymongo==4.12.1`)
- Shared runtime Mongo access uses `pymongo.AsyncMongoClient` through the normalized database seam
- The normalized runtime seam is the top-level `database` module with `get_quiz_db()` plus shared `init_db()` / `close_db()` lifecycle helpers
- FastAPI app construction uses `create_app()` with `lifespan` context manager for PyMongo Async client initialization/shutdown
- `main.py` exports `app = create_app()` for the ECS deployment entrypoint
- `MONGO_DB_NAME` is implemented and used by both the async runtime client and sync test/admin client without import-time freezing, and test cleanup guards reject the default `quiz` DB
- `MONGO_DB_NAME` is the authoritative DB selector in runtime code, CI, ECS task definitions, Terraform examples, and docs; URI examples are no longer treated as the source of truth for DB selection
- Mongo configuration is owned by `app/settings.py` through a dedicated lazy Mongo settings/helper path, read only inside runtime/test helper functions, and no env-backed Mongo setting is frozen through module-scope `Settings()` objects
- `app/scripts/backfill_time_limits_and_spent.py` no longer depends on the shared runtime client
- Local pytest and in-scope script execution paths are documented with explicit env bootstrap commands instead of hidden dotenv loading inside application code
- Direct `.quiz` access has been removed from runtime code and isolated behind the planned sync admin/test helper or local script client everywhere else
- Affected tests pass with real MongoDB as the primary backend, a separate sync admin/test client for setup/assertion, and per-test cleanup for local isolation
- Fixture loading no longer depends on repo-root CWD
- All `BaseTestCase` / `SessionsBaseTestCase` consumers have been verified under the new harness
- `test_pydantic_v2_compat.py` has been migrated with the shared harness changes, and `test_pyobjectid.py` has been aligned with the canonical import strategy
- Focused route coverage exists for the migrated forms router, whether kept in `test_pydantic_v2_compat.py` or later relocated without coverage loss
- Full-suite verification includes `app/tests/test_scoring.py`
- The PyMongo-specific spy test (`test_batch_update_uses_aggregate_not_find_one`) has been dropped since the aggregate-over-find_one choice is an internal optimization that does not warrant a driver-level unit test guard
- Dependency choices are pinned and documented after the Python 3.12 compatibility spike selects the exact PyMongo Async and framework/test stack pins
- `.github/workflows/ci.yml` sets `MONGO_DB_NAME=quiz_test`, while the test harness still forces a safe DB name before app construction for non-CI runs
- A lightweight import-root enforcement check or equivalent explicit verification exists so banned mixed import pairs do not re-enter active code
- README/test instructions match the final setup, including Terraform-owned ECS runtime env configuration
- Deployment/runtime docs reflect ECS-only deployment, `.env.example` includes `MONGO_DB_NAME`, and `docs/ENV.md` documents `MONGO_AUTH_CREDENTIALS`, `MONGO_DB_NAME`, and optional pool-size overrides with concrete runtime/test examples while removing stale GitHub-repository-environments wording
- The plan and implementation explicitly state that legacy standalone maintenance scripts outside this migration may continue using hardcoded `quiz` until separate follow-up cleanup
- `docs/pymongo-async-staging-smoke.md` exists and contains the required DB-backed staging smoke checklist and cleanup steps
- Local Docker validation includes both image build success and a container-start `/health` smoke as manual validation steps for this migration
- Lifespan startup performs a fail-fast Mongo connectivity check before the service is considered up
- Required manual DB-backed staging validation has been completed for ECS with namespaced test data and cleanup
