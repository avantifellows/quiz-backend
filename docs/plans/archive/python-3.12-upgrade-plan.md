# Python 3.12 Upgrade + Lambda Cleanup Plan

**Date:** 2026-04-01
**Goal:** Remove all Lambda/SAM/Mangum traces from the codebase, upgrade Python from 3.9 to 3.12, and migrate from Pydantic v1 to Pydantic v2. This establishes a clean, modern baseline before the async MongoDB migration.
**Expected outcome:** A simplified codebase with no dead Lambda code, running on Python 3.12 with modern dependency pins and Pydantic v2 models. This is a prerequisite for the PyMongo Async migration that follows.

---

## Selected Compatibility Matrix (validated 2026-04-09)

| Package | Version | Notes |
|---------|---------|-------|
| Python | 3.12.8 | Target runtime |
| fastapi | 0.115.12 | Requires Pydantic v2, stable 0.115.x line |
| pydantic | 2.11.3 | Pydantic v2, stable release |
| pydantic-settings | 2.9.1 | BaseSettings for Pydantic v2 |
| uvicorn | 0.34.2 | ASGI server |
| pymongo | 4.12.1 | Has AsyncMongoClient, MongoDB 5.0 compatible, arm64 wheels |
| dnspython | 2.7.0 | Required for MongoDB SRV URIs |
| python-dotenv | 1.1.0 | .env file loading |
| httpx | 0.28.1 | Required by Starlette TestClient |
| pytest | 8.3.5 | Test runner |
| pytest-cov | 6.1.1 | Coverage reporting |
| requests | 2.32.3 | HTTP client |

All packages installed successfully on Python 3.12.8. PyMongo 4.12.1 has `AsyncMongoClient` support confirmed. All packages have arm64 wheels (pymongo) or are pure Python.

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
- Standalone maintenance scripts that already create their own local sync `MongoClient`, except `app/scripts/backfill_time_limits_and_spent.py`, which is in scope for shared bootstrap/import compatibility only
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
| `README.md` | Lambda deployment section (~lines 240-283), local startup section, local Mongo setup section | Remove Lambda/SAM sections, keep ECS-only, remove `--freshSync`/`--source` remote-sync startup guidance from the supported developer flow, replace Lambda-specific logging text with current ECS observability guidance or an explicit deferred-owner note, and remove the incorrect `pip install mongodb` advice |
| `context_for_ai/project-context.md` | Multiple Lambda/SAM references spread across the file | Remove all Lambda/SAM references and correct active test/runtime guidance; broader documentation cleanup can happen later |
| `docs/ENV.md` | Active environment-variable guidance | Rewrite `MONGO_AUTH_CREDENTIALS` guidance so it reflects the ECS/current test model instead of only GitHub staging/production environment wording |
| `.env.example` | Local env example | Keep it local-only, make `MONGO_AUTH_CREDENTIALS` clearly represent local developer setup, and avoid wording that implies shared staging/production URIs are part of normal setup |
| `startServerMac.sh` | Argument parsing and startup flow | Remove the destructive `--freshSync` / `--source` remote-sync path from the supported startup script, keep the script focused on local app startup, and source repo-root `.env` explicitly if present |
| `startServerLinux.sh` | Argument parsing and startup flow | Remove the destructive `--freshSync` / `--source` remote-sync path from the supported startup script, keep the script focused on local app startup, and source repo-root `.env` explicitly if present |
| `.planning/ecs-migration-status-and-next-steps.md` | Active migration status note still describing Lambda as live and linking a missing current doc | Archive it or rewrite it as historical so it no longer acts like current operational guidance |

### Historical-doc decision

Archived/historical docs under archive directories should be treated as historical records and are exempt from destructive rewriting unless they are referenced as current operational guidance. For this repo, do not rely on the previous "historical unless referenced" shortcut:

- `.planning/ecs-migration-status-and-next-steps.md` is currently an active doc and conflicts with the newer ECS-complete direction. Pre-Phase A must either archive it or rewrite it explicitly as historical.
- `context_for_ai/plans/ecs-migration-implementation-plan.md` should be treated as a historical implementation record for the completed ECS migration, not as active operational guidance for the current codebase.
- Active docs and current developer guidance must be ECS-only. Any active references that keep old Lambda-era planning docs looking current should be removed or replaced during cleanup.

