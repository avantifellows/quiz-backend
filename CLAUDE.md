# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FastAPI-based REST API for a mobile-friendly quiz engine. Manages quizzes, questions, sessions, and user answers with support for various question types (single-choice, multi-choice, subjective, numerical, matrix-match). Built with Python 3.12, Pydantic v2, and PyMongo AsyncMongoClient (pymongo 4.16.0). Uses MongoDB. Deployed on ECS Fargate (testing/production).

## Common Commands

```bash
# Start development server (starts MongoDB + Uvicorn on port 8000)
./startServerMac.sh        # macOS
./startServerLinux.sh      # Linux

# Install dependencies
pip install -r app/requirements.txt

# Run tests
pytest                      # all tests
pytest app/tests/test_quizzes.py  # single file
pytest -k "test_name"       # single test by name

# Pre-commit hooks (auto-runs on commit)
pre-commit install          # install hooks
pre-commit run --all-files  # manual run

# API docs available at http://127.0.0.1:8000/docs after server start
```

## Architecture

### Directory Structure
- `app/main.py` - FastAPI app initialization, middleware (request logging, CORS, GZIP), `/health` endpoint
- `app/routers/` - API route handlers (quizzes, questions, sessions, session_answers, organizations, forms)
- `app/models.py` - Pydantic v2 request/response models (ConfigDict, model_validate, model_dump)
- `app/schemas.py` - Enums (QuestionType, QuizType, NavigationMode) and custom types (PyObjectId with Pydantic v2 core schema)
- `app/database.py` - MongoDB async connection (AsyncMongoClient) with `init_db()`, `close_db()`, `get_quiz_db()` accessor
- `app/cache.py` - Redis cache client, helpers (`cache_get`, `cache_set`, `cache_key`), shared quiz loader (`get_cached_quiz`)
- `app/settings.py` - `Settings` (non-Mongo), `MongoSettings` (Mongo-specific), `CacheSettings` (Redis, lazy via `get_cache_settings()`)
- `app/services/` - Shared service helpers: `quiz_fixups.py` (backwards-compat fixup), `omr.py` (OMR aggregation pipeline), `scoring.py` (session metrics)
- `app/scripts/` - Database migration scripts (including `backfill_quiz_backwards_compatibility.py`)
- `Dockerfile` - Container image (ARM64/Graviton, 4 Uvicorn workers)
- `terraform/` - ECS Fargate infrastructure (testing + prod environments)

### API Routes
```
GET    /health                     - ALB health check (no DB, no auth)
POST   /quiz                      - Create quiz with embedded questions
GET    /quiz/{quiz_id}            - Get quiz
GET    /form/{form_id}            - Get form (quiz_type must be "form")
GET    /questions/{question_id}   - Get question
GET    /questions/?question_set_id=...&skip=...&limit=...
POST   /organizations             - Create org (generates API key)
GET    /organizations/authenticate/{api_key}
POST   /sessions                  - Create quiz session for user
GET    /sessions/{session_id}
PATCH  /sessions/{session_id}     - Update session (events, metrics)
PATCH  /session_answers/{session_id}/{position_index}
PATCH  /session_answers/{session_id}/update-multiple-answers
```

### Key Concepts
- **Quiz** contains **QuestionSets**, each containing **Questions**
- **Sessions** track user quiz attempts with randomized question order
- **SessionAnswers** store user responses with timestamps, time_spent, visited flags
- Question ordering: Fisher-Yates shuffle in blocks of 10 (configurable via `subset_size`)
- Marking schemes can be defined at question or question-set level (question-level overrides)

### Question Types
`single-choice`, `multi-choice`, `subjective`, `numerical-integer`, `numerical-float`, `matrix-match`, `matrix-rating`, `matrix-numerical`, `matrix-subjective`

### Quiz Types
`assessment`, `homework`, `omr` (OMR-assessment), `form`

## App Architecture

### App Factory & Lifespan
- `main.py` uses `create_app()` factory with `lifespan` async context manager
- Startup: `init_db()` + `await _client.admin.command("ping")` (fail-fast connectivity check) + `await init_cache()` (best-effort Redis, never blocks startup)
- Shutdown: `await close_cache()` + `await close_db()`
- `app = create_app()` at module scope for `main:app` deployment entrypoint

