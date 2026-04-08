# Python 3.12 Upgrade + Lambda Cleanup Plan

**Date:** 2026-04-01
**Goal:** Remove all Lambda/SAM/Mangum traces from the codebase, upgrade Python from 3.9 to 3.12, and migrate from Pydantic v1 to Pydantic v2. This establishes a clean, modern baseline before the async MongoDB migration.
**Expected outcome:** A simplified codebase with no dead Lambda code, running on Python 3.12 with modern dependency pins and Pydantic v2 models. This is a prerequisite for the PyMongo Async migration that follows.

---

## Why This Matters

The project has fully migrated to ECS Fargate, but the codebase still carries Lambda/SAM/Mangum traces that add confusion and maintenance burden. Removing them simplifies every subsequent change.

Python 3.9 is approaching end-of-life, and the current dependency pins (from 2021-2022) are old enough that they block adoption of PyMongo Async and other modern libraries. Pydantic v1 has known issues on Python 3.12+, so the v1-to-v2 migration must happen as part of this upgrade. Getting all of this done in one PR creates a clean foundation for the async MongoDB migration.

---

## Scope

### In scope

- **Lambda/SAM removal**
  - Remove all Lambda, SAM, and Mangum traces -- the project has fully moved to ECS

- **Python upgrade**
  - Upgrade from Python 3.9 to Python 3.12 across Dockerfile, CI, and dependencies

- **Dependency upgrades**
  - Bump all dependencies to exact tested Python 3.12-compatible pins
  - Add `pydantic-settings`, `httpx`
  - Pin `pytest`, `pytest-cov`

- **Pydantic v1 to v2 migration**
  - `app/schemas.py` -- rewrite `PyObjectId` custom type
  - `app/models.py` -- convert all 13 `class Config` blocks, handle Optional/default changes, fix mutable defaults
  - `app/settings.py` -- `BaseSettings` import change
  - `app/utils.py` -- `.dict()` to `.model_dump()`
  - `app/routers/sessions.py` -- `.parse_obj()` to `.model_validate()`
  - `app/routers/session_answers.py` -- `__fields_set__` to `model_fields_set`

- **Dependencies and docs**
  - `app/requirements.txt`
  - Dockerfile, CI workflows

- **Compatibility matrix / migration spike**
  - Select and validate a coherent dependency matrix before mass edits

### Out of scope for this PR

- PyMongo Async migration (covered in `pymongo-async-migration-plan.md`)
- Database access seam normalization (covered in `pymongo-async-migration-plan.md`)
- Test harness redesign (covered in `pymongo-async-migration-plan.md`)
- Standalone maintenance scripts that already create their own local sync `MongoClient`
- Broader performance work outside the dependency upgrades

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
- `main.py` becomes simpler -- just a FastAPI app, no dual export
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
| `pydantic` | 1.9.0 | Pydantic v1 has known issues on 3.12+ | Select and record one exact tested Pydantic v2 pin. **This is the biggest change** -- model syntax differs between v1 and v2 |
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
- `validator` -> `field_validator`, `root_validator` -> `model_validator`
- `.dict()` -> `.model_dump()`, `.json()` -> `.model_dump_json()`
- schema generation APIs such as `schema()` / `json_schema()` -> `.model_json_schema()`
- `orm_mode = True` -> `from_attributes = True` in `model_config`
- `class Config` inner classes -> `model_config = ConfigDict(...)`
- `BaseSettings` moved from `pydantic` to separate `pydantic-settings` package
- Custom types using `__get_validators__()` / `__modify_schema__()` must be rewritten

#### File-by-file Pydantic v2 migration breakdown

##### `app/settings.py` -- 1 change (will crash at import if missed)

| Line | Current | Change |
|------|---------|--------|
| 1 | `from pydantic import BaseSettings` | `from pydantic_settings import BaseSettings` |

