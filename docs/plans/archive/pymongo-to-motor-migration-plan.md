# PyMongo Sync -> PyMongo Async Migration Plan

**Date:** 2026-04-01
**Goal:** Replace synchronous PyMongo with PyMongo Async (`pymongo.AsyncMongoClient`) in the FastAPI runtime so MongoDB calls stop blocking the event loop. Also: upgrade Python to 3.12, and remove all Lambda/SAM traces from the active code, config, and docs.
**Expected outcome:** Lower request blocking and better concurrency under load. The exact throughput gain is a staging-validation target, not a guaranteed 5-10x outcome, because this codebase still has read-before-write patterns and CPU-heavy scoring paths.

---

## Why This Matters

FastAPI is async, but the current MongoDB access path is synchronous. Every `find_one()` or `update_one()` blocks the worker while the database responds. PyMongo Async keeps the same MongoDB model but exposes awaitable operations so the app can yield control while I/O is in flight.

That said, PyMongo Async only removes the blocking I/O portion of the request path. It does not by itself remove extra reads, aggregation cost, or CPU-bound scoring work already identified elsewhere in the repo. This migration should therefore be treated as a meaningful concurrency improvement whose real impact must be measured after rollout.

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

- **Python upgrade**
  - Upgrade from Python 3.9 to Python 3.12 across Dockerfile, CI, and dependencies

- **Lambda/SAM removal**
  - Remove all Lambda, SAM, and Mangum traces — the project has fully moved to ECS

### Out of scope for this migration

- Standalone maintenance scripts that already create their own local sync `MongoClient`
- Broader performance work outside the Mongo driver swap
- Reorganizing the repo into separate runtime/test dependency files unless explicitly chosen as follow-up work

### Explicit no-change item

- `app/scripts/add_marking_scheme_to_questions_without_details.py`
  - Remains synchronous and independent because it does not use the shared app client.

---

## Pre-Phase A: Remove Lambda/SAM/Mangum

The project has fully migrated to ECS Fargate. User confirmation on 2026-04-07 says Lambda/SAM is no longer in use and cutover to ECS-based infra is complete. All Lambda and SAM traces should be removed before the async MongoDB migration to simplify the codebase and avoid carrying dead code through every subsequent phase.

### Files to delete

| File | What it is |
|------|-----------|
| `templates/staging.yaml` | SAM CloudFormation template for Lambda staging |
| `templates/prod.yaml` | SAM CloudFormation template for Lambda production |
| `.github/workflows/deploy_to_staging.yml` | GitHub Actions workflow for SAM deploy to staging |
| `.github/workflows/deploy_to_prod.yml` | GitHub Actions workflow for SAM deploy to prod via Lambda |

> If the `templates/` directory is empty after deletion, remove the directory too.

### Files to modify

| File | Lines/sections | What to change |
|------|---------------|----------------|
| `app/main.py` | Line 5: `from mangum import Mangum` | Remove import |
| `app/main.py` | Line 79: `handler = Mangum(app)` | Remove handler export |
| `app/requirements.txt` | Line 6: `mangum==0.14.1` | Remove dependency |
| `.dockerignore` | Lines 40-43: SAM exclusions block | Remove the `# AWS SAM (Lambda)`, `templates/`, `.aws-sam/`, `samconfig.toml` lines |
| `.gitignore` | Line 35: `.aws-sam` | Remove (SAM artifact) |
| `.gitignore` | Lines 153-154: `#Zappa` comment + `*backend*json` | Remove (dead Zappa artifacts, not SAM) |
| `.gitignore` | Line 121: `zappa_env/` | Remove (dead Zappa virtualenv artifact) |
| `.gitignore` | Line 160: `zappa_settings.json` | Remove (dead Zappa artifact) |
| `.gitignore` | Line 162: `templates/staging-test.yaml` | Remove (SAM template reference) |
| `.pre-commit-config.yaml` | `check-yaml` hook `exclude: "templates/*"` | Remove stale template exclusion |
| `.pre-commit-config.yaml` | `cfn-python-lint` hook for `templates/.*` | Remove CloudFormation lint hook if no other templates remain |
| `.github/workflows/deploy_ecs_testing.yml` | Temporary push trigger for `docs/migration-lambda-to-ecs` | Remove or explicitly re-justify the stale ECS-migration branch trigger |
| `.github/workflows/deploy_ecs_prod.yml` | Temporary push trigger for `docs/migration-lambda-to-ecs` | Remove or explicitly re-justify the stale ECS-migration branch trigger |
| `app/database.py` | Lambda compatibility comment in connection-pool section | Rewrite as ECS-only connection-pool guidance |
| `app/logger_config.py` | Lambda logging StackOverflow comment | Remove or replace with non-Lambda logging rationale |
| `CLAUDE.md` | Line 7: mentions "AWS Lambda (staging)" | Update to ECS-only |
| `CLAUDE.md` | Line 45: references `templates/` as SAM templates | Remove line |
| `CLAUDE.md` | Lines 113-114: Lambda/Mangum deployment section | Remove Lambda subsection |
| `CLAUDE.md` | CI/CD section referencing `deploy_to_staging.yml` and `deploy_to_prod.yml` | Remove those workflow references |
| `README.md` | Lambda deployment section (~lines 240-283) | Remove Lambda/SAM sections, keep ECS-only, and replace Lambda-specific logging text with current ECS observability guidance or an explicit deferred-owner note |
| `context_for_ai/project-context.md` | Multiple Lambda/SAM references spread across the file | Remove all Lambda/SAM references (this file will need broader rewriting after the full migration in Phase 6) |

