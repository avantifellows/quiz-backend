# ECS Migration — Status & Next Steps

> **Last reviewed:** February 7, 2026
> **Branch:** `docs/migration-lambda-to-ecs` (merged with main)
> **Reference:** `context_for_ai/plans/ecs-migration-implementation-plan.md`

---

## Current State Summary

### What's deployed

**Testing** and **production** ECS Fargate environments are both live. Staging still runs on Lambda via SAM. Production Lambda remains active until traffic cutover.

| Resource | Testing | Production |
|----------|---------|------------|
| API Endpoint | `https://quiz-backend-testing.avantifellows.org` | `https://quiz-backend.avantifellows.org` |
| ECR Repository | `quiz-backend-testing` | `quiz-backend-prod` |
| ECS Cluster | `quiz-backend-testing` | `quiz-backend-prod` |
| Architecture | ARM64 (Graviton) | ARM64 (Graviton) |
| Task Size | 1 vCPU, 2 GB RAM | 1 vCPU, 2 GB RAM |
| Auto-scaling | 1–10 tasks, CPU 50% | 1–10 tasks, CPU 50% |
| Log Retention | 7 days | 30 days |
| ALB Deletion Protection | No | Yes |
| CloudWatch Logs | `/ecs/quiz-backend-testing` | `/ecs/quiz-backend-prod` |
| Terraform State | `s3://…/testing/terraform.tfstate` | `s3://…/prod/terraform.tfstate` |
| Deploy Trigger | Push to `main` (after CI) | Push to `release` (after CI) |

### What exists in the codebase

| Artifact | Status | Location |
|----------|--------|----------|
| Terraform IaC (13 files) | Complete | `terraform/testing/` |
| Terraform state (testing) | S3 backend | `s3://quiz-terraform-state-111766607077/testing/terraform.tfstate` |
| Terraform state (prod) | S3 backend | `s3://quiz-terraform-state-111766607077/prod/terraform.tfstate` |
| State backend bootstrap IaC | Complete | `terraform/shared/state-backend/` |
| Dockerfile | Complete | repo root |
| .dockerignore | Complete | repo root |
| database.py connection pooling | Complete | `app/database.py` |
| Migration proposal doc | Complete | `docs/MIGRATION_LAMBDA_TO_ECS.md` |
| Implementation plan | Complete | `context_for_ai/plans/ecs-migration-implementation-plan.md` |
| ECS deploy workflow (testing) | Complete | `.github/workflows/deploy_ecs_testing.yml` |
| Terraform IaC (prod) | Complete | `terraform/prod/` |
| ECS deploy workflow (prod) | Complete | `.github/workflows/deploy_ecs_prod.yml` |

### What's still running (Lambda — Staging + Production legacy)

| Pipeline | Trigger | Template |
|----------|---------|----------|
| Staging deploy (Lambda) | Push/PR to `main` | `templates/staging.yaml` (1024 MB Lambda) |
| Production deploy (Lambda) | Push to `release` | `templates/prod.yaml` (2048 MB Lambda) |
| CI | Push/PR to `main` | `.github/workflows/ci.yml` |

> **Note:** Production Lambda and ECS prod both deploy on push to `release`. Both will run in parallel until Lambda is decommissioned.

### Config differences: plan vs. actual

| Config | Plan document | Actual (tfvars) |
|--------|---------------|-----------------|
| CPU | 0.5 vCPU (512) | 1 vCPU (1024) |
| Memory | 1 GB (1024) | 2 GB (2048) |
| Health check path | `/docs` | `/health` |
| Architecture | ARM64 | ARM64 |
| Region | ap-south-1 | ap-south-1 |

### Known risks

1. ~~**Terraform state is local** — if lost, infrastructure management breaks.~~ Resolved — migrated to S3 with DynamoDB locking (Feb 6, 2026).
2. ~~**No HTTPS** — ALB serves plain HTTP on port 80.~~ Resolved — HTTPS via Cloudflare proxy (Feb 7, 2026).
3. **Real MongoDB credentials** sit in `terraform.tfvars` locally (excluded from git by `.gitignore`).
4. ~~**No CI/CD for ECS** — deploys are manual `docker build` + `terraform apply`.~~ Resolved — GitHub Actions workflow deploys on push (Feb 6, 2026).
5. ~~**No auto-scaling** — fixed task count of 1.~~ Resolved — target-tracking on CPU at 50%, min=1 max=10 (Feb 7, 2026).