> **Dependency:** Add `pydantic-settings` to `app/requirements.txt`. In Pydantic v2, `BaseSettings` was moved to a separate package.

##### `app/schemas.py` -- `PyObjectId` custom type rewrite (HIGH complexity)

The `PyObjectId` class (lines 5-18) uses two methods removed in Pydantic v2:

| Method | Current (v1) | Replacement (v2) |
|--------|-------------|-------------------|
| `__get_validators__()` | Yields `cls.validate` | Replace with `__get_pydantic_core_schema__(cls, source_type, handler)` using `pydantic_core.core_schema` |
| `__modify_schema__()` | `field_schema.update(type="string")` | Replace with `__get_pydantic_json_schema__(cls, schema, handler)` |

This requires importing `pydantic_core.core_schema` and using `core_schema.no_info_plain_validator_function()` or similar. This is the most non-trivial single change in the migration.

##### `app/models.py` -- 13 `class Config` blocks across 13 models

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

##### `app/models.py` -- Optional/default inventory for Pydantic v2

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

##### `app/models.py` -- non-Optional fields currently defaulting to `None`

These fields need an explicit contract decision during the Pydantic v2 rewrite because omitted values and explicit `null` can diverge from current behavior.

| Model / field(s) | Current location | Planned decision |
|------------------|------------------|------------------|
| `MarkingScheme.partial` | `app/models.py:62` | Convert to `Optional[List[PartialMarkRule]] = None` unless the API should require the key |
| `Question.marking_scheme` | `app/models.py:148` | Convert to `Optional[MarkingScheme] = None` unless the API should require the key |
| `Question.metadata` | `app/models.py:150` | Convert to `Optional[QuestionMetadata] = None` unless the API should require the key |
| `QuestionSet.marking_scheme` | `app/models.py:222` | Convert to `Optional[MarkingScheme] = None` unless the API should require the key |
| `Quiz.metadata` | `app/models.py:249` | Convert to `Optional[QuizMetadata] = None` unless the API should require the key |
| `SessionAnswer.time_spent` | `app/models.py:412` | Convert to `Optional[int] = None` unless the API should reject `null` and omitted values |

##### `app/models.py` -- mutable default cleanup while touching the models

| Model / field(s) | Current location | Planned change |
|------------------|------------------|----------------|
| `Question.options` | `app/models.py:141` | Replace `=[]` with `Field(default_factory=list)` if empty-list default remains correct |
| `Question.solution` | `app/models.py:149` | Replace `=[]` with `Field(default_factory=list)` if empty-list default remains correct |
| `Session.events` | `app/models.py:462` | Replace `=[]` with `Field(default_factory=list)` |
| `Session.question_order` | `app/models.py:472-474` | Replace `=[]` with `Field(default_factory=list)` |

Add focused tests for PATCH/update/null behavior, especially `UpdateSessionAnswer` payloads such as `{"visited": true}`, `{"answer": [...]}`, `{}`, `{"answer": null}`, and `{"time_spent": null}`. The empty payload should still be handled by the endpoint's explicit validation path rather than failing model construction unexpectedly. Preserve the current two-dump merge semantics in `remove_optional_unset_args()` unless the implementation intentionally changes the API contract and documents that change.

##### `app/utils.py` -- 2 `.dict()` calls (line 29)

| Current | Change |
|---------|--------|
| `model.dict(exclude_unset=True)` | `model.model_dump(exclude_unset=True)` |
| `model.dict(exclude_none=True)` | `model.model_dump(exclude_none=True)` |

> This file is called from `app/routers/session_answers.py` (lines 125 and 183) -- critical runtime paths.

Keep the current behavior that merges `exclude_unset=True` and `exclude_none=True` results unless the migration explicitly decides to change PATCH semantics for explicit `null`.

##### `app/routers/sessions.py` -- 3 `.parse_obj()` calls