### Historical-doc decision

Archived/historical docs under archive directories should be treated as historical records and are exempt from destructive rewriting unless they are referenced as current operational guidance. Treat `context_for_ai/plans/` the same way: it is historical planning context unless a current operational document links to it as active guidance. Active docs and current developer guidance must be ECS-only.

### Validation after cleanup

- Run a post-cleanup grep to confirm active docs/config no longer reference Lambda/SAM/Mangum:

```bash
rg "deploy_to_staging|deploy_to_prod|SAM|Mangum|AWS Lambda" . -g '!docs/plans/archive/**' -g '!context_for_ai/plans/**'
```

- If `.pre-commit-config.yaml` drops the CloudFormation hook, also update `context_for_ai/project-context.md` so its tooling/docs section no longer claims CloudFormation linting is part of the active workflow.
- If `context_for_ai/plans/` is later linked from active developer docs, reclassify the specific file and clean it up instead of relying on the historical-doc exemption.

### What this unblocks

- Later phases no longer need to consider Mangum lifecycle, Lambda warm-start behavior, or `sam build` packaging
- `main.py` becomes simpler — just a FastAPI app, no dual export
- The migration plan itself can drop all Lambda-specific caveats

---

## Pre-Phase B: Upgrade Python from 3.9 to 3.12

### Why 3.12 (not 3.13)

Python 3.12 is well-established with broad package ecosystem support. Python 3.13 is available but some packages (especially older pinned versions) may not have wheels yet. 3.12 is the safe, modern target.

### Current Python version references

| File | Current | Change to |
|------|---------|-----------|
| `Dockerfile` (line 2) | `python:3.9-slim` | `python:3.12-slim` |
| `.github/workflows/ci.yml` (line 31) | `python-version: '3.9'` (unit tests) | `'3.12'` |
| `.github/workflows/ci.yml` (line 17) | `python-version: '3.11'` (pre-commit) | `'3.12'` (align everything) |

> The SAM templates also reference `python3.9` but those are deleted in Pre-Phase A.

### CI workflow modernization references

The Python 3.12 step should also validate or update old GitHub Actions versions while the CI workflow is being touched.

| File | Current | Change to |
|------|---------|-----------|
| `.github/workflows/ci.yml` | `actions/checkout@v3` and `actions/checkout@v2` | Prefer one supported current major across jobs |
| `.github/workflows/ci.yml` | `actions/setup-python@v3` and `actions/setup-python@v2` | Prefer one supported current major with Python 3.12 |
| `.github/workflows/ci.yml` | `codecov/codecov-action@v2` | Upgrade to a supported current major or explicitly validate support before keeping it |

### Compatibility matrix gate before final pin edits

Pre-Phase B should not start with a blind requirements rewrite. It should start by selecting a coherent candidate matrix for:

- Python 3.12
- FastAPI / Starlette / httpx / TestClient
- Pydantic v2 + `pydantic-settings`
- PyMongo with `AsyncMongoClient`
- Uvicorn / pytest / pytest-cov / requests / support libraries