---

## Next Steps

These are the outstanding items from the original migration plan, prioritized for pickup.

### ~~Step 1: S3 Backend for Terraform State~~ — Done (Feb 6, 2026)

**What was done:**
- Created bootstrap Terraform config at `terraform/shared/state-backend/` (4 files: `main.tf`, `s3.tf`, `dynamodb.tf`, `outputs.tf`)
- S3 bucket `quiz-terraform-state-111766607077` with versioning, AES256 encryption, public access blocked, 90-day noncurrent version expiry
- DynamoDB table `terraform-locks` (already existed, shared with etl-next and discord-concierge — imported into state)
- Migrated `terraform/testing/` from local state to S3 backend — all 20 resources verified, `terraform plan` shows no changes
- Updated `terraform/.gitignore` to commit bootstrap state files
- Bootstrap config uses local state (committed to git) — standard pattern

---

### ~~Steps 2 & 5: Custom Domain + HTTPS~~ — Done (Feb 7, 2026)

**What was done:**
- Domain: `quiz-backend-testing.avantifellows.org`
- DNS managed via Cloudflare (not Route53) — CNAME record pointing to ALB
- Cloudflare proxy (orange cloud) enabled — terminates TLS and proxies to ALB over HTTP
- Page rule sets SSL to "Flexible" for this hostname (ALB only has an HTTP listener; zone-level SSL is "Full")
- No ACM certificate needed — Cloudflare handles HTTPS automatically
- Added Cloudflare provider (`cloudflare/cloudflare ~> 4.0`) to `terraform/testing/main.tf`
- Added variables: `cloudflare_api_key` (sensitive), `cloudflare_email`, `cloudflare_zone_name`
- New file: `terraform/testing/dns.tf` (data source for zone lookup, CNAME record, page rule)
- New output: `app_url` = `https://quiz-backend-testing.avantifellows.org`
- Smoke test in CI/CD updated to use `https://quiz-backend-testing.avantifellows.org/health`
- Verified: `curl` returns `{"status":"healthy"}` with Cloudflare headers

---

### ~~Step 3: Auto-Scaling~~ — Done (Feb 7, 2026)

**What was done:**
- Created `terraform/testing/autoscaling.tf` with target-tracking scaling policy
- `aws_appautoscaling_target`: min=1, max=10 tasks
- `aws_appautoscaling_policy`: tracks `ECSServiceAverageCPUUtilization` at 50% target
- When average CPU exceeds 50%, ECS spins up additional tasks; scales back in when load drops
- `ecs.tf` already had `lifecycle { ignore_changes = [desired_count] }` — no conflict with autoscaler

---

### ~~Step 4: CI/CD Pipeline for ECS Deployments~~ — Done (Feb 6, 2026)

**What was done:**
- Created `.github/workflows/deploy_ecs_testing.yml` — full build-and-deploy pipeline
- Triggers: `workflow_run` after CI succeeds on `main` (primary), plus temporary `push` trigger on `docs/migration-lambda-to-ecs` (remove after merge)
- Builds ARM64 image via QEMU/Buildx with GHA layer caching (~2 min cached builds)
- Dual-tags images: git SHA (immutable) + `latest` (keeps Terraform reference valid)
- Fetches live task definition from ECS (preserves Terraform-managed env vars like `MONGO_AUTH_CREDENTIALS`)
- Registers new task def revision, updates ECS service, waits for stability
- Includes deployment verification and ALB smoke test (skips gracefully if service is scaled to 0)
- Added `ecs-deploy` inline IAM policy to `quiz-backend` IAM user (via CLI) with ECR, ECS, and `iam:PassRole` permissions
- Successfully tested: all 12 steps pass, new task def revision deployed and healthy

---

### ~~Step 6: Create Production ECS Environment~~ — Done (Feb 7, 2026)