| Line | Current | Change |
|------|---------|--------|
| 192 | `SessionAnswer.parse_obj(...)` | `SessionAnswer.model_validate(...)` |
| 283 | `SessionAnswer.parse_obj(...)` | `SessionAnswer.model_validate(...)` |
| 350 | `Event.parse_obj(...)` | `Event.model_validate(...)` |

##### `app/routers/session_answers.py` -- 2 `__fields_set__` usages

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
4. Migrate Pydantic v1 -> v2 across all affected files (see detailed breakdown above):
   - `app/schemas.py` -- rewrite `PyObjectId` custom type (highest complexity)
   - `app/models.py` -- convert all 13 `class Config` blocks to `model_config = ConfigDict(...)`
   - `app/models.py` -- add defaults for Pydantic v2 Optional fields where omission is valid, convert nullable non-Optional fields deliberately, and fix mutable list defaults
   - `app/settings.py` -- change `BaseSettings` import to `pydantic_settings`
   - `app/utils.py` -- change `.dict()` to `.model_dump()`
   - `app/routers/sessions.py` -- change `.parse_obj()` to `.model_validate()`
   - `app/routers/session_answers.py` -- change `__fields_set__` to `model_fields_set`
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

## Execution Order

1. **Remove Lambda/SAM/Mangum (Pre-Phase A)**
   - Delete SAM templates, Lambda deploy workflows
   - Remove Mangum from `main.py` and `requirements.txt`
   - Clean up docs, `.gitignore`, `.dockerignore`, stale ECS migration branch triggers, and active-doc references
   - Verify ECS deploys still work after cleanup

2. **Upgrade Python to 3.12 (Pre-Phase B)**
   - Run the Phase 1 compatibility-matrix selection and throwaway spike first
   - Record the selected exact versions in the plan or a linked implementation note
   - Bump all dependencies to exact tested Python 3.12-compatible pins
   - Migrate Pydantic v1 -> v2 in `models.py`, `schemas.py`, `settings.py`, `utils.py`, and affected router files (see detailed breakdown in Pre-Phase B)
   - Update Dockerfile and CI workflow Python/action versions
   - Run full test suite, fix breakage
   - Docker build verification plus local container-start `/health` smoke

3. **Finalize compatibility matrix and dependency pins (Phase 1)**
   - This phase overlaps with Pre-Phase B and must be completed before dependency edits are final
   - Record the exact stack versions selected from the migration spike
   - Pin all dependencies in `app/requirements.txt`

This order removes dead code first, then upgrades the language and framework stack to establish a clean baseline.

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Pydantic v1 -> v2 migration breaks request/response models | Migrate models carefully, run full test suite after each file. Use Pydantic's migration guide |
| Pydantic v2 changes omitted or explicit-`null` request semantics | Add explicit defaults for optional/update fields, convert nullable non-Optional fields deliberately, and add focused tests for omitted and explicit-`null` PATCH fields |
| Dependency upgrades introduce breaking changes | Upgrade and test incrementally, not all at once |
| Packaging or import cleanup accidentally changes deployment entrypoints | Preserve the current top-level module layout plus `main:app` export throughout the migration |

---

## Done Criteria

- All Lambda/SAM/Mangum traces removed from the codebase
- Python upgraded to 3.12 with all dependencies at exact tested compatible pins chosen from a recorded compatibility matrix/spike
- Pydantic v2 migration complete in `models.py`, `schemas.py`, `settings.py`, `utils.py`, and affected router files
- Pydantic v2 Optional/default behavior is explicitly handled for update/PATCH models, nullable non-Optional fields, and mutable list defaults, and verified with tests
- Active docs/config pass the Lambda/SAM/Mangum validation grep outside explicitly historical paths
- Local Docker validation includes both image build success and a container-start `/health` smoke
- Full test suite passes, including `app/tests/test_scoring.py`

---

> **Next step:** After this PR merges, continue with `pymongo-async-migration-plan.md`.