That candidate matrix should then be validated in a short throwaway spike before the pins in `app/requirements.txt`, Docker, and CI are treated as final. Record the chosen exact versions in this plan or in a linked implementation note before mass edits begin.

### Dependency upgrades required

The current dependency pins are from 2021-2022 and several are not tested against Python 3.12. These need version bumps:

| Package | Current | Concern | Action |
|---------|---------|---------|--------|
| `fastapi` | 0.75.0 | Old, pre-3.12 era | Select and record one exact tested Python 3.12-compatible pin. Note: newer FastAPI requires Pydantic v2 |
| `pydantic` | 1.9.0 | Pydantic v1 has known issues on 3.12+ | Select and record one exact tested Pydantic v2 pin. **This is the biggest change** — model syntax differs between v1 and v2 |
| `pydantic-settings` | Not present | Required by Pydantic v2 `BaseSettings` | Add one exact tested pin |
| `uvicorn` | 0.17.6 | Old | Select and record one exact tested pin |
| `pymongo` | 4.0.2 | Old and must provide `AsyncMongoClient` | Select and record one exact tested PyMongo 4.x pin that supports PyMongo Async |
| `dnspython` | 2.2.1 | Old | Select and record one exact tested pin |
| `python-dotenv` | 0.20.0 | Old | Select and record one exact tested pin |
| `httpx` | Not present | Modern Starlette/FastAPI `TestClient` dependency | Add one exact tested pin |
| `mongoengine` | 0.24.1 | Test-only, old, no-op for app DB access | Remove in Phase 5 |
| `mongomock` | 4.0.0 | Test-only, no-op for app DB access | Remove in Phase 5 |
| `pytest` | 7.1.2 | Old | Select and record one exact tested pin |
| `pytest-cov` | Installed unpinned in CI | Unpinned CI drift risk | Add one exact tested pin or remove the separate CI install |
| `requests` | 2.27.1 | Old | Select and record one exact tested pin |

### Pydantic v1 -> v2 migration (the hard part)

This is the most impactful sub-task of the Python upgrade. Pydantic v2 changes:
- `BaseModel` field definitions: `Field(...)` syntax changes, `Optional` handling differs
- `validator` → `field_validator`, `root_validator` → `model_validator`
- `.dict()` → `.model_dump()`, `.json()` → `.model_dump_json()`
- schema generation APIs such as `schema()` / `json_schema()` → `.model_json_schema()`
- `orm_mode = True` → `from_attributes = True` in `model_config`
- `class Config` inner classes → `model_config = ConfigDict(...)`
- `BaseSettings` moved from `pydantic` to separate `pydantic-settings` package
- Custom types using `__get_validators__()` / `__modify_schema__()` must be rewritten

#### File-by-file Pydantic v2 migration breakdown

##### `app/settings.py` — 1 change (will crash at import if missed)

| Line | Current | Change |
|------|---------|--------|
| 1 | `from pydantic import BaseSettings` | `from pydantic_settings import BaseSettings` |

> **Dependency:** Add `pydantic-settings` to `app/requirements.txt`. In Pydantic v2, `BaseSettings` was moved to a separate package.

##### `app/schemas.py` — `PyObjectId` custom type rewrite (HIGH complexity)

The `PyObjectId` class (lines 5-18) uses two methods removed in Pydantic v2:

| Method | Current (v1) | Replacement (v2) |
|--------|-------------|-------------------|
| `__get_validators__()` | Yields `cls.validate` | Replace with `__get_pydantic_core_schema__(cls, source_type, handler)` using `pydantic_core.core_schema` |
| `__modify_schema__()` | `field_schema.update(type="string")` | Replace with `__get_pydantic_json_schema__(cls, schema, handler)` |

This requires importing `pydantic_core.core_schema` and using `core_schema.no_info_plain_validator_function()` or similar. This is the most non-trivial single change in the migration.

##### `app/models.py` — 13 `class Config` blocks across 13 models

All `class Config` inner classes must be converted to `model_config = ConfigDict(...)`.