### Validation after cleanup

- Run a post-cleanup search to confirm active docs/config no longer reference Lambda/SAM/Mangum or Zappa leftovers:

```bash
rg --hidden -n -i "(deploy_to_staging|deploy_to_prod|setup-sam|sam build|sam deploy|samconfig\.toml|\.aws-sam|mangum|aws lambda|zappa_env/|zappa_settings\.json)" . \
  -g '!.git/**' \
  -g '!docs/plans/archive/**' \
  -g '!context_for_ai/plans/**' \
  -g '!pral/pral/workspaces/**' \
  -g '!docs/plans/python-3.12-upgrade-plan.md'
```

- If `.pre-commit-config.yaml` drops the CloudFormation hook, also update `context_for_ai/project-context.md` so its tooling/docs section no longer claims CloudFormation linting is part of the active workflow.
- Confirm no active doc still points to stale ECS/Lambda planning paths such as `context_for_ai/plans/ecs-migration-implementation-plan.md` or the missing `docs/MIGRATION_LAMBDA_TO_ECS.md`. If such references remain, remove them or rewrite the doc as historical before calling cleanup complete.
- Run a separate stale-guidance search for active Python/runtime/test-model references that should disappear during this PR, for example:

```bash
rg --hidden -n -i "(python 3\\.9|python-version:\\s*['\"]?3\\.(9|11)['\"]?|mongoengine|mongomock|MONGO_AUTH_CREDENTIALS.*(staging|production|github)|github staging|github production)" . \
  -g '!.git/**' \
  -g '!docs/plans/archive/**' \
  -g '!context_for_ai/plans/**' \
  -g '!pral/pral/workspaces/**' \
  -g '!docs/plans/python-3.12-upgrade-plan.md'
```

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
| `.github/workflows/ci.yml` | `supercharge/mongodb-github-action@1.7.0` | Audit Python 3.12-era compatibility and keep or upgrade intentionally |
| `.github/workflows/ci.yml` | `codecov/codecov-action@v2` | Upgrade to a supported current major or explicitly validate support before keeping it |
| `.github/workflows/ci.yml` | `pre-commit/action@v3.0.0` | Upgrade to a supported current major or explicitly validate why keeping it is acceptable |

### Local development/runtime alignment

Pre-Phase B also needs to update the local developer path, not just Docker and CI:

- Update active local-setup docs in `README.md`, `CLAUDE.md`, and `context_for_ai/project-context.md` so they describe Python 3.12 as the required interpreter for local work.
- Update `docs/ENV.md` and `.env.example` at the same time so environment-variable guidance matches the new local/CI test model and no longer implies that GitHub staging/production environment setup is the primary way to think about `MONGO_AUTH_CREDENTIALS`.
- Verify both `startServerMac.sh` and `startServerLinux.sh` under Python 3.12, including their current `venv` activation flow and `uvicorn main:app --reload` startup path.
- Make repo-root invocation the explicit supported contract for both startup scripts; if that assumption stays, document it clearly instead of leaving it implicit.
- Replace the hidden import-time `../.env` fallback with an explicit local startup path: update `startServerMac.sh` and `startServerLinux.sh` to source the repo-root `.env` before starting the app, and document manual `export MONGO_AUTH_CREDENTIALS=...` as the supported alternative.
- Remove the destructive `--freshSync` remote-sync workflow from the supported startup path in this PR. If the team still needs remote data copy later, move it to a separate manual script or runbook with explicit warnings rather than keeping it in the normal startup scripts.
- Treat the baked-in Mongo service startup commands in `startServerMac.sh` and `startServerLinux.sh` as local convenience helpers only, not as part of the required automated validation contract.
- Document that developers may start Mongo separately and then run the app with Python 3.12 without depending on the helper commands.
- Make the interpreter check explicit in docs: either recreate the virtualenv with Python 3.12 before running the startup scripts, or activate the existing `venv` and prove `python --version` reports 3.12 before using it.
- Keep repo-local interpreter markers such as `.python-version` or `.tool-versions` out of scope by default for this PR unless the team already standardizes on one elsewhere. Accurate docs and verified startup are the required outcomes.

### Database isolation safety gate before any spike or full-suite run

This is the first gate in Pre-Phase B and must happen before the compatibility spike, dependency upgrades, or any broad test execution.

