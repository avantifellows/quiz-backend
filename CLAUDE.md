# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FastAPI-based REST API for a mobile-friendly quiz engine. Manages quizzes, questions, sessions, and user answers with support for various question types (single-choice, multi-choice, subjective, numerical, matrix-match). Uses MongoDB. Deployed on ECS Fargate (testing/production).

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
- `app/models.py` - Pydantic request/response models
- `app/schemas.py` - Enums (QuestionType, QuizType, NavigationMode) and custom types (PyObjectId)
- `app/database.py` - MongoDB connection setup with connection pooling
- `app/scripts/` - Database migration scripts
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

## Testing

Tests use real MongoDB (local or CI service). Test fixtures in `app/tests/dummy_data/` (JSON files for various quiz types).

Base test classes in `app/tests/base.py`:
- `BaseTestCase` - sets up organizations and quiz types
- `SessionsBaseTestCase` - extends with session data

## Environment Variables

Required: `MONGO_AUTH_CREDENTIALS` - MongoDB connection URI

Copy `.env.example` to `.env` for local development.

## Deployment

### ECS Fargate (Testing + Production)
- **Testing**: `https://quiz-backend-testing.avantifellows.org` — deploys on CI success on `main`
- **Production**: `https://quiz-backend.avantifellows.org` — deploys on CI success on `release`
- ARM64 Graviton, 1 vCPU / 2GB RAM per task, 4 Uvicorn workers
- Auto-scaling: 1–10 tasks, CPU target-tracking at 50%
- HTTPS via Cloudflare proxy, DNS CNAME → ALB
- Infrastructure managed by Terraform in `terraform/testing/` and `terraform/prod/`
- Terraform state: S3 + DynamoDB backend (bootstrap at `terraform/shared/state-backend/`)

### CI/CD Workflows (`.github/workflows/`)
- `ci.yml` - Pre-commit checks and pytest
- `deploy_ecs_testing.yml` - Build ARM64 image → ECR → ECS (testing)
- `deploy_ecs_prod.yml` - Build ARM64 image → ECR → ECS (production)