### Database Seam
- `database.py` is side-effect free — no client creation at import time
- All routers use `db = get_quiz_db()` inside each handler (not at module scope)
- Async DB patterns: `await find_one()`, `await insert_one()`, `await update_one()`; `find()` returns AsyncCursor (no await), use `await cursor.to_list(length=None)`; `await aggregate()` returns AsyncCursor
- `MongoSettings` in `settings.py` reads env vars lazily via `get_mongo_settings()` — never called at module scope

### Redis Caching
- Cache-aside pattern: check cache → on miss read MongoDB → cache result → return
- `get_cached_quiz(quiz_id)` in `cache.py` is the shared quiz loader — returns canonical quiz with backwards-compat fixup applied. All quiz-reading routes should use this instead of direct `db.quizzes.find_one()`
- After cache read, `deepcopy()` before applying route-specific transforms (answer hiding, OMR shaping) to prevent mutation of shared cached data
- Cache keys are namespaced: `cache:{namespace}:{family}:{parts}` — built via `cache_key(family, *parts)`
- TTLs: 1h for immutable data (quizzes, questions, OMR), 5min for revocable data (org auth)
- Session data is NEVER cached — sessions and session_answers are always direct MongoDB reads
- OMR aggregation is in `app/services/omr.py` — shared by quiz and form routes, caches result keyed by sha256 of sorted question_set_ids
- All cache ops silently fall back on failure — Redis is optional, never required
- `CacheSettings` follows the same lazy accessor pattern: `get_cache_settings()`, never at module scope

## Testing

Tests use real MongoDB (local or CI service). `MONGO_AUTH_CREDENTIALS` must be set (app fails with RuntimeError if unset). Test fixtures in `app/tests/dummy_data/` (JSON files for various quiz types).

Base test classes in `app/tests/base.py`:
- `BaseTestCase` - sets up organizations and quiz types; uses sync `MongoClient` admin handle (`self.db`) for direct DB ops
- `SessionsBaseTestCase` - extends with session data
- `CacheEnabledBaseTestCase` (in `test_cache_integration.py`) - extends `BaseTestCase` with Redis enabled, flushes cache before/after each test. Uses `unittest.skipUnless(_redis_available())` to skip when Redis is not running
- Test harness forces `MONGO_DB_NAME=quiz_test` before app construction; `_guard_db_name()` refuses cleanup if DB is `quiz`
- `TestClient` used as context manager so lifespan startup/shutdown runs
- Test files use `self.db` (sync) for direct DB assertions — never `get_quiz_db()` (async)
- Fixture paths use `Path(__file__).resolve().parent / "dummy_data"` — no CWD assumption

### Running Tests
```bash
# Set env vars first (database.py does not load .env automatically)
export MONGO_AUTH_CREDENTIALS='mongodb://127.0.0.1:27017'
pytest                                    # all tests
pytest app/tests/test_quizzes.py          # single file
# Or with .env file (note: use set -a if .env has special chars like &)
set -a; source .env; set +a; pytest
```

## Environment Variables

Required: `MONGO_AUTH_CREDENTIALS` - MongoDB connection URI
Optional: `MONGO_DB_NAME` (default: `quiz`), `MONGO_MAX_POOL_SIZE` (default: 20), `MONGO_MIN_POOL_SIZE` (default: 5)
Cache: `CACHE_ENABLED` (default: `false`), `REDIS_URL` (default: `redis://localhost:6379/0`), `REDIS_MAX_CONNECTIONS` (default: 10), `CACHE_NAMESPACE` (default: `v1`)

Copy `.env.example` to `.env` for local development.

## Deployment

### ECS Fargate (Testing + Production)
- **Testing**: `https://quiz-backend-testing.avantifellows.org` — deploys on CI success on `main`
- **Production**: `https://quiz-backend.avantifellows.org` — deploys on CI success on `release`
- ARM64 Graviton, 1 vCPU / 2GB RAM per task, 4 Uvicorn workers, Redis 7.2.5-alpine sidecar (64MB maxmemory, allkeys-lru eviction)
- Auto-scaling: 1–10 tasks, CPU target-tracking at 50%
- HTTPS via Cloudflare proxy, DNS CNAME → ALB
- Infrastructure managed by Terraform in `terraform/testing/` and `terraform/prod/`
- Terraform state: S3 + DynamoDB backend (bootstrap at `terraform/shared/state-backend/`)

### CI/CD Workflows (`.github/workflows/`)
- `ci.yml` - Pre-commit checks and pytest
- `deploy_ecs_testing.yml` - Build ARM64 image → ECR → ECS (testing)
- `deploy_ecs_prod.yml` - Build ARM64 image → ECR → ECS (production)