- Explicitly set `MONGO_AUTH_CREDENTIALS` to an isolated local or CI Mongo target dedicated to this repo's validation runs before running the spike or the full suite. Do not rely on ambient shell state or a developer's existing repo-local `.env`.
- In this repo, "safe" does **not** mean changing only the default database name in the Mongo URI. The code talks to `client.quiz...` directly, so DB isolation must come from a separate Mongo instance or cluster unless DB-name indirection is brought into scope separately.
- Update `app/database.py` so tests and CI do not silently load `../.env` when `MONGO_AUTH_CREDENTIALS` is missing. The safer default for automated paths is to fail clearly when the variable is unset.
- Keep local developer convenience in the startup scripts and docs, not in the core database bootstrap path used by automated validation.
- Remove `mongoengine` and `mongomock` from the active install/test path early, and replace them with one explicit cleanup model: clear the whole `quiz` database at the start of every test case in `app/tests/base.py` before fixture seeding. Do not rely on ad hoc per-test cleanup once the suite is on real Mongo.
- Record the isolated Mongo target used for the spike/full suite in the implementation notes or CI config so the safety gate is auditable.
- Treat this gate as blocking: no migration spike result or full-suite result counts unless the DB target is known-safe and recorded.

### Compatibility matrix gate before final pin edits

Pre-Phase B should not start with a blind requirements rewrite. It should start by selecting a coherent candidate matrix for:

- Python 3.12
- FastAPI / Starlette / httpx / TestClient
- Pydantic v2 + `pydantic-settings`
- PyMongo with `AsyncMongoClient`
- Uvicorn / pytest / pytest-cov / requests / support libraries

That candidate matrix should then be validated in a short throwaway spike before the pins in `app/requirements.txt`, Docker, and CI are treated as final. Record the chosen exact versions in this plan or in a linked implementation note before mass edits begin.

### Compatibility targets that must stay explicit

- `linux/arm64` is a required compatibility target because the real ECS deploy path builds ARM64 images. A default local Docker build is not enough by itself.
- ECS workflow success is the final architecture gate, but the upgrade work should also perform an explicit local or CI-visible ARM64 image build validation before calling the stack ready.
- MongoDB 5.0 remains the server compatibility target for this PR because `.github/workflows/ci.yml` currently runs the suite against MongoDB 5.0. Upgrading CI to MongoDB 6.0 at the same time would widen scope unnecessarily.
- Local docs may continue to mention MongoDB 6.0 for developer setup if that remains the preferred local install path, but the selected dependency stack must at least prove compatibility against MongoDB 5.0.

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
| `mongoengine` | 0.24.1 | Still on the active install and test-import path | Remove in this PR as early test-path cleanup |
| `mongomock` | 4.0.0 | Still on the active install and test-import path | Remove in this PR as early test-path cleanup |
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

> **Early gate:** Immediately after the `pydantic-settings` swap, run a direct `main:app` import or `TestClient` smoke before broader router/model/container work. `Settings()` is instantiated at import time in multiple modules, so this check must happen early.

##### `app/schemas.py` -- `PyObjectId` custom type rewrite (HIGH complexity)

The `PyObjectId` class (lines 5-18) uses two methods removed in Pydantic v2:

| Method | Current (v1) | Replacement (v2) |
|--------|-------------|-------------------|
| `__get_validators__()` | Yields `cls.validate` | Replace with `__get_pydantic_core_schema__(cls, source_type, handler)` using `pydantic_core.core_schema` |
| `__modify_schema__()` | `field_schema.update(type="string")` | Replace with `__get_pydantic_json_schema__(cls, schema, handler)` |

This requires importing `pydantic_core.core_schema` and using `core_schema.no_info_plain_validator_function()` or similar. This is the most non-trivial single change in the migration.

The rewrite also needs an explicit contract:

- Models should continue to accept both string ids and BSON `ObjectId` inputs unless a specific endpoint contract is intentionally narrowed and documented.
- JSON responses must serialize all `PyObjectId` values as strings.
- OpenAPI / JSON schema output must expose these id fields as `type: string`, including nested and inherited model fields.
- Create paths that call `jsonable_encoder()` before Mongo inserts must preserve the current stored-id behavior, including string `_id` values where the live app currently inserts encoded model dictionaries.
- Preserve the existing route-level ID output contracts instead of normalizing everything to one shape during this migration. Some paths currently return `_id`, while others expose `id`; the plan should lock down today's behavior per route.
- Add focused tests for `model_validate()` from a string id, `model_validate()` from an `ObjectId`, JSON serialization, create-path insert payloads that rely on `jsonable_encoder()`, current route-level ID field shapes, and `/openapi.json` id-field schema output.

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

