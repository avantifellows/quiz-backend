# Quiz Backend - Project Context

> **Last Updated:** February 7, 2026
>
> This document provides comprehensive context for AI coding agents and human engineers working on this project.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Purpose and Use Case](#purpose-and-use-case)
3. [User Flow](#user-flow)
4. [Technical Stack](#technical-stack)
5. [Project Structure](#project-structure)
6. [Core Concepts and Data Models](#core-concepts-and-data-models)
7. [API Endpoints](#api-endpoints)
8. [Database Schema](#database-schema)
9. [Key Code Files Explained](#key-code-files-explained)
10. [Important Code Patterns](#important-code-patterns)
11. [Local Development](#local-development)
12. [Testing](#testing)
13. [Deployment](#deployment)
14. [Configuration](#configuration)
15. [Logging](#logging)
16. [ECS vs Lambda](#ecs-vs-lambda)

---

## Project Overview

**Quiz Backend** is a FastAPI-based REST API for a mobile-friendly quiz engine. It is developed by [Avanti Fellows](https://avantifellows.org/), an educational non-profit organization.

The backend manages:
- Quizzes and question sets
- Individual questions with various types
- User sessions and quiz attempts
- User answers and progress tracking
- Organization authentication

**Frontend Repository:** [quiz-frontend](https://github.com/avantifellows/quiz-frontend)

---

## Purpose and Use Case

This system serves as the backend for conducting online assessments, homework assignments, and data collection forms for students. The primary use cases include:

1. **Assessments/Tests**: Timed or untimed examinations with graded questions
2. **Homework**: Practice assignments with immediate feedback
3. **OMR Mode**: Optical Mark Recognition style tests where students see a bubble sheet interface
4. **Forms**: Data collection questionnaires (non-graded)

The system is designed to handle:
- Large concurrent user loads (5,000+ students taking tests simultaneously)
- Various question types (MCQ, numerical, subjective, matrix-match)
- Partial marking schemes for competitive exams (JEE-style marking)
- Question shuffling within sections
- Session persistence and resume capability

---

## User Flow

### Typical Quiz Flow

```
1. Frontend authenticates using Organization API key
   └── GET /organizations/authenticate/{api_key}

2. User opens a quiz
   └── GET /quiz/{quiz_id}
   └── Returns quiz structure with question sets

3. User starts quiz session
   └── POST /sessions
   └── Creates session with shuffled question order
   └── Returns session with empty session_answers

4. User answers questions
   └── PATCH /session_answers/{session_id}/{position_index}
   └── Updates individual answers as user progresses

5. User navigates through quiz
   └── Session events tracked: start-quiz, resume-quiz, end-quiz

6. User submits quiz
   └── PATCH /sessions/{session_id} with end-quiz event
   └── Session metrics calculated and stored

7. User can resume if session wasn't ended
   └── POST /sessions returns existing session if no meaningful event occurred
```

### Session Management Logic

- **First Session**: New session created with shuffled question order
- **Returning User (no events)**: Same session returned
- **Returning User (with events)**: New session created, preserving answers and question order
- **OMR Mode**: Question order is sequential (not shuffled)

---

## Technical Stack

| Component | Technology |
|-----------|------------|
| **Framework** | FastAPI 0.75.0 |
| **Language** | Python 3.9 |
| **Database** | MongoDB (via PyMongo 4.0.2) |
| **Data Validation** | Pydantic 1.9.0 |
| **ASGI Server** | Uvicorn 0.17.6 (4 workers) |
| **Cloud Hosting** | ECS Fargate (testing/prod) / AWS Lambda (staging) |
| **Infrastructure** | Terraform (ECS) / AWS SAM (Lambda) |
| **DNS/HTTPS** | Cloudflare (proxy mode, domain: `avantifellows.org`) |
| **Container** | Docker (ARM64/Graviton) |
| **Testing** | Pytest + mongomock |
| **Code Quality** | Pre-commit hooks (Black, Flake8) |

---

## Project Structure

```
quiz-backend/
├── app/                          # Main application directory
│   ├── main.py                   # FastAPI app initialization, middleware
│   ├── models.py                 # Pydantic models for request/response
│   ├── schemas.py                # Enums and custom types (PyObjectId)
│   ├── database.py               # MongoDB connection setup
│   ├── settings.py               # Application settings
│   ├── utils.py                  # Utility functions
│   ├── logger_config.py          # Logging configuration
│   ├── requirements.txt          # Python dependencies
│   ├── routers/                  # API route handlers
│   │   ├── quizzes.py            # Quiz CRUD operations
│   │   ├── questions.py          # Question retrieval
│   │   ├── sessions.py           # Session management
│   │   ├── session_answers.py    # Answer updates
│   │   ├── organizations.py      # Organization auth
│   │   └── forms.py              # Form-specific endpoints
│   ├── scripts/                  # Database migration scripts
│   └── tests/                    # Test files and fixtures
│       ├── base.py               # Base test classes
│       ├── test_*.py             # Test modules
│       └── dummy_data/           # JSON test fixtures
├── templates/                    # AWS SAM templates
│   ├── staging.yaml
│   └── prod.yaml
├── docs/                         # Documentation
│   ├── ENV.md                    # Environment variables
│   ├── quiz-prod-m10_Schema_Documentation.md
│   └── MIGRATION_LAMBDA_TO_ECS.md
├── terraform/                    # ECS Fargate infrastructure
│   ├── shared/state-backend/     # S3 + DynamoDB backend bootstrap
│   ├── testing/                  # Testing environment
│   │   ├── main.tf, variables.tf, outputs.tf
│   │   ├── ecr.tf, ecs.tf, alb.tf, dns.tf, autoscaling.tf
│   │   ├── iam.tf, security.tf, data.tf
│   │   └── terraform.tfvars      # (gitignored)
│   └── prod/                     # Production environment
│       ├── main.tf, variables.tf, outputs.tf
│       ├── ecr.tf, ecs.tf, alb.tf, dns.tf, autoscaling.tf
│       ├── iam.tf, security.tf, data.tf
│       └── terraform.tfvars      # (gitignored)
├── .github/workflows/            # CI/CD pipelines
│   ├── ci.yml                    # Tests and pre-commit
│   ├── deploy_ecs_testing.yml    # ECS testing deploy (on CI success)
│   ├── deploy_ecs_prod.yml       # ECS prod deploy (on CI success for release)
│   ├── deploy_to_staging.yml     # Lambda staging deploy
│   └── deploy_to_prod.yml        # Lambda production deploy
├── Dockerfile                    # Container image definition
├── .dockerignore                 # Docker build exclusions
├── startServerMac.sh             # Local dev server (macOS)
├── startServerLinux.sh           # Local dev server (Linux)
├── .pre-commit-config.yaml       # Pre-commit hooks config
├── CLAUDE.md                     # AI assistant instructions
└── README.md                     # Project documentation
```

---

## Core Concepts and Data Models

### Entity Hierarchy

```
Organization
└── Has API key for authentication

Quiz
├── title, metadata (quiz_type, subject, grade)
├── settings (shuffle, time_limit, navigation_mode)
└── QuestionSets[]
    ├── title, description
    ├── max_questions_allowed_to_attempt
    ├── marking_scheme (question set level)
    └── Questions[]
        ├── text, type, options, correct_answer
        ├── marking_scheme (question level, overrides set)
        └── metadata (chapter, topic, difficulty)

Session
├── user_id, quiz_id
├── question_order (shuffled indices)
├── events[] (start, resume, end)
├── time_remaining
├── metrics (calculated on end)
└── SessionAnswers[]
    ├── question_id, answer
    ├── visited, time_spent
    └── marked_for_review
```

### Question Types

| Type | Description | Answer Format |
|------|-------------|---------------|
| `single-choice` | Single correct option | `List[int]` (single index) |
| `multi-choice` | Multiple correct options | `List[int]` (multiple indices) |
| `subjective` | Free text response | `str` |
| `numerical-integer` | Integer answer | `int` |
| `numerical-float` | Decimal answer | `float` |
| `matrix-match` | Match columns | `List[str]` |
| `matrix-rating` | Rate items on scale | `dict` |
| `matrix-numerical` | Matrix with numbers | `dict` |
| `matrix-subjective` | Matrix with text | `dict` |

### Quiz Types

| Type | Description |
|------|-------------|
| `assessment` | Formal graded test |
| `homework` | Practice assignment |
| `omr-assessment` | OMR bubble sheet style |
| `form` | Non-graded data collection |

### Navigation Modes

- `linear`: Sequential question navigation
- `non-linear`: Free navigation between questions

---

## API Endpoints

### Quiz Endpoints (`/quiz`)

```
POST   /quiz/                     Create quiz with embedded questions
GET    /quiz/{quiz_id}            Get quiz (validates not a form)
                                  Query params: omr_mode, single_page_mode
```

### Form Endpoints (`/form`)

```
GET    /form/{form_id}            Get form (validates quiz_type is "form")
                                  Query params: omr_mode, single_page_mode
```

### Questions Endpoints (`/questions`)

```
GET    /questions/{question_id}   Get single question
GET    /questions/                Get questions by question_set_id
                                  Query params: question_set_id, skip, limit
```

### Sessions Endpoints (`/sessions`)

```
POST   /sessions/                 Create or resume session
GET    /sessions/{session_id}     Get session details
PATCH  /sessions/{session_id}     Update session (events, metrics)
GET    /sessions/user/{user_id}/quiz-attempts
                                  Get all quiz end statuses for user
```

### Session Answers Endpoints (`/session_answers`)

```
GET    /session_answers/{session_id}/{position_index}
                                  Get answer at position
PATCH  /session_answers/{session_id}/{position_index}
                                  Update single answer
PATCH  /session_answers/{session_id}/update-multiple-answers
                                  Batch update multiple answers
```

### Organizations Endpoints (`/organizations`)

```
POST   /organizations/            Create organization (generates API key)
GET    /organizations/authenticate/{api_key}
                                  Validate API key
```

### Health Endpoint (`/health`)

```
GET    /health                    Lightweight health check for ALB
                                  Returns: {"status": "healthy"}
                                  No DB calls, no auth required
```

---

## Database Schema

### Collections

| Collection | Purpose |
|------------|---------|
| `quizzes` | Quiz definitions with embedded question sets |
| `questions` | Individual questions (stored separately for pagination) |
| `sessions` | User quiz sessions with answers embedded |
| `organization` | Organizations with API keys |
| `marking_presets` | Reusable marking schemes |

### Subset Pattern

Questions are stored using a "subset pattern" for optimization:
- First `subset_size` (default: 10) questions in each set have full details
- Remaining questions have only essential fields (type, correct_answer, marking_scheme)
- Full question details are fetched lazily via `/questions` endpoint

This reduces initial quiz load payload size for large quizzes.

---

## Key Code Files Explained

### `app/main.py`
Entry point for the FastAPI application:
- Request logging middleware (assigns unique request IDs)
- CORS configuration for allowed origins
- GZIP compression for responses > 1KB
- Router registration
- `/health` endpoint for ALB health checks
- Mangum handler for AWS Lambda

### `app/database.py`
MongoDB connection setup with connection pooling:
- `maxPoolSize=20`: Maximum connections per container
- `minPoolSize=5`: Minimum idle connections
- `maxIdleTimeMS=30000`: Close idle connections after 30s
- Retry settings for resilience

### `app/models.py`
Pydantic models for all request/response schemas:
- `Quiz`, `QuestionSet`, `Question`: Quiz structure
- `Session`, `SessionAnswer`: Session tracking
- `Organization`: Auth entities
- `MarkingScheme`, `PartialMarkRule`: Scoring configuration
- `SessionMetrics`, `QuestionSetMetric`: Analytics

### `app/schemas.py`
Enums and custom types:
- `PyObjectId`: Custom ObjectId validator for Pydantic
- `QuestionType`, `QuizType`, `NavigationMode`, `EventType`: Enum definitions
- `TestFormat`, `QuizLanguage`: Additional enums

### `app/routers/sessions.py`
Most complex router - handles session logic:
- `shuffle_question_order()`: Fisher-Yates shuffle in blocks of `subset_size`
- Session creation with resume logic
- Time tracking between events
- Dummy event compression (multiple consecutive dummy events squashed)

### `app/routers/quizzes.py`
Quiz creation and retrieval:
- Stores questions separately in `questions` collection
- Implements subset pattern for large quizzes
- Backwards compatibility updates for old quiz formats
- OMR mode: includes option counts for rendering

### `app/settings.py`
Configurable settings:
- `api_key_length`: 20 characters
- `subset_size`: 10 questions per block

---

## Important Code Patterns

### Session Resume Logic

```python
# Simplified logic from sessions.py
if no_previous_session:
    create_new_session(is_first=True)
elif no_meaningful_event_in_last_session:
    return_last_session()  # Same session, no event
else:
    create_new_session(is_first=False, copy_answers_from_previous)
```

### Question Shuffling

Questions are shuffled in blocks of `subset_size` (10):
```python
# Example: 25 questions, subset_size=10
# Block 1: questions 0-9 shuffled among themselves
# Block 2: questions 10-19 shuffled among themselves
# Block 3: questions 20-24 shuffled among themselves
```

This ensures lazy-loaded questions maintain their block boundaries.

### Marking Scheme Priority

```
Question-level marking_scheme (if present)
    └── overrides
Question-set-level marking_scheme
    └── default fallback
```

### Partial Marking (JEE-style)

```python
# Example partial marking scheme
{
    "correct": 4,
    "wrong": -2,
    "skipped": 0,
    "partial": [
        {
            "conditions": [{"num_correct_selected": 3}],
            "marks": 3
        },
        {
            "conditions": [{"num_correct_selected": 2}],
            "marks": 2
        }
    ]
}
```

---

## Local Development

### Prerequisites

1. MongoDB 6.0 installed locally
2. Python 3.9
3. Virtual environment

### Setup

```bash
# Create and activate virtual environment
virtualenv venv
source venv/bin/activate

# Install dependencies
pip install -r app/requirements.txt

# Set up pre-commit hooks
pip install pre-commit
pre-commit install

# Copy environment variables
cp .env.example .env
```

### Running Locally

**macOS:**
```bash
./startServerMac.sh
```

**Linux:**
```bash
./startServerLinux.sh
```

**Fresh sync from remote DB:**
```bash
./startServerMac.sh --freshSync --source mongodb+srv://user:pass@host/db
```

Server runs at `http://127.0.0.1:8000`
API docs at `http://127.0.0.1:8000/docs`

---

## Testing

### Framework

- **Pytest** for test execution
- **mongomock** for MongoDB mocking
- Test fixtures in `app/tests/dummy_data/`

### Base Test Classes

| Class | Purpose |
|-------|---------|
| `BaseTestCase` | Sets up organizations and quiz types |
| `SessionsBaseTestCase` | Extends with session data |

### Running Tests

```bash
# All tests
pytest

# Single file
pytest app/tests/test_quizzes.py

# Single test by name
pytest -k "test_name"

# With coverage
coverage run --rcfile=.coveragerc -m pytest
coverage xml
```

### Test Data Files

Located in `app/tests/dummy_data/`:
- `homework_quiz.json`
- `assessment_timed.json`
- `multiple_question_set_quiz.json`
- `multiple_question_set_omr_quiz.json`
- `partial_marking_assessment.json`
- `matrix_matching_assessment.json`
- `form_questionnaire.json`
- `organization.json`

---

## Deployment

### Architecture Overview

| Environment | Compute | Infrastructure | Status |
|-------------|---------|----------------|--------|
| **Testing** | ECS Fargate (ARM64) | Terraform | Active |
| **Production** | ECS Fargate (ARM64) | Terraform | Active |
| **Staging** | AWS Lambda | AWS SAM | Active |

### ECS Fargate (Testing Environment)

| Resource | Value |
|----------|-------|
| **API Endpoint** | `https://quiz-backend-testing.avantifellows.org` |
| **ECR Repository** | `111766607077.dkr.ecr.ap-south-1.amazonaws.com/quiz-backend-testing` |
| **ECS Cluster** | `quiz-backend-testing` |
| **Architecture** | ARM64 (Graviton) |
| **Task Size** | 1 vCPU, 2GB RAM |
| **Auto-scaling** | 1–10 tasks, target-tracking on CPU at 50% |
| **Workers** | 4 Uvicorn workers |
| **Health Check** | `/health` endpoint |
| **HTTPS** | Cloudflare proxy (flexible SSL) — terminates TLS at Cloudflare edge, proxies to ALB over HTTP |
| **DNS** | Cloudflare CNAME `quiz-backend-testing.avantifellows.org` → ALB |

#### ECS Deployment (CI/CD)

Automated via `.github/workflows/deploy_ecs_testing.yml`:

1. Triggers after `CI` workflow succeeds on `main` (`workflow_run`)
2. Builds ARM64 Docker image via QEMU/Buildx with GHA layer caching
3. Pushes to ECR with dual tags: git SHA (immutable) + `latest`
4. Fetches live task definition from ECS (preserves env vars set by Terraform)
5. Renders the new image into the task definition
6. Deploys to ECS and waits for service stability
7. Verifies deployment and runs smoke test against `https://quiz-backend-testing.avantifellows.org/health`

```bash
# Manual rollback (if needed)
aws ecs update-service \
  --cluster quiz-backend-testing \
  --service quiz-backend-testing \
  --force-new-deployment
```

### ECS Fargate (Production Environment)

| Resource | Value |
|----------|-------|
| **API Endpoint** | `https://quiz-backend.avantifellows.org` |
| **ECR Repository** | `111766607077.dkr.ecr.ap-south-1.amazonaws.com/quiz-backend-prod` |
| **ECS Cluster** | `quiz-backend-prod` |
| **Architecture** | ARM64 (Graviton) |
| **Task Size** | 1 vCPU, 2GB RAM |
| **Auto-scaling** | 1–10 tasks, target-tracking on CPU at 50% |
| **Workers** | 4 Uvicorn workers |
| **Health Check** | `/health` endpoint |
| **HTTPS** | Cloudflare proxy (flexible SSL) |
| **DNS** | Cloudflare CNAME `quiz-backend.avantifellows.org` → ALB |
| **Log Retention** | 30 days |
| **ALB Deletion Protection** | Enabled |

#### ECS Prod Deployment (CI/CD)

Automated via `.github/workflows/deploy_ecs_prod.yml`:

1. Triggers after `CI` workflow succeeds on `release` (`workflow_run`)
2. Builds ARM64 Docker image via QEMU/Buildx with GHA layer caching
3. Pushes to ECR with dual tags: git SHA (immutable) + `latest`
4. Fetches live task definition from ECS (preserves env vars set by Terraform)
5. Renders the new image into the task definition
6. Deploys to ECS and waits for service stability
7. Verifies deployment and runs smoke test against `https://quiz-backend.avantifellows.org/health`

```bash
# Manual rollback (if needed)
aws ecs update-service \
  --cluster quiz-backend-prod \
  --service quiz-backend-prod \
  --force-new-deployment
```

#### ECS Monitoring Commands

Replace `ENV` with `testing` or `prod` as appropriate.

```bash
# Live monitoring dashboard (refreshes every 15s)
# Shows: ECS tasks, auto-scaling, CPU/Memory, ALB metrics, health check
cd load-testing/quiz-http-api/deployment
./monitor_ecs.sh --profile <aws-profile> [--env testing|prod] [--interval 15]

# Check service status
aws ecs describe-services --cluster quiz-backend-ENV \
  --services quiz-backend-ENV \
  --query 'services[0].{desired:desiredCount,running:runningCount}'

# Tail logs
aws logs tail /ecs/quiz-backend-ENV --follow

# Check task details
aws ecs describe-tasks --cluster quiz-backend-ENV \
  --tasks $(aws ecs list-tasks --cluster quiz-backend-ENV --query 'taskArns[0]' --output text) \
  --query 'tasks[0].{cpu:cpu,memory:memory,lastStatus:lastStatus}'
```

### AWS Lambda (Staging)

- **Compute**: AWS Lambda (Python 3.9, 1024MB, 300s timeout)
- **API**: AWS API Gateway (HTTP API)
- **Database**: MongoDB Atlas (M10 tier, 500 connections)
- **Infrastructure**: AWS SAM (CloudFormation)

#### Lambda Deployment Triggers

| Environment | Trigger |
|-------------|---------|
| Staging | Push/merge to `main` branch |

#### GitHub Actions Workflows

1. **ci.yml**: Pre-commit checks and pytest
2. **deploy_ecs_testing.yml**: Build ARM64 image, push to ECR, update ECS testing service
3. **deploy_ecs_prod.yml**: Build ARM64 image, push to ECR, update ECS prod service
4. **deploy_to_staging.yml**: SAM deploy to Lambda staging
5. **deploy_to_prod.yml**: SAM deploy to Lambda production

#### Required Secrets (GitHub)

- `AWS_ACCESS_KEY_ID` — used by all deploy workflows (IAM user: `quiz-backend`)
- `AWS_SECRET_ACCESS_KEY` — used by all deploy workflows
- `MONGO_AUTH_CREDENTIALS` — used by Lambda SAM deploys only (ECS gets it from the live task definition)

#### Lambda Deployment Commands (Manual)

```bash
# Build
sam build --use-container -t templates/staging.yaml

# Deploy
sam deploy --stack-name QuizBackendStaging \
  --s3-bucket quiz-staging-backend \
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides MongoAuthCredentials=$MONGO_AUTH_CREDENTIALS
```

---

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `MONGO_AUTH_CREDENTIALS` | MongoDB connection URI |

Example:
```
MONGO_AUTH_CREDENTIALS="mongodb+srv://USER:PASS@cluster.mongodb.net/quiz?retryWrites=true&w=majority"
```

### CORS Origins

Configured in `main.py`:
- `http://localhost:8080`
- `http://localhost:8081`
- `http://localhost:3000`
- `https://staging-quiz.avantifellows.org`
- `https://quiz.avantifellows.org`
- `https://staging-gurukul.avantifellows.org`
- `https://gurukul.avantifellows.org`

### Pre-commit Hooks

- `trailing-whitespace`
- `end-of-file-fixer`
- `check-json`, `check-yaml`
- `check-merge-conflict`
- `check-added-large-files`
- `black` (code formatting)
- `flake8` (linting, ignores E501, E203, W503)
- `tflint` (Terraform)
- `cfn-python-lint` (CloudFormation)

---

## Logging

### Configuration (`logger_config.py`)

- Logger name: `quizenginelogger`
- Level: DEBUG
- Timezone: IST (UTC+5:30)
- Format includes: timestamp, level, filename, function, line, message, call trace

### Log Format

```
2024-01-15 10:30:45 IST loglevel=INFO   filename=sessions.py funcName=create_session() L68 Creating new session for user: 123
```

### Request Tracking

Each HTTP request is assigned a unique ID (`rid`) for tracing:
```
rid=ABC123 start request path=/quiz/xyz method=GET
rid=ABC123 completed_in=45.23ms status_code=200
```

### Log Shipping (Production)

Logs are shipped to Loki via Lambda Promtail for centralized logging and Grafana dashboards.

---

## ECS vs Lambda

Testing and production run on ECS Fargate. Staging runs on Lambda.

**Why ECS Fargate for testing/production:**
- Connection pooling (20 connections per container vs 1 per Lambda invocation)
- Stays on MongoDB M10 tier for most scenarios
- Lower latency (no cold starts)
- Cost savings (~$75-130/month)

Both ECS environments have: Terraform IaC, S3 remote state, CI/CD pipelines, custom domains, HTTPS via Cloudflare proxy, auto-scaling (1–10 tasks on CPU). Production additionally has 30-day log retention and ALB deletion protection.

**Load-tested capacity (testing environment):**
- 5,000 concurrent users on 10 pre-scaled tasks: 474 RPS, p50 60ms, p95 400ms (steady-state p95 ~100ms), 0.004% failure rate
- Each task handles ~500-700 concurrent users at sub-110ms p95
- MongoDB connections scale from ~100 (idle) to ~350 (under load) on M10 tier
- Auto-scaling alarm evaluation takes ~5 min; for planned load events, pre-scale with `aws ecs update-service --desired-count N`
- Load test reports: `load-testing/quiz-http-api/reports/`

---

## Quick Reference

### Common Development Tasks

```bash
# Start server
./startServerMac.sh

# Run tests
pytest

# Format code
black app/

# Lint
flake8 app/

# Run pre-commit on all files
pre-commit run --all-files
```

### Important Files to Edit

| Task | File(s) |
|------|---------|
| Add new endpoint | `app/routers/`, `app/main.py` |
| Add new model | `app/models.py` |
| Add new enum | `app/schemas.py` |
| Add new setting | `app/settings.py` |
| Database config | `app/database.py` |
| Add test | `app/tests/test_*.py` |
| Add test fixture | `app/tests/dummy_data/*.json` |
| ECS infrastructure | `terraform/testing/*.tf`, `terraform/prod/*.tf` |
| Container config | `Dockerfile` |

### Key Contacts

- **Organization**: Avanti Fellows
- **Repository**: https://github.com/avantifellows/quiz-backend
- **License**: GPL v3
- **Discord**: https://discord.gg/29qYD7fZtZ

---

*This document is maintained as part of the quiz-backend repository. Update it when making significant changes to the project.*