| Pattern | Count | Models affected | v1 syntax | v2 syntax |
|---------|-------|-----------------|-----------|-----------|
| `class Config` blocks | 13 | Organization, OrganizationResponse, Question, QuestionResponse, Quiz, GetQuizResponse, CreateQuizResponse, SessionAnswer, UpdateSessionAnswer, Session, UpdateSession, SessionResponse, UpdateSessionResponse | `class Config:` inner class | `model_config = ConfigDict(...)` |
| `json_encoders = {ObjectId: str}` | 5 | Organization, Question, Quiz, SessionAnswer, Session | `json_encoders` in Config | Replace with a reusable `PyObjectId`-level serialization strategy (preferred), or prove via explicit audit/tests that every inherited and nested `PyObjectId` field serializes correctly |
| `allow_population_by_field_name` | 6 | Organization, OrganizationResponse, Question, Quiz, SessionAnswer, Session | `allow_population_by_field_name = True` | `populate_by_name=True` in `ConfigDict` |
| `schema_extra` | 13 | All 13 models with Config | `schema_extra = {...}` | `json_schema_extra={...}` in `ConfigDict` |
| `arbitrary_types_allowed` | 6 | Organization, OrganizationResponse, Question, Quiz, SessionAnswer, Session | `arbitrary_types_allowed = True` | `arbitrary_types_allowed=True` in `ConfigDict` |

> **New import needed** at top of `models.py`: `from pydantic import ConfigDict`

The selected ObjectId serialization strategy must cover every `PyObjectId` field, not only the five models that currently define `json_encoders`. This explicitly includes nested `QuestionSet.id` at `app/models.py:217`, which currently has no `Config` block, plus inherited response-model IDs.

##### `app/models.py` — Optional/default inventory for Pydantic v2

In Pydantic v2, `Optional[T]` without a default is still required. The implementation must decide whether each field is logically optional or required, and must add `= None` where omitted input should remain valid.

| Model / field(s) | Current location | Planned defaulting strategy |
|------------------|------------------|-----------------------------|
| `QuestionSetMetric.num_marked_for_review` | `app/models.py:85` | Add `= None`; non-assessment metrics may omit it |
| `SessionMetrics.total_marked_for_review` | `app/models.py:97` | Add `= None`; non-assessment metrics may omit it |
| `QuestionMetadata.grade`, `subject`, `chapter`, `chapter_id`, `topic`, `topic_id`, `competency`, `difficulty`, `skill`, `skill_id`, `concept`, `concept_id`, `priority` | `app/models.py:102-114` | Add `= None` unless endpoint contracts intentionally require metadata keys |
| `QuizMetadata.test_format`, `grade`, `subject`, `chapter`, `topic`, `source`, `source_id`, `session_end_time`, `next_step_url`, `next_step_text`, `single_page_header_text` | `app/models.py:119-130` | Add `= None` for fields that may be omitted; keep `next_step_autostart = False` |
| `Quiz.title` | `app/models.py:235` | Decide contract explicitly; add `= None` only if title may be omitted |
| `UpdateSessionAnswer.answer`, `visited`, `time_spent`, `marked_for_review` | `app/models.py:429-432` | Add `= None` to all four PATCH fields so omitted PATCH fields are valid and existing empty-payload checks still run |
| `UpdateSession.metrics` | `app/models.py:493` | Make it `Optional[SessionMetrics] = None`; event-only updates are already part of the supported contract |
| `UpdateSessionResponse.time_remaining` | `app/models.py:537` | Add `= None` if responses may omit time remaining |

##### `app/models.py` — non-Optional fields currently defaulting to `None`

These fields need an explicit contract decision during the Pydantic v2 rewrite because omitted values and explicit `null` can diverge from current behavior.

| Model / field(s) | Current location | Planned decision |
|------------------|------------------|------------------|
| `MarkingScheme.partial` | `app/models.py:62` | Convert to `Optional[List[PartialMarkRule]] = None` unless the API should require the key |
| `Question.marking_scheme` | `app/models.py:148` | Convert to `Optional[MarkingScheme] = None` unless the API should require the key |
| `Question.metadata` | `app/models.py:150` | Convert to `Optional[QuestionMetadata] = None` unless the API should require the key |
| `QuestionSet.marking_scheme` | `app/models.py:222` | Convert to `Optional[MarkingScheme] = None` unless the API should require the key |
| `Quiz.metadata` | `app/models.py:249` | Convert to `Optional[QuizMetadata] = None` unless the API should require the key |
| `SessionAnswer.time_spent` | `app/models.py:412` | Convert to `Optional[int] = None` unless the API should reject `null` and omitted values |

##### `app/models.py` — mutable default cleanup while touching the models