The batch PATCH path needs separate compatibility coverage, not just the single-item route. Explicitly test the live `List[Tuple[int, UpdateSessionAnswer]]` request shape used by `update_session_answers_at_specific_positions()`, including:

- omitted business fields
- explicit `null` values
- empty per-item payloads
- scalar `int` answer payloads
- scalar `str` answer payloads
- dict answer payloads
- `List[str]` answer payloads
- duplicate positions
- negative or out-of-bounds positions
- nested tuple/list parsing under Pydantic v2 before endpoint validation runs

Cover both the single-item PATCH route and the batch PATCH route so the migration does not silently narrow the accepted `answerType` contract already declared in `app/models.py`.

##### Request/response contracts that must be made explicit during the migration

- `Session.user_id` is typed/stored as `str` today, but active tests still submit integers to `POST /sessions`. Preserve the current API behavior by accepting numeric `user_id` inputs at the request boundary and normalizing them to strings before storage and response validation. Add migration coverage that sends `user_id` as an integer and proves the stored and returned value is a string.
- Quiz create/read behavior for `correct_answer` must be locked down separately from PATCH behavior. Preserve the current stored/read shapes for fixture-backed values that already exist in this repo unless a test proves the app already expects normalization:
  - float values
  - integer values
  - numeric-string values
  - existing list values in question data
- Add explicit create-and-read compatibility coverage for those `correct_answer` shapes so Pydantic v2 union validation does not silently change quiz creation or quiz retrieval behavior.

##### Raw-dict `response_model` paths that need focused Pydantic v2 coverage

The response-validation risk in this migration is specifically about endpoints that still return raw Mongo/Python dict data while declaring `response_model=...`, because those paths will be revalidated under Pydantic v2. Focus the compatibility checks and tests on those routes. Do not widen this item to handlers that return `JSONResponse` directly unless the implementation changes them back onto the model-validation path.

The migration spike and follow-up tests should cover a small route matrix rather than a single representative route:

- `/quiz/{id}`
- `/form/{id}`
- `/sessions/{id}`
- `/questions/{id}`

The `/quiz/{id}` item needs explicit response-shape and backwards-compatibility acceptance criteria, not just "response validation passes." Require:

- preserved trimmed-question placeholder keys for sparse question entries returned by `/quiz/{id}`
- explicit verification that trimmed questions still include `text`, `instructions`, `image`, `options`, `marking_scheme`, `solution`, and `metadata`
- explicit verification that nullable placeholder fields remain `None` where that is the current contract
- explicit verification that list-shaped placeholder fields such as `solution` and `options` remain `[]` where that is the current contract
- one legacy stored-document fixture inserted directly in Mongo so `update_quiz_for_backwards_compatibility()` is exercised for missing question-set fields such as `max_questions_allowed_to_attempt`, `title`, and `marking_scheme`

The `/form/{id}` item needs branch-level acceptance criteria, not just one happy-path test. Require:

- a real form fixture/helper path in `app/tests/base.py` or nearby test helpers
- rejection coverage for non-form records sent to `/form/{id}`
- `single_page_mode` coverage that proves full question details are fetched
- OMR option-count aggregation and padding coverage for the returned question subsets

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

1. Apply the DB-isolation safety gate before any spike or full-suite run
   - Set `MONGO_AUTH_CREDENTIALS` explicitly to an isolated Mongo target dedicated to this repo's validation runs
   - Do not treat a different URI default database name as isolation; the code still uses `client.quiz...`
   - Remove automated-path reliance on `../.env` fallback in `app/database.py`
   - Keep local convenience by sourcing repo-root `.env` in the startup scripts or by manual export, not by hidden import-time loading
   - Treat any run without explicit DB targeting as invalid for plan sign-off
2. Select a candidate exact-version compatibility matrix for Python 3.12, FastAPI/Starlette/httpx/TestClient, Pydantic v2, PyMongo Async, Uvicorn, pytest, pytest-cov, requests, and support libraries
   - Record the candidate exact versions in this plan or a linked implementation note before mass edits
   - Treat this as a gate for the rest of Pre-Phase B, not a later optional clean-up