**What was done:**
- Copied `terraform/testing/` to `terraform/prod/` (11 .tf files + lock file)
- Production-specific changes: S3 state key `prod/terraform.tfstate`, log retention 30 days, ALB deletion protection enabled
- Domain: `quiz-backend.avantifellows.org` (dns.tf hardcodes `quiz-backend` instead of `quiz-backend-${var.environment}`)
- Created `terraform/prod/terraform.tfvars` with prod values, `terraform/prod/terraform.tfvars.example` as template
- `terraform apply` — 19 resources created (ECR, ECS cluster/service/task def, ALB, target group, listener, security groups, IAM roles, CloudWatch log group, Cloudflare CNAME + page rule, autoscaling target + policy)
- Created `.github/workflows/deploy_ecs_prod.yml` — triggers on `release` branch (via `workflow_run` after CI) + temporary `docs/migration-lambda-to-ecs` push trigger
- Updated IAM `ecs-deploy` inline policy on `quiz-backend` user (via CLI) — added `quiz-backend-prod` ECR repo and both prod ECS roles to the existing testing permissions
- First CI/CD deploy triggered and succeeded — all 12 workflow steps passed including smoke test
- Verified: `curl https://quiz-backend.avantifellows.org/health` → `{"status":"healthy"}`

---

### ~~Step 7: Load Testing~~ — Done (Feb 7, 2026)

**What was done:**
- Updated existing Locust load test suite (`load-testing/quiz-http-api/`) to match recent backend changes (session timing fields, matrix question types, SinglePageQuizUser class)
- Updated backend URL from direct ALB to `https://quiz-backend-testing.avantifellows.org` (Cloudflare)
- Local smoke test passed (1 user, 8 requests, 0 failures)
- Deployed Locust to EC2 (c5.9xlarge, 32 workers) via `run_on_server.sh`
- Created `deployment/monitor_ecs.sh` — terminal-based ECS monitoring script (service status, CloudWatch CPU/Memory, ALB metrics, auto-scaling state, health check)

**Load test: 5,000 concurrent users, 50 u/s ramp-up, 10 pre-scaled ECS tasks**
- **133,244 requests**, **474 RPS** avg, **5 failures** (0.004% — all on session end)
- p50 **60ms**, p95 **400ms** (inflated by ramp-up thundering herd; steady-state p95 ~100ms)
- CPU peaked ~65% across 10 tasks, memory stable at ~11%
- MongoDB connections: 100 → 350 during test (M10 staging tier)
- Zero ALB 5xx errors, health check stayed at 200 OK throughout
- Session end remains the slowest endpoint (p50 3,400ms) — known pattern, metrics calculation is heavy

**Auto-scaling observations:**
- Target tracking alarm took ~5 min to trigger after CPU exceeded 50% (3 consecutive 60s evaluation periods + CloudWatch lag)
- For planned load events (exam start), pre-scaling with `aws ecs update-service --desired-count N` is recommended
- Each task comfortably handles ~500-700 concurrent users at sub-110ms p95

**Full report:** `load-testing/quiz-http-api/reports/07-02-2026/report_2026-02-07.md`

---

## Suggested pickup order

| Priority | Step | Reason |
|----------|------|--------|
| ~~1~~ | ~~S3 Backend~~ | ~~Done (Feb 6, 2026)~~ |
| ~~2~~ | ~~CI/CD Pipeline~~ | ~~Done (Feb 6, 2026)~~ |
| ~~3~~ | ~~Custom Domain + HTTPS~~ | ~~Done (Feb 7, 2026) — Cloudflare proxy~~ |
| ~~4~~ | ~~Auto-Scaling~~ | ~~Done (Feb 7, 2026) — CPU target-tracking~~ |
| ~~5~~ | ~~Production Environment~~ | ~~Done (Feb 7, 2026) — fully deployed, CI/CD verified, health check passing~~ |
| ~~6~~ | ~~Load Testing~~ | ~~Done (Feb 7, 2026) — 5k users, 474 RPS, 0.004% failure rate~~ |
| ~~7~~ | ~~Infra parity audit~~ | ~~Done (Feb 7, 2026) — all 11 .tf files verified, 6 identical, 5 with expected env-specific diffs only~~ |
| ~~8~~ | ~~Workflow audit~~ | ~~Done (Feb 7, 2026) — workflows identical except 5 env-specific values, triggers correct~~ |
| ~~9~~ | ~~PRs with full descriptions~~ | ~~Done (Feb 7, 2026) — quiz-backend#130 + load-testing#5, cross-linked~~ |
| ~~10~~ | ~~Frontend backend switcher~~ | ~~Done (Feb 7, 2026) — quiz-frontend#198, cross-linked with quiz-backend#130~~ |
| 11 | Scheduled scaling from sheet | Set up a flow (separate repo) that reads from a Google Sheet and sets min/desired/max for ECS clusters on a schedule |

