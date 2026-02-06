# ECS Migration — Status & Next Steps

> **Last reviewed:** February 6, 2026
> **Branch:** `docs/migration-lambda-to-ecs` (merged with main)
> **Reference:** `context_for_ai/plans/ecs-migration-implementation-plan.md`

---

## Current State Summary

### What's deployed

A **testing-only** ECS Fargate environment was stood up on January 3, 2026. Production and staging still run on Lambda via SAM.

| Resource | Value |
|----------|-------|
| API Endpoint | `http://quiz-backend-testing-1700268315.ap-south-1.elb.amazonaws.com` |
| ECR Repository | `111766607077.dkr.ecr.ap-south-1.amazonaws.com/quiz-backend-testing` |
| ECS Cluster | `quiz-backend-testing` |
| Architecture | ARM64 (Graviton) |
| Task Size | 1 vCPU, 2 GB RAM |
| Desired Count | 1 |
| CloudWatch Logs | `/ecs/quiz-backend-testing` |

### What exists in the codebase

| Artifact | Status | Location |
|----------|--------|----------|
| Terraform IaC (all 10 files) | Complete | `terraform/testing/` |
| Terraform state | S3 backend | `s3://quiz-terraform-state-111766607077/testing/terraform.tfstate` |
| State backend bootstrap IaC | Complete | `terraform/shared/state-backend/` |
| Dockerfile | Complete | repo root |
| .dockerignore | Complete | repo root |
| database.py connection pooling | Complete | `app/database.py` |
| Migration proposal doc | Complete | `docs/MIGRATION_LAMBDA_TO_ECS.md` |
| Implementation plan | Complete | `context_for_ai/plans/ecs-migration-implementation-plan.md` |

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
2. **No HTTPS** — ALB serves plain HTTP on port 80.
3. **Real MongoDB credentials** sit in `terraform.tfvars` locally (excluded from git by `.gitignore`).
4. **No CI/CD for ECS** — deploys are manual `docker build` + `terraform apply`.
5. **No auto-scaling** — fixed task count of 1.

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

### Step 2: HTTPS (ACM Certificate + HTTPS Listener)

**Why:** The API is currently served over plain HTTP. Any environment beyond testing must have TLS.

**Scope:**
- Request an ACM certificate (or use an existing one) for the desired domain
- Add an HTTPS listener (port 443) to the ALB
- Redirect HTTP (port 80) to HTTPS
- Update `terraform/testing/alb.tf`

**Files to change:**
- `terraform/testing/alb.tf` (add HTTPS listener, redirect rule)
- Possibly new `acm.tf` if creating a certificate via Terraform

**Prerequisite:** A custom domain must be decided (Step 5) for ACM validation, unless using the raw ALB DNS with a wildcard.

---

### Step 3: Auto-Scaling

**Why:** Fixed count of 1 won't handle traffic spikes (the whole reason for migrating off Lambda).

**Scope:**
- Add `aws_appautoscaling_target` and `aws_appautoscaling_policy` resources
- Use target-tracking on CPU utilization (e.g., target 70%)
- Set min=1, max=4 for testing (adjust for prod)
- Update `terraform/testing/ecs.tf` or create a new `autoscaling.tf`

**Files to change:**
- New `terraform/testing/autoscaling.tf` or additions to `ecs.tf`

---

### Step 4: CI/CD Pipeline for ECS Deployments

**Why:** Manual `docker build` + `push` + `terraform apply` is error-prone and unsustainable.

**Scope:**
- Create a GitHub Actions workflow for ECS deployment
- On push to `main`: build Docker image, push to ECR, update ECS service
- Use `aws-actions/amazon-ecr-login` and `aws-actions/amazon-ecs-deploy-task-definition`
- Keep the existing Lambda CI/CD workflows until full migration is done

**Files to create:**
- `.github/workflows/deploy_ecs_testing.yml`
- Later: `deploy_ecs_staging.yml`, `deploy_ecs_prod.yml`

---

### Step 5: Custom Domain (Route53)

**Why:** Raw ALB DNS names are not user-friendly and change if the ALB is recreated.

**Scope:**
- Decide on domain/subdomain (e.g., `api-testing.yourdomain.com`)
- Create Route53 hosted zone (if not existing) and A/AAAA alias record pointing to ALB
- This unblocks ACM DNS validation for HTTPS (Step 2)

**Files to change:**
- New `terraform/testing/dns.tf` or `route53.tf`

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
| 2 | CI/CD Pipeline | Unblock iterative deploys for all subsequent steps |
| 3 | Custom Domain | Required for ACM cert validation |
| 4 | HTTPS | Security requirement, depends on domain |
| 5 | Auto-Scaling | Production-readiness |
| 6 | Staging & Prod Environments | Duplicate tested infra to higher environments |
| 7 | Load Testing | Final validation before traffic cutover |