3. Run a throwaway migration spike with that candidate matrix before finalizing dependency edits
   - Keep the spike inside the current architecture: validate `AsyncMongoClient`, one minimal async CRUD path, the raw-dict route matrix (`/quiz/{id}`, `/form/{id}`, `/sessions/{id}`, `/questions/{id}`), the batch `List[Tuple[int, UpdateSessionAnswer]]` PATCH shape, one single-item PATCH-style Pydantic v2 path, the `POST /sessions` `user_id` int-to-string compatibility path, quiz create/read `correct_answer` compatibility on float/int/numeric-string/list shapes, and the existing module-level `main:app` / `TestClient` flow
   - Treat `/quiz/{id}` as a contract-preservation item: sparse questions must keep their current placeholder key set and `None`/`[]` placeholder values, not merely satisfy Pydantic v2 validation
   - Add one legacy stored-quiz fixture to the spike or immediate follow-up tests so `update_quiz_for_backwards_compatibility()` is proven against documents missing question-set fields such as `max_questions_allowed_to_attempt`, `title`, and `marking_scheme`
   - Treat `/form/{id}` as a multi-branch compatibility item: non-form rejection, `single_page_mode`, and OMR option-count/padding all need coverage
   - Cover the full accepted `answerType` contract in both single-item and batch PATCH paths, including scalar `int`, scalar `str`, dict, and `List[str]` payloads
   - If the spike fails, revise the matrix before touching the broader codebase
4. Remove `mongoengine` and `mongomock` from the active install/test path early in the implementation
   - Update `app/tests/base.py` so the suite no longer imports or connects through those packages
   - Keep the test path aligned with the repo's actual real-Mongo integration behavior by clearing the whole `quiz` database at the start of each test case in `app/tests/base.py` before seeding fixtures
5. Bump all dependencies to the selected Python 3.12-compatible exact pins in `requirements.txt` (including adding `pydantic-settings`)
   - Use exact tested pins for the whole stack, not `latest`, `>=`, or other open-ended ranges
   - Add and pin `httpx` for the modern Starlette/FastAPI `TestClient`
   - Add or pin `pytest-cov`, and update CI so it does not install unpinned `pytest pytest-cov`
6. Swap `app/settings.py` to `pydantic-settings` and run an immediate import smoke
   - Perform a direct `main:app` import or `TestClient` smoke right after the settings change before broader router/model rewrites
   - Treat this as an early gate because `Settings()` is instantiated at import time across multiple modules
7. Migrate Pydantic v1 -> v2 across all affected files (see detailed breakdown above):
   - `app/schemas.py` -- rewrite `PyObjectId` custom type (highest complexity)
   - Preserve the explicit `PyObjectId` contract: accept `str` and `ObjectId` inputs, serialize ids as strings, preserve current create-path stored `_id` behavior, preserve current route-level `id` vs `_id` output shapes, and prove `/openapi.json` exposes string id schemas
   - `app/models.py` -- convert all 13 `class Config` blocks to `model_config = ConfigDict(...)`
   - `app/models.py` -- add defaults for Pydantic v2 Optional fields where omission is valid, convert nullable non-Optional fields deliberately, fix mutable list defaults, preserve `Session.user_id` int-input-to-string behavior, and preserve quiz create/read `correct_answer` shapes unless a tested normalization decision is made
   - `app/settings.py` -- change `BaseSettings` import to `pydantic_settings`
   - `app/utils.py` -- change `.dict()` to `.model_dump()`
   - `app/routers/sessions.py` -- change `.parse_obj()` to `.model_validate()`
   - `app/routers/session_answers.py` -- change `__fields_set__` to `model_fields_set`
   - Keep `app/scripts/backfill_time_limits_and_spent.py` in scope for import/bootstrap compatibility after the shared settings/database changes, without widening scope into broader script refactors