| Model / field(s) | Current location | Planned change |
|------------------|------------------|----------------|
| `Question.options` | `app/models.py:141` | Replace `=[]` with `Field(default_factory=list)` if empty-list default remains correct |
| `Question.solution` | `app/models.py:149` | Replace `=[]` with `Field(default_factory=list)` if empty-list default remains correct |
| `Session.events` | `app/models.py:462` | Replace `=[]` with `Field(default_factory=list)` |
| `Session.question_order` | `app/models.py:472-474` | Replace `=[]` with `Field(default_factory=list)` |

Add focused tests for PATCH/update/null behavior, especially `UpdateSessionAnswer` payloads such as `{"visited": true}`, `{"answer": [...]}`, `{}`, `{"answer": null}`, and `{"time_spent": null}`. The empty payload should still be handled by the endpoint's explicit validation path rather than failing model construction unexpectedly. Preserve the current two-dump merge semantics in `remove_optional_unset_args()` unless the implementation intentionally changes the API contract and documents that change.

##### `app/utils.py` — 2 `.dict()` calls (line 29)

| Current | Change |
|---------|--------|
| `model.dict(exclude_unset=True)` | `model.model_dump(exclude_unset=True)` |
| `model.dict(exclude_none=True)` | `model.model_dump(exclude_none=True)` |

> This file is called from `app/routers/session_answers.py` (lines 125 and 183) — critical runtime paths.

Keep the current behavior that merges `exclude_unset=True` and `exclude_none=True` results unless the migration explicitly decides to change PATCH semantics for explicit `null`.

##### `app/routers/sessions.py` — 3 `.parse_obj()` calls

| Line | Current | Change |
|------|---------|--------|
| 192 | `SessionAnswer.parse_obj(...)` | `SessionAnswer.model_validate(...)` |
| 283 | `SessionAnswer.parse_obj(...)` | `SessionAnswer.model_validate(...)` |
| 350 | `Event.parse_obj(...)` | `Event.model_validate(...)` |

##### `app/routers/session_answers.py` — 2 `__fields_set__` usages

| Line | Current | Change |
|------|---------|--------|
| 65 | `session_answer.__fields_set__` | `session_answer.model_fields_set` |
| 166 | `session_answer.__fields_set__` | `session_answer.model_fields_set` |

> `__fields_set__` still works in v2 but is deprecated. The new name is `model_fields_set`.

### Upgrade strategy

1. Select a candidate exact-version compatibility matrix for Python 3.12, FastAPI/Starlette/httpx/TestClient, Pydantic v2, PyMongo Async, Uvicorn, pytest, pytest-cov, requests, and support libraries
   - Record the candidate exact versions in this plan or a linked implementation note before mass edits
   - Treat this as a gate for the rest of Pre-Phase B, not a later optional clean-up
2. Run a throwaway migration spike with that candidate matrix before finalizing dependency edits
   - Validate `AsyncMongoClient`, one DB-backed route through `get_quiz_db()`, `create_app()` + lifespan-managed `TestClient`, `MONGO_DB_NAME` selection, and one PATCH-style Pydantic v2 path
   - If the spike fails, revise the matrix before touching the broader codebase
3. Bump all dependencies to the selected Python 3.12-compatible exact pins in `requirements.txt` (including adding `pydantic-settings`)
   - Use exact tested pins for the whole stack, not `latest`, `>=`, or other open-ended ranges
   - Add and pin `httpx` for the modern Starlette/FastAPI `TestClient`
   - Add or pin `pytest-cov`, and update CI so it does not install unpinned `pytest pytest-cov`
4. Migrate Pydantic v1 → v2 across all affected files (see detailed breakdown above):
   - `app/schemas.py` — rewrite `PyObjectId` custom type (highest complexity)
   - `app/models.py` — convert all 13 `class Config` blocks to `model_config = ConfigDict(...)`
   - `app/models.py` — add defaults for Pydantic v2 Optional fields where omission is valid, convert nullable non-Optional fields deliberately, and fix mutable list defaults
   - `app/settings.py` — change `BaseSettings` import to `pydantic_settings`
   - `app/utils.py` — change `.dict()` to `.model_dump()`
   - `app/routers/sessions.py` — change `.parse_obj()` to `.model_validate()`
   - `app/routers/session_answers.py` — change `__fields_set__` to `model_fields_set`
