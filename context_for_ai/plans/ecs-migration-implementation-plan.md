# ECS Migration Implementation Plan

> **Environment:** Testing
> **Region:** ap-south-1
> **Infrastructure:** Terraform
> **Created:** January 3, 2026
> **Last Updated:** January 3, 2026
> **Status:** ✅ COMPLETED

---

## Implementation Summary

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1: Terraform Foundation & ECR | ✅ Complete | All infrastructure files created |
| Phase 2: Docker Setup | ✅ Complete | Dockerfile, .dockerignore, database.py updated |
| Phase 3: IAM & Security Groups | ✅ Complete | Roles and security groups created |
| Phase 4: Application Load Balancer | ✅ Complete | ALB with health checks configured |
| Phase 5: ECS Cluster & Service | ✅ Complete | Running on ARM64 (Graviton) |
| Phase 6: Testing & Validation | ✅ Complete | API responding correctly |

### Current Deployment

| Resource | Value |
|----------|-------|
| **API Endpoint** | http://quiz-backend-testing-1700268315.ap-south-1.elb.amazonaws.com |
| **ECR Repository** | 111766607077.dkr.ecr.ap-south-1.amazonaws.com/quiz-backend-testing |
| **ECS Cluster** | quiz-backend-testing |
| **ECS Service** | quiz-backend-testing |
| **Task Definition** | quiz-backend-testing:3 |
| **Architecture** | ARM64 (Graviton) |
| **Task Size** | 0.5 vCPU, 1GB RAM |
| **CloudWatch Logs** | /ecs/quiz-backend-testing |

---

## Overview

This plan implements the Lambda to ECS Fargate migration outlined in `docs/MIGRATION_LAMBDA_TO_ECS.md` for a testing environment.

### Key Decisions

| Aspect | Decision |
|--------|----------|
| Terraform State | Local (S3 backend to be added later) |
| VPC | Default VPC |
| MongoDB | Staging DB (URL via tfvars) |
| DNS | ALB URL directly (no custom domain) |
| Scaling | Fixed task count (no auto-scaling) |
| CI/CD | Manual Terraform deployments |
| Secrets | Via tfvars (no Secrets Manager) |
| **Architecture** | **ARM64 (Graviton) - ~20% cost savings** |

---

## Issues Encountered & Resolutions

### Issue 1: ALB Subnet Conflict

**Error:** `A load balancer cannot be attached to multiple subnets in the same Availability Zone`

**Cause:** The default VPC had multiple subnets, some in the same AZ.

**Resolution:** Updated `data.tf` to filter for only default subnets (one per AZ):
```hcl
data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}
```

### Issue 2: Docker Architecture Mismatch

**Error:** `exec /usr/local/bin/uvicorn: exec format error`

**Cause:** Docker image built on Mac M-series (ARM64) but ECS was initially configured for x86_64.

**Resolution:**
1. Initially rebuilt with `--platform linux/amd64`
2. Later switched to ARM64 (Graviton) for cost savings

### Issue 3: MongoDB URI Format

**Error:** `pymongo.errors.InvalidURI: Invalid URI scheme: URI must begin with 'mongodb://' or 'mongodb+srv://'`

**Cause:** Extra quotes or formatting in terraform.tfvars

**Resolution:** Ensure tfvars has proper format:
```hcl
# Correct
mongo_auth_credentials = "mongodb+srv://user:pass@cluster/db"

# Wrong - extra quotes
mongo_auth_credentials = "\"mongodb+srv://...\""
```

### Issue 4: Terraform deployment_configuration Block

**Error:** `Blocks of type "deployment_configuration" are not expected here`

**Cause:** AWS provider 5.x changed the syntax

**Resolution:** Changed from block to attributes:
```hcl
# Old (doesn't work in provider 5.x)
deployment_configuration {
  maximum_percent         = 200
  minimum_healthy_percent = 100
}

# New
deployment_maximum_percent         = 200
deployment_minimum_healthy_percent = 100
```

---

## Phase 1: Terraform Foundation & ECR ✅

**Status:** Complete

### Files Created

```
terraform/
├── .gitignore
└── testing/
    ├── main.tf
    ├── variables.tf
    ├── outputs.tf
    ├── terraform.tfvars.example
    ├── data.tf
    ├── ecr.tf
    ├── iam.tf
    ├── security.tf
    ├── alb.tf
    └── ecs.tf
```