8. Update `Dockerfile` base image to `python:3.12-slim`
9. Update CI workflow Python versions and old workflow action majors together
   - Prefer supported current majors for `actions/checkout`, `actions/setup-python`, the MongoDB GitHub Action, Codecov, and `pre-commit/action` while the CI workflow is already being edited
   - Keep MongoDB 5.0 as the CI service version for this PR unless a separately scoped change intentionally updates the server target
   - Explicitly set the safe CI `MONGO_AUTH_CREDENTIALS` during test runs instead of relying on fallback behavior
   - Make an explicit decision on `coverage`: either pin it directly in the install path or document why its indirect installation remains intentional and stable
   - If any action version is intentionally kept, explicitly validate and document Python 3.12 support
10. Update local developer docs and startup guidance to Python 3.12
   - Cover `README.md`, `CLAUDE.md`, and `context_for_ai/project-context.md`
   - Cover `docs/ENV.md` and `.env.example` for environment-variable/test-model guidance
   - Update `startServerMac.sh` and `startServerLinux.sh` to remove `--freshSync` from the supported startup flow, source repo-root `.env`, document manual export as the fallback path, keep repo-root invocation as the explicit supported usage, and verify both scripts under Python 3.12 after recreating or version-checking the virtualenv
   - Document that the built-in Mongo start commands are optional local helpers and that developers may start Mongo separately before launching the app
   - Remove or replace the incorrect README instruction telling Ubuntu users to run `pip install mongodb` for local database setup
11. Run full test suite, including `app/tests/test_scoring.py`, and fix any breakage
12. Do a local Docker build and a local container-start smoke test
   - Start the built image with required env vars
   - Confirm `uvicorn main:app` imports successfully
   - Hit `/health` to prove import/startup success independent of DB-backed smoke validation
13. Add one DB-backed smoke validation after image build or ECS deploy
   - Keep `/health` as the liveness check, but also verify one stable DB-backed read path using known-safe data or a short manual runbook step
   - Reuse an existing stable endpoint such as organization authentication or quiz fetch in the target environment
14. Prove the deployment build path remains compatible with ECS
   - Run an explicit `linux/arm64` image build validation locally or in CI-visible automation
   - Treat ECS workflow success as the final architecture gate before the plan is considered complete

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

- Before the broader code migration starts, select one exact `pymongo` version that is compatible with Python 3.12, includes `AsyncMongoClient`, preserves MongoDB 5.0 compatibility for CI, and is validated against the ARM64 deployment path used by ECS. Validate it with the migration spike below, then record the exact pin in `app/requirements.txt`.

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

- While the CI workflow is being updated for Python 3.12, also update or explicitly validate the action versions used by checkout, setup-python, the MongoDB GitHub Action, Codecov, and `pre-commit/action`.
- Make `coverage` installation explicit during this phase: either pin it directly in `app/requirements.txt` or document the exact indirect install path being relied on.
- Treat deploy-workflow hardening as optional but worthwhile follow-up while those files are open.
  - Either pin/set up Python explicitly in the ECS deploy workflows, or replace the inline `python3 -c` task-definition rewrite with a checked-in script or another clearer method.
  - Optionally align Docker bootstrap behavior with the final CI install flow if that falls out naturally from the implementation.

- Remove `mongoengine` and `mongomock` in this PR as early test-path cleanup.
  - These packages are confirmed no-ops for application data access, but they are still part of the active install/import path today via `app/requirements.txt` and `app/tests/base.py`.
  - Keeping them adds unnecessary Python 3.12 packaging risk and misrepresents how the suite actually talks to MongoDB.

### Migration spike before mass edits

Before broad router/test rewrites, do a short spike that validates the risky integration points together:

- explicit isolated DB targeting via `MONGO_AUTH_CREDENTIALS`, with no test/CI reliance on repo-local `.env` fallback and no assumption that URI default DB selection isolates this repo
- Python 3.12 environment with exact candidate dependency pins
- `pymongo.AsyncMongoClient` creation, one async `find_one`/`insert_one`, and client close behavior
- the raw-dict `response_model` matrix: `/quiz/{id}`, `/form/{id}`, `/sessions/{id}`, and `/questions/{id}`
- `/quiz/{id}` sparse-response behavior: trimmed questions must keep the current placeholder keys and current `None`/`[]` value shapes, not just validate successfully
- one legacy `/quiz/{id}` stored-document case that exercises `update_quiz_for_backwards_compatibility()` on documents missing question-set fields
- `/form/{id}` branch behavior: non-form rejection, `single_page_mode` full-question fetches, and OMR option-count aggregation/padding
- `POST /sessions` compatibility when callers send `user_id` as an integer, with explicit proof that storage and responses still use strings
- quiz create/read compatibility for stored `correct_answer` shapes already present in fixtures: float, integer, numeric-string, and list values
- One Pydantic v2 model path, including omitted-field and explicit-`null` PATCH-style payloads for `UpdateSessionAnswer`
- the batch `List[Tuple[int, UpdateSessionAnswer]]` request shape, including empty item payloads, scalar `int`, scalar `str`, dict, and `List[str]` answers, duplicate positions, and invalid positions
- the `PyObjectId` acceptance/serialization contract, including `str` + `ObjectId` inputs, string-typed OpenAPI output, create-path stored `_id` behavior, and current route-level `id` vs `_id` response contracts
- the existing module-level `main:app` import and `TestClient` path, without introducing `create_app()`, `get_quiz_db()`, lifespan rewrites, or `MONGO_DB_NAME` refactors in this plan
- at least one `linux/arm64` image build on the selected dependency stack, or a clearly documented equivalent pre-merge architecture check
- one DB-backed smoke or runbook validation beyond `/health` after build/deploy, so the spike notes do not stop at pure liveness

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
   - Archive or rewrite `.planning/ecs-migration-status-and-next-steps.md` so it no longer acts like current guidance
   - Verify ECS deploys still work after cleanup

2. **Upgrade Python to 3.12 (Pre-Phase B)**
   - Apply the DB-isolation safety gate before any spike or full-suite run
   - Run the Phase 1 compatibility-matrix selection and throwaway spike first
   - Record the selected exact versions in the plan or a linked implementation note
   - Remove `mongoengine` and `mongomock` from the active test/install path early
   - Bump all dependencies to exact tested Python 3.12-compatible pins
   - Swap `app/settings.py` to `pydantic-settings` and pass the immediate import smoke before broader migration work
   - Migrate Pydantic v1 -> v2 in `models.py`, `schemas.py`, `settings.py`, `utils.py`, and affected router files (see detailed breakdown in Pre-Phase B)
   - Update Dockerfile and CI workflow Python/action versions
   - Update local Python 3.12 docs plus `docs/ENV.md` and `.env.example`, remove `--freshSync` from the supported startup flow, and verify `startServerMac.sh` / `startServerLinux.sh` against a real Python 3.12 interpreter
   - Run full test suite, fix breakage
   - Docker build verification plus local container-start `/health` smoke
   - Add one DB-backed smoke or runbook check after build/deploy
   - Explicit ARM64 build validation, with ECS workflow success as the final architecture gate

3. **Finalize compatibility matrix and dependency pins (Phase 1)**
   - This phase overlaps with Pre-Phase B and must be completed before dependency edits are final
   - Record the exact stack versions selected from the migration spike
   - Pin all dependencies in `app/requirements.txt`

This order removes dead code first, then upgrades the language and framework stack to establish a clean baseline.

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Spike or full-suite run targets the wrong database through `.env` fallback or URI-default-db assumptions | Require an explicit isolated `MONGO_AUTH_CREDENTIALS` before any automated validation, state that URI default DB selection does not isolate `client.quiz...`, remove silent test/CI fallback to `../.env`, and document whole-DB cleanup in `app/tests/base.py` |
| Pydantic v1 -> v2 migration breaks request/response models | Migrate models carefully, run full test suite after each file. Use Pydantic's migration guide |
| `Session.user_id` input coercion changes accidentally under Pydantic v2 | Preserve numeric-input acceptance at the request boundary, normalize to string before storage/response validation, and add explicit `POST /sessions` migration coverage |
| Pydantic v2 changes omitted or explicit-`null` request semantics | Add explicit defaults for optional/update fields, convert nullable non-Optional fields deliberately, and add focused tests for omitted and explicit-`null` behavior in both single-item and batch PATCH request shapes |
| Quiz create/read behavior changes for mixed `correct_answer` shapes under v2 union validation | Add explicit create/read coverage for float, integer, numeric-string, and list-backed `correct_answer` values, and preserve current read behavior unless a tested normalization decision is made |
| `PyObjectId` rewrite breaks DB writes or route-level ID output shapes | Preserve and test the contract for `str` and `ObjectId` inputs, string JSON serialization, create-path stored `_id` behavior, current route-level `id` vs `_id` outputs, and string-typed `/openapi.json` ids |
| Raw-dict endpoints behave differently under Pydantic v2 response validation | Add focused coverage for the raw-dict route matrix (`/quiz`, `/form`, `/sessions`, `/questions`), require exact `/quiz` sparse-response placeholder-key preservation plus a legacy stored-document case, require branch-level `/form` checks, and do not spend time on `JSONResponse` paths unless they are refactored onto model validation |
| Dependency upgrades introduce breaking changes | Upgrade and test incrementally, not all at once |
| The destructive remote-sync startup path survives as normal developer guidance | Remove `--freshSync` from the supported startup scripts/docs in this PR and, if still needed later, move remote sync into a separate manual workflow with explicit warnings |
| Python 3.12 dependencies build differently on ECS ARM64 than on a default local host image | Require explicit `linux/arm64` build validation before relying on ECS workflow success as the final architecture gate |
| Post-build or post-deploy smoke passes while DB access is broken | Keep `/health` for liveness, but require one DB-backed smoke or manual runbook validation before sign-off |
| Packaging or import cleanup accidentally changes deployment entrypoints | Preserve the current top-level module layout plus `main:app` export throughout the migration |