5. Update `Dockerfile` base image to `python:3.12-slim`
6. Update CI workflow Python versions and old workflow action majors together
   - Prefer supported current majors for `actions/checkout`, `actions/setup-python`, and Codecov while the CI workflow is already being edited
   - If any action version is intentionally kept, explicitly validate and document Python 3.12 support
7. Run full test suite, including `app/tests/test_scoring.py`, and fix any breakage
8. Do a local Docker build and a local container-start smoke test
   - Start the built image with required env vars
   - Confirm `uvicorn main:app` imports successfully
   - Hit `/health` to prove import/startup success independent of DB-backed smoke validation

### What this unblocks

- Current PyMongo Async support works best with a modern Python and PyMongo stack
- Modern FastAPI + Pydantic v2 is significantly faster
- Establishes Python 3.12 as the new target baseline for Docker, CI, and the async MongoDB migration

---

## Phase 0: Normalize the Database Access Seam

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

## Phase 1: Compatibility Matrix and Dependency Strategy

**File:** `app/requirements.txt`

This phase starts during Pre-Phase B and must be completed before the Python/dependency edits are considered final. It is described separately here so the chosen version matrix and spike expectations remain explicit throughout implementation.

### Dependency decisions

- Keep `pymongo` as a direct dependency.
  - It provides both the async runtime client (`AsyncMongoClient`) and the sync APIs still needed by support/test code.
  - Examples include sync script support (`UpdateOne`, `bulk_write` patterns), the separate sync test/admin client, and `pymongo.DESCENDING`.

- Do **not** add `motor` for this migration.
  - MongoDB-maintained guidance now points new async Python migrations to PyMongo Async.
  - If the team later wants Motor anyway, that should be a separate explicit risk-acceptance decision.

- Before the broader code migration starts, select one exact `pymongo` version that is compatible with Python 3.12, includes `AsyncMongoClient`, and works in the current deployment/runtime setup. Validate it with the migration spike below, then record the exact pin in `app/requirements.txt`.

- Record the selected exact stack versions in this plan or in a linked implementation note before broad file edits begin.

- Do **not** make a mock async Mongo backend the default backend for this migration.
  - The existing suite remains primarily real-Mongo integration testing.
  - Mock async Mongo libraries can be evaluated later for small focused unit tests, but they are not required to complete this migration.

- Do **not** use open-ended version ranges in this repo's only requirements file.
  - The implementation should pin the exact tested versions for the whole upgraded stack selected in the compatibility step above, including FastAPI, Pydantic, PyMongo, Uvicorn, httpx, pytest, pytest-cov, requests, and support libraries.
  - The plan should not rely on `>=` ranges because there is no separate lockfile or constraints file here.

- Update `.github/workflows/ci.yml` so it does not install unpinned `pytest pytest-cov` after `app/requirements.txt`.
  - Preferred: add exact `pytest` and `pytest-cov` pins to `app/requirements.txt` and remove the separate `pip install pytest pytest-cov` command.
  - Acceptable fallback: keep the separate install only if it uses the exact same tested pins.

- While the CI workflow is being updated for Python 3.12, also update or explicitly validate the action versions used by checkout, setup-python, and Codecov.

- Remove `mongoengine` and `mongomock` early in Phase 5 (test redesign).
  - These packages are confirmed no-ops: the app never uses `mongoengine` for data access, and the `mongoengine.connect("mongoenginetest", host="mongomock://...")` call in `base.py` doesn't affect test outcomes (tests run against real MongoDB via `database.client`).
  - Keeping them adds confusion and may lead implementers to waste time understanding non-existent interactions with the async runtime client.

### Migration spike before mass edits

Before broad router/test rewrites, do a short spike that validates the risky integration points together:

- Python 3.12 environment with exact candidate dependency pins
- `pymongo.AsyncMongoClient` creation, one async `find_one`/`insert_one`, and client close behavior
- `MONGO_DB_NAME` selection shared by async runtime code and the sync test/admin client
- One Pydantic v2 model path, including omitted-field and explicit-`null` PATCH-style payloads for `UpdateSessionAnswer`
- `create_app()` plus lifespan-managed startup/teardown under context-managed `TestClient`
- One DB-backed route using the new `get_quiz_db()` seam

Use the spike result to finalize exact dependency pins and implementation patterns before mass edits. If the team skips this spike, the implementation notes must explicitly record why.

### Runtime artifact note