---

### ~~Step 8: Infra Parity Audit~~ — Done (Feb 7, 2026)

**What was done:**
- Diffed all 11 `.tf` files between `terraform/testing/` and `terraform/prod/`
- **6 files identical:** `autoscaling.tf`, `data.tf`, `ecr.tf`, `iam.tf`, `outputs.tf`, `security.tf`, `variables.tf` — IAM roles/policies, auto-scaling targets/policies, and security group rules all match
- **5 files with expected env-specific differences only:**
  - `main.tf` — state key path (`testing/` vs `prod/`)
  - `ecs.tf` — log retention (7 vs 30 days)
  - `alb.tf` — deletion protection (false vs true)
  - `dns.tf` — domain name (`quiz-backend-${var.environment}` vs hardcoded `quiz-backend`) — intentional, prod domain is `quiz-backend.avantifellows.org`
  - `terraform.tfvars.example` — env name, mongo URI, task size
- **Fix applied:** Updated `terraform/testing/terraform.tfvars.example` task size from 512/1024 to 1024/2048 to match actual deployment

---

### ~~Step 9: Workflow Audit~~ — Done (Feb 7, 2026)

**What was done:**
- Diffed `deploy_ecs_testing.yml` vs `deploy_ecs_prod.yml` — structurally identical
- **5 env-specific differences only:**
  - Workflow name (`Deploy to ECS Testing` vs `Deploy to ECS Prod`)
  - Trigger branch (`main` vs `release`)
  - 4 env vars (`ECR_REPOSITORY`, `ECS_CLUSTER`, `ECS_SERVICE`, `TASK_DEFINITION_FAMILY` — all `quiz-backend-testing` vs `quiz-backend-prod`)
  - Smoke test URL (`quiz-backend-testing.avantifellows.org` vs `quiz-backend.avantifellows.org`)
- Triggers confirmed correct: testing fires on CI success for `main`, prod fires on CI success for `release`
- Lambda workflows (`deploy_to_staging.yml`, `deploy_to_prod.yml`) remain active — do not remove until cutover

---

### ~~Step 10: PRs with Full Descriptions~~ — Done (Feb 7, 2026)

**What was done:**
- **quiz-backend PR:** [avantifellows/quiz-backend#130](https://github.com/avantifellows/quiz-backend/pull/130) — updated title and description covering all Terraform, Dockerfile, CI/CD, app code changes, architecture diagram, load test results, and test plan
- **load-testing PR:** [avantifellows/load-testing#5](https://github.com/avantifellows/load-testing/pull/5) — new branch `feature/quiz-http-api-load-testing` with full description of quiz-http-api module, quiz-mongo updates, deployment scripts, and load test reports
- Both PRs cross-link each other

---

### ~~Step 11: Frontend Backend Switcher~~ — Done (Feb 7, 2026)

**What was done:**
- **PR:** [avantifellows/quiz-frontend#198](https://github.com/avantifellows/quiz-frontend/pull/198) — branch `feature/ecs-backend-switcher`
- Modified `src/services/API/RootClient.ts` — extracted `createClient()` factory, creates two Axios clients (default Lambda + ECS), `apiClient()` checks `window.location.search` for `new_backend` param
- ECS backend URLs hardcoded in CI/CD workflows (not secrets — they're public):
  - Staging: `https://quiz-backend-testing.avantifellows.org`
  - Production: `https://quiz-backend.avantifellows.org`
- Added `VUE_APP_BACKEND_ECS` to `.env.example`
- Safe fallback: if `VUE_APP_BACKEND_ECS` is not set, the query param is ignored
- Usage: append `&new_backend=true` to any quiz URL to route API calls to ECS
- Cross-linked with [quiz-backend#130](https://github.com/avantifellows/quiz-backend/pull/130)

---

### Step 12: Scheduled Scaling from Sheet

**Why:** For planned exam events, ECS tasks should be pre-scaled ahead of time rather than relying on reactive auto-scaling (which has ~5 min delay). A Google Sheet-driven flow allows non-engineers to schedule scaling.

**Scope:**
- A flow (in a separate repo) reads scaling schedules from a Google Sheet
- Sets min, desired, and max capacity for testing or production ECS clusters on the defined schedule
- Lightweight mention here — implementation lives elsewhere