### Verification

- [x] Terraform initializes without errors
- [x] ECR repository created: `quiz-backend-testing`
- [x] ECR repository URL is output

---

## Phase 2: Docker Setup ✅

**Status:** Complete

### Files Created/Modified

- [x] `Dockerfile` - Created in repo root
- [x] `.dockerignore` - Created in repo root
- [x] `app/database.py` - Updated with connection pooling

### database.py Changes

```python
client = MongoClient(
    os.getenv("MONGO_AUTH_CREDENTIALS"),
    maxPoolSize=20,
    minPoolSize=5,
    maxIdleTimeMS=30000,
    connectTimeoutMS=5000,
    serverSelectionTimeoutMS=5000,
    retryWrites=True,
    retryReads=True,
)
```

### Verification

- [x] Docker image builds successfully
- [x] Image pushed to ECR successfully
- [x] Image visible in AWS Console

---

## Phase 3: IAM & Security Groups ✅

**Status:** Complete

### Resources Created

- [x] IAM role: `quiz-backend-testing-ecs-task-execution`
- [x] IAM role: `quiz-backend-testing-ecs-task`
- [x] IAM policy: `ecs-exec` (for debugging)
- [x] Security group: `quiz-backend-testing-alb` (allows port 80)
- [x] Security group: `quiz-backend-testing-ecs-tasks` (allows 8000 from ALB)

---

## Phase 4: Application Load Balancer ✅

**Status:** Complete

### Resources Created

- [x] ALB: `quiz-backend-testing`
- [x] Target group: `quiz-backend-testing` (health check on `/docs`)
- [x] HTTP listener on port 80

### ALB DNS

```
quiz-backend-testing-1700268315.ap-south-1.elb.amazonaws.com
```

---

## Phase 5: ECS Cluster & Service ✅

**Status:** Complete (ARM64)

### Resources Created

- [x] ECS Cluster: `quiz-backend-testing`
- [x] CloudWatch Log Group: `/ecs/quiz-backend-testing`
- [x] Task Definition: `quiz-backend-testing:3` (ARM64)
- [x] ECS Service: `quiz-backend-testing`

### Task Definition Configuration

```hcl
runtime_platform {
  operating_system_family = "LINUX"
  cpu_architecture        = "ARM64"
}
```

### Current Task Status

```
Cluster: quiz-backend-testing
Service: quiz-backend-testing
  - Desired: 1
  - Running: 1
  - Task Definition: quiz-backend-testing:3
  - Architecture: ARM64 (Graviton)
```

---

## Phase 6: Testing & Validation ✅

**Status:** Complete

### Verification Results

- [x] `/docs` returns 200 and shows Swagger UI
- [x] Application startup logs show 4 Uvicorn workers
- [x] CloudWatch logs show requests being processed
- [x] No MongoDB connection errors in logs
- [x] ALB target group shows healthy targets

### Test Commands

```bash
# Test API docs
curl http://quiz-backend-testing-1700268315.ap-south-1.elb.amazonaws.com/docs
# Returns: 200 OK with Swagger UI HTML

# Check service status
aws ecs describe-services --cluster quiz-backend-testing --services quiz-backend-testing \
  --query 'services[0].{status:status,running:runningCount,desired:desiredCount}'
# Returns: {"status": "ACTIVE", "running": 1, "desired": 1}
```

---

## Quick Reference Commands

### Deployment Commands

```bash
# Navigate to terraform directory
cd terraform/testing

# Initialize (first time only)
terraform init

# Preview changes
terraform plan

# Apply changes
terraform apply

# Show outputs
terraform output
```

### Docker Commands (ARM64)

```bash
# Build ARM64 image (on Mac M-series, no --platform needed)
docker build -t quiz-backend-testing .

# Build ARM64 image (on x86 machine)
docker build --platform linux/arm64 -t quiz-backend-testing .

# Get ECR login
aws ecr get-login-password --region ap-south-1 | \
  docker login --username AWS --password-stdin \
  111766607077.dkr.ecr.ap-south-1.amazonaws.com

# Tag and push
docker tag quiz-backend-testing:latest \
  111766607077.dkr.ecr.ap-south-1.amazonaws.com/quiz-backend-testing:latest
docker push 111766607077.dkr.ecr.ap-south-1.amazonaws.com/quiz-backend-testing:latest

# Force ECS to pull new image
aws ecs update-service \
  --cluster quiz-backend-testing \
  --service quiz-backend-testing \
  --force-new-deployment
```