This repo currently uses one shared `requirements.txt` for local installs, Docker, and deployment packaging. Every entry added to that file will also be present in runtime artifacts.

**Planned default:** keep the single-file approach for now, use exact pins, and document any test-only overlap explicitly. Splitting runtime and test dependencies can be handled later as a separate cleanup if desired.

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

> **Note:** Line numbers below are as of the current commit and should be re-verified before execution, especially if Pre-Phase B's Pydantic v2 changes (e.g., `.parse_obj()` → `.model_validate()` in `sessions.py`) shift router file line numbers.

### File-by-file runtime changes

#### `routers/session_answers.py` — 5 calls

| Line | Current | Change |
|------|---------|--------|
| 92 | `list(client.quiz.sessions.aggregate(pipeline))` | `await db.sessions.aggregate(pipeline).to_list(length=None)` |
| 137 | `client.quiz.sessions.update_one(...)` | Add `await` |
| 187 | `client.quiz.sessions.find_one(...)` | Add `await` |
| 231 | `client.quiz.sessions.update_one(...)` | Add `await` |
| 267 | `list(client.quiz.sessions.aggregate(pipeline))` | `await db.sessions.aggregate(pipeline).to_list(length=None)` |

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

**Special case:** `update_quiz_for_backwards_compatibility` must become `async def`, and its call site must use `await`.

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

### `import pymongo` usage

`sessions.py` currently imports `pymongo` for `pymongo.DESCENDING`. Keeping `pymongo` installed remains valid and intentional after the runtime migration.

---

## Phase 5: Redesign the Test Strategy for PyMongo Async

### Current state to describe accurately

- Tests currently call `mongoengine.connect(..., host=\"mongomock://...\")`.
- The application under test does **not** use `mongoengine` for its runtime database access.
- The app talks directly to `database.client`, so the future PyMongo Async test setup is a design change, not a drop-in replacement of one mock package with another.

### Planned test strategy

1. **Continue using real MongoDB as the primary backend for the existing test suite**
   - The current suite already runs as integration-style testing against a real MongoDB service in CI (not mongomock, despite the `CLAUDE.md` claim — see Phase 6 docs note).
   - Do not switch the whole suite to a mock async Mongo backend as part of this migration.

2. **Remove `mongoengine` and `mongomock` as one of the first steps in this phase**
   - These are confirmed no-ops: the `mongoengine.connect(...)` in `base.py` doesn't affect any test outcomes.
   - Remove both packages from `requirements.txt` and remove the `mongoengine.connect(...)` / `mongoengine.disconnect()` calls from `base.py`.

3. **Use the canonical database seam from Phase 0**
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
   - If a call-level assertion is still necessary, patch only a narrow seam owned by the app (for example the accessor/collection seam introduced in Phase 0).
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
  - Replace the old Lambda Promtail/Loki section with the current ECS logging/observability source of truth, or add an explicit deferred-doc note with owner/runbook placeholder instead of silently deleting the guidance

- Update deployment/runtime documentation
  - Document that deployment is ECS-only (Lambda has been removed)
  - Document `MONGO_DB_NAME` in `docs/ENV.md`, including runtime default and safe test override
  - Document `MONGO_MAX_POOL_SIZE` and `MONGO_MIN_POOL_SIZE` in `docs/ENV.md` as optional overrides with defaults matching current behavior

- Update rollout validation notes
  - Document that `/health` is not a DB-backed smoke check
  - Document DB-backed staging smoke validation as a required manual migration runbook step for now, separate from CI/CD liveness checks
  - Include test-data namespacing and cleanup expectations for create organization, create quiz, create session, and submit/update session answer flows

- Update `CLAUDE.md`
  - Correct "Tests use mongomock" — tests actually run against real MongoDB in CI
  - Update testing section to reflect the new PyMongo Async test bootstrap

- Update any developer notes affected by the chosen database seam, app factory, or test bootstrap strategy
  - Treat `context_for_ai/plans/` as historical planning context unless a file there is still linked from active docs
  - After the cleanup, run the active-doc grep from Pre-Phase A and resolve any remaining hits outside explicitly historical paths

- Keep this migration plan document aligned with the final implementation choices

### Done criteria for docs

- A developer can read the README and run the intended test flow without reverse-engineering the new harness
- A developer can read the README and understand the ECS-only deployment path plus DB-backed smoke expectations
- Active docs/config pass the Lambda/SAM/Mangum validation grep outside explicitly historical paths
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