---

## Done Criteria

- All Lambda/SAM/Mangum traces removed from the codebase
- Python upgraded to 3.12 with all dependencies at exact tested compatible pins chosen from a recorded compatibility matrix/spike
- No migration spike or full-suite result is accepted unless `MONGO_AUTH_CREDENTIALS` was set explicitly to an isolated local/CI Mongo target dedicated to this repo, with no reliance on URI default DB naming as a safety mechanism
- `mongoengine` and `mongomock` removed from `app/requirements.txt` and the active test path
- `app/tests/base.py` defines the real-Mongo cleanup model explicitly by clearing the `quiz` database before each test case and then seeding fixtures
- Pydantic v2 migration complete in `models.py`, `schemas.py`, `settings.py`, `utils.py`, and affected router files
- The `pydantic-settings` swap passes an immediate `main:app` import or `TestClient` smoke before broader router/model/container work proceeds
- Pydantic v2 Optional/default behavior is explicitly handled for update/PATCH models, nullable non-Optional fields, mutable list defaults, the raw-dict route matrix, the exact `/quiz/{id}` sparse-response placeholder-key contract, the batch `List[Tuple[int, UpdateSessionAnswer]]` request shape including scalar and dict answer variants, the `Session.user_id` int-input-to-string contract, quiz create/read `correct_answer` compatibility, and the `PyObjectId` input/output schema contract, and verified with tests
- Active docs/config pass both the Lambda/SAM/Mangum cleanup grep and the stale runtime/test-guidance grep outside explicitly historical paths
- Active docs are consistent with the new reality: `README.md`, `CLAUDE.md`, `context_for_ai/project-context.md`, `docs/ENV.md`, and `.env.example` describe ECS-only deployment, Python 3.12 local setup, explicit interpreter verification, repo-root startup-script usage, the startup-script `.env` loading/manual export path, removal of `--freshSync` from the supported startup flow, optional local Mongo helper commands, proper local Mongo installation guidance, and the real Mongo-backed test model rather than `mongomock`
- `PyObjectId` compatibility is proven for validation, JSON/OpenAPI output, create-path stored `_id` behavior, and current route-level `id` vs `_id` response contracts
- `/quiz/{id}` compatibility is proven for both the sparse-response placeholder-key contract and the legacy stored-document compatibility backfill path
- `/form/{id}` compatibility is proven across non-form rejection, `single_page_mode`, and OMR option-count/padding behavior
- `/questions/{id}` is covered as the fourth raw-dict response-validation route in the migration matrix
- `app/scripts/backfill_time_limits_and_spent.py` still imports and runs after the shared settings/database bootstrap changes
- CI workflow updates explicitly cover the MongoDB GitHub Action, `pre-commit/action`, and the `coverage` install path instead of relying on implicit behavior
- Local Docker validation includes both image build success and a container-start `/health` smoke, plus one DB-backed smoke or runbook check
- The selected dependency stack is proven against MongoDB 5.0 in CI and against the ECS `linux/arm64` image build path
- Full test suite passes, including `app/tests/test_scoring.py`

---

> **Next step:** After this PR merges, continue with `pymongo-async-migration-plan.md`.