### Monitoring Commands

```bash
# Check service status
aws ecs describe-services \
  --cluster quiz-backend-testing \
  --services quiz-backend-testing \
  --query 'services[0].{desired:desiredCount,running:runningCount,pending:pendingCount}'

# Tail logs
aws logs tail /ecs/quiz-backend-testing --follow

# Check ALB health
curl -s -o /dev/null -w "%{http_code}" \
  http://quiz-backend-testing-1700268315.ap-south-1.elb.amazonaws.com/docs

# Check task architecture
aws ecs describe-task-definition --task-definition quiz-backend-testing \
  --query 'taskDefinition.runtimePlatform'
```

### Scaling Commands

```bash
# Scale up
aws ecs update-service \
  --cluster quiz-backend-testing \
  --service quiz-backend-testing \
  --desired-count 2

# Scale down
aws ecs update-service \
  --cluster quiz-backend-testing \
  --service quiz-backend-testing \
  --desired-count 1
```

---

## Troubleshooting

### Task Fails to Start

1. **Check CloudWatch logs**: `aws logs tail /ecs/quiz-backend-testing --follow`
2. **Check task stopped reason**:
   ```bash
   TASK_ARN=$(aws ecs list-tasks --cluster quiz-backend-testing --desired-status STOPPED --query 'taskArns[0]' --output text)
   aws ecs describe-tasks --cluster quiz-backend-testing --tasks $TASK_ARN \
     --query 'tasks[0].stoppedReason'
   ```
3. **Common issues**:
   - `exec format error` → Architecture mismatch, rebuild image for correct platform
   - `InvalidURI` → Check MongoDB connection string format in tfvars
   - `Image not found` → Ensure image is pushed to ECR with correct tag

### ALB Returns 502/503

1. **Check target health**: AWS Console → EC2 → Target Groups → quiz-backend-testing
2. **Common causes**:
   - 502: Task is running but unhealthy → Check application logs
   - 503: No healthy targets → Check if task is running
   - Health check failing → Verify `/docs` endpoint responds

### MongoDB Connection Errors

1. **Check connection string format**: Must start with `mongodb://` or `mongodb+srv://`
2. **Check network**: ECS tasks need internet access (we use `assign_public_ip = true`)
3. **Check MongoDB Atlas**: Ensure IP allowlist includes `0.0.0.0/0` for testing

---

## Cost Estimate (Testing Environment)

| Resource | Specification | Monthly Cost (approx) |
|----------|---------------|----------------------|
| ECS Fargate (ARM64) | 0.5 vCPU, 1GB, 24/7 | ~$15 |
| ALB | 1 ALB, minimal traffic | ~$18 |
| CloudWatch Logs | 7-day retention | ~$1 |
| ECR | <1GB storage | ~$0.10 |
| **Total** | | **~$35/month** |

*ARM64 (Graviton) saves ~20% compared to x86*

---

## Next Steps

1. **Add S3 Backend**: Update `main.tf` to use S3 for Terraform state
2. **Add HTTPS**: Create ACM certificate and HTTPS listener
3. **Add Auto-scaling**: Configure target tracking scaling policy
4. **Create Staging/Prod**: Copy testing config with adjusted values
5. **CI/CD Pipeline**: Add GitHub Actions workflow for automated deployments
6. **Custom Domain**: Set up Route53 record pointing to ALB
7. **Load Testing**: Verify connection pooling works under load

---

## Lessons Learned

1. **Always specify platform for Docker builds** when building on a different architecture than the target
2. **Use `default-for-az` filter** when working with default VPC subnets to avoid ALB conflicts
3. **ARM64 (Graviton) is recommended** - same performance, 20% cheaper, and Mac M-series builds natively
4. **Check Terraform provider version** - syntax changes between major versions
5. **MongoDB URI format is strict** - no extra quotes or escaping in tfvars

---

*Document created: January 3, 2026*
*Implementation completed: January 3, 2026*