1. **Remove Lambda/SAM/Mangum (Pre-Phase A)**
   - Delete SAM templates, Lambda deploy workflows
   - Remove Mangum from `main.py` and `requirements.txt`
   - Clean up docs, `.gitignore`, `.dockerignore`, stale ECS migration branch triggers, and active-doc references
   - Verify ECS deploys still work after cleanup

2. **Upgrade Python to 3.12 (Pre-Phase B)**
   - Run the Phase 1 compatibility-matrix selection and throwaway spike first
   - Record the selected exact versions in the plan or a linked implementation note
   - Bump all dependencies to exact tested Python 3.12-compatible pins
   - Migrate Pydantic v1 → v2 in `models.py`, `schemas.py`, `settings.py`, `utils.py`, and affected router files (see detailed breakdown in Pre-Phase B)
   - Update Dockerfile and CI workflow Python/action versions
   - Run full test suite, fix breakage
   - Docker build verification plus local container-start `/health` smoke

3. **Normalize the database access seam (Phase 0)**
   - Standardize app module imports, not only database imports
   - Introduce `get_quiz_db()`, `init_db()`, and `close_db()` in the top-level `database` module
   - Add `create_app()`, keep `app = create_app()` in `main.py`, and move test app construction after seam configuration with delayed `main` import in the harness

4. **Handle shared-client consumers outside routers (Phase 2)**
   - Move `app/scripts/backfill_time_limits_and_spent.py` to its own local sync client

5. **Migrate runtime code in one coherent pass (Phase 3 + 4)**
   - Update `database.py` to use `pymongo.AsyncMongoClient`
   - Add `MONGO_DB_NAME` handling for runtime and tests without import-time freezing
   - Update the 6 router files
   - Introduce `lifespan` context manager for PyMongo Async client creation and shutdown

6. **Migrate affected tests (Phase 5)**
   - Update `app/tests/base.py`
   - Use a context-managed `TestClient` so lifespan startup/shutdown runs
   - Introduce the separate sync admin/test client and shared `self.db`-style helper
   - Apply the per-test cleanup policy with the `quiz`-DB safety guard
   - Update all `BaseTestCase` / `SessionsBaseTestCase` consumers as needed
   - Rewrite the PyMongo-specific spy test
   - Add focused `forms` route coverage

7. **Update documentation (Phase 6)**
   - README, deployment/runtime notes, and rollout validation notes

8. **Run verification and rollout validation (Phase 7)**
   - Focused local/CI validation first, including Docker build packaging checks
   - Then DB-backed staging checks for ECS
   - Then any load/performance comparison work

This order is designed to avoid a broken middle state. Lambda cleanup and Python upgrade come first so the rest of the migration works against a clean, modern baseline.

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Pydantic v1 → v2 migration breaks request/response models | Migrate models carefully, run full test suite after each file. Use Pydantic's migration guide |
| Pydantic v2 changes omitted or explicit-`null` request semantics | Add explicit defaults for optional/update fields, convert nullable non-Optional fields deliberately, and add focused tests for omitted and explicit-`null` PATCH fields |
| Dependency upgrades introduce breaking changes | Upgrade and test incrementally, not all at once |
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

- All Lambda/SAM/Mangum traces removed from the codebase
- Python upgraded to 3.12 with all dependencies at exact tested compatible pins chosen from a recorded compatibility matrix/spike
- Pydantic v2 migration complete in `models.py`, `schemas.py`, `settings.py`, `utils.py`, and affected router files
- Pydantic v2 Optional/default behavior is explicitly handled for update/PATCH models, nullable non-Optional fields, and mutable list defaults, and verified with tests
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
- Dependency choices are pinned and documented after a Python 3.12 compatibility spike selects the exact PyMongo Async and framework/test stack pins
- README/test instructions match the final setup, including ECS logging/observability guidance or an explicit deferred-doc pointer
- Deployment/runtime docs reflect ECS-only deployment and `docs/ENV.md` documents `MONGO_DB_NAME` plus optional pool-size overrides
- Active docs/config pass the Lambda/SAM/Mangum cleanup validation grep outside explicitly historical paths
- Local Docker validation includes both image build success and a container-start `/health` smoke
- Required manual DB-backed staging validation has been completed for ECS with namespaced test data and cleanup
