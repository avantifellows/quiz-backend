# ECS Migration — Status & Next Steps

> **Last reviewed:** February 7, 2026
> **Branch:** `docs/migration-lambda-to-ecs` (merged with main)
> **Reference:** `context_for_ai/plans/ecs-migration-implementation-plan.md`

---

## Current State Summary

### What's deployed

A **testing-only** ECS Fargate environment was stood up on January 3, 2026. Production and staging still run on Lambda via SAM.

| Resource | Value |
|----------|-------|
| API Endpoint | `https://quiz-backend-testing.avantifellows.org` |
| ECR Repository | `111766607077.dkr.ecr.ap-south-1.amazonaws.com/quiz-backend-testing` |
| ECS Cluster | `quiz-backend-testing` |
| Architecture | ARM64 (Graviton) |
| Task Size | 1 vCPU, 2 GB RAM |
| Desired Count | 1 (auto-scales 1–10 on CPU) |
| CloudWatch Logs | `/ecs/quiz-backend-testing` |

### What exists in the codebase

| Artifact | Status | Location |
|----------|--------|----------|
| Terraform IaC (13 files) | Complete | `terraform/testing/` |
| Terraform state | S3 backend | `s3://quiz-terraform-state-111766607077/testing/terraform.tfstate` |
| State backend bootstrap IaC | Complete | `terraform/shared/state-backend/` |
| Dockerfile | Complete | repo root |
| .dockerignore | Complete | repo root |
| database.py connection pooling | Complete | `app/database.py` |
| Migration proposal doc | Complete | `docs/MIGRATION_LAMBDA_TO_ECS.md` |
| Implementation plan | Complete | `context_for_ai/plans/ecs-migration-implementation-plan.md` |
| ECS deploy workflow | Complete | `.github/workflows/deploy_ecs_testing.yml` |

### What's still running (Lambda — Production/Staging)

| Pipeline | Trigger | Template |
|----------|---------|----------|
| Staging deploy | Push/PR to `main` | `templates/staging.yaml` (1024 MB Lambda) |
| Production deploy | Push to `release` | `templates/prod.yaml` (2048 MB Lambda) |
| CI | Push/PR to `main` | `.github/workflows/ci.yml` |

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

### Step 6: Create Staging & Production ECS Environments

**Why:** Testing is a proof-of-concept. Staging and production need their own isolated infrastructure.

**Scope:**
- Copy `terraform/testing/` to `terraform/staging/` and `terraform/prod/`
- Adjust `terraform.tfvars` per environment (task size, desired count, MongoDB URI)
- Consider extracting shared config into Terraform modules to reduce duplication

**Files to create:**
- `terraform/staging/` (full set)
- `terraform/prod/` (full set)
- Optionally `terraform/modules/ecs-service/` for shared logic

---

### Step 7: Load Testing

**Why:** The migration's core promise is better connection handling. This needs to be validated before cutting over production traffic.

**Scope:**
- Run load tests against the ECS testing endpoint
- Verify MongoDB connection pooling holds under concurrent load
- Monitor CloudWatch metrics (CPU, memory, connection count)
- Compare latency and error rates vs. Lambda

**Tools:** k6, Locust, or Artillery

---

## Suggested pickup order

| Priority | Step | Reason |
|----------|------|--------|
| ~~1~~ | ~~S3 Backend~~ | ~~Done (Feb 6, 2026)~~ |
| ~~2~~ | ~~CI/CD Pipeline~~ | ~~Done (Feb 6, 2026)~~ |
| ~~3~~ | ~~Custom Domain + HTTPS~~ | ~~Done (Feb 7, 2026) — Cloudflare proxy~~ |
| ~~4~~ | ~~Auto-Scaling~~ | ~~Done (Feb 7, 2026) — CPU target-tracking~~ |
| 5 | Staging & Prod Environments | Duplicate tested infra to higher environments |
| 6 | Load Testing | Final validation before traffic cutover |
