# Quiz Backend: Migration from Lambda to ECS

## Document Purpose

This document outlines a proposed migration of the Quiz Backend from AWS Lambda to ECS Fargate to solve MongoDB connection limit issues. It is intended for discussion with the development team before implementation.

---

## Table of Contents

1. [The Problem](#the-problem)
2. [Background: How Lambda and Connections Work](#background-how-lambda-and-connections-work)
3. [Solution Options Considered](#solution-options-considered)
4. [Recommended Solution: ECS Fargate](#recommended-solution-ecs-fargate)
5. [Scaling Guide: ECS and MongoDB](#scaling-guide-ecs-and-mongodb) ⬅️ **Important for Operations**
6. [Technical Implementation](#technical-implementation)
7. [Cost Comparison](#cost-comparison)
8. [Migration Steps](#migration-steps)
9. [Risks and Rollback Plan](#risks-and-rollback-plan)
10. [FAQ](#faq)

---

## The Problem

### Current Situation

- Quiz Backend runs on **AWS Lambda** with API Gateway
- Database is **MongoDB Atlas M10** (500 connection limit)
- During peak usage (1000-1500 concurrent students taking tests), we hit MongoDB connection limits
- Current workaround: Manually scale to M40 ($455/month vs $57/month) when we expect high load
- This is expensive and requires manual intervention 1-2 days before peaks

### Why This Happens

When many students access the quiz simultaneously:

```
Student 1 → Lambda Instance 1 → MongoDB Connection 1
Student 2 → Lambda Instance 2 → MongoDB Connection 2
Student 3 → Lambda Instance 3 → MongoDB Connection 3
...
Student 500 → Lambda Instance 500 → MongoDB Connection 500
Student 501 → Lambda Instance 501 → ❌ CONNECTION LIMIT EXCEEDED
```

Each Lambda instance creates its own connection(s) to MongoDB. With 500+ concurrent requests, we exceed the M10's 500 connection limit.

---

## Background: How Lambda and Connections Work

### What is AWS Lambda?

Lambda is "serverless" - you upload code, AWS runs it when requests come in. You don't manage servers.

**How Lambda scales:**
- Each incoming request gets its own "instance" (isolated container)
- If 100 requests come in simultaneously, AWS creates 100 instances
- Each instance has its own memory, its own database connections
- Instances are destroyed after ~15 minutes of inactivity

**The connection problem:**
```python
# Our current database.py
client = MongoClient(os.getenv("MONGO_AUTH_CREDENTIALS"))
```

Every Lambda instance runs this code and creates a new connection. There's no sharing between instances.

### What is Connection Pooling?

Connection pooling means reusing database connections instead of creating new ones for each request.

**Without pooling (Lambda):**
```
Request 1 → Create connection → Use → Destroy
Request 2 → Create connection → Use → Destroy
Request 3 → Create connection → Use → Destroy
(Each request pays the ~20-50ms connection cost)
```

**With pooling (ECS):**
```
App starts → Create 20 connections (pool)

Request 1 → Borrow connection → Use → Return to pool
Request 2 → Borrow connection → Use → Return to pool
Request 3 → Borrow connection → Use → Return to pool
(Connections are reused, no creation overhead)
```

### What is ECS Fargate?

ECS (Elastic Container Service) runs Docker containers. Fargate is the "serverless" version - you don't manage the underlying servers.

**Key differences from Lambda:**

| Aspect | Lambda | ECS Fargate |
|--------|--------|-------------|
| Unit of deployment | Function | Docker container |
| Lifespan | Seconds to minutes | Hours to forever |
| Scaling | Per-request (aggressive) | Per-container (controlled) |
| Connection pooling | Not effective | Very effective |
| Cold starts | Yes (500ms-2s) | No (always running) |
| Billing | Per 100ms of execution | Per second of container time |

**Why ECS solves our problem:**

```
Container 1 (20 pooled connections) → handles ~500 requests/sec
Container 2 (20 pooled connections) → handles ~500 requests/sec
Container 3 (20 pooled connections) → handles ~500 requests/sec
────────────────────────────────────────────────────────────────
Total: 60 connections, handles 1500 concurrent users easily
```

Instead of 1500 Lambda instances with 1500+ connections, we have 3-20 containers with 60-400 connections.

---

## Solution Options Considered

### Option 1: Lambda + Provisioned Concurrency

**What it is:** Pre-warm a fixed number of Lambda instances to limit total connections.

**Pros:**
- Minimal code changes
- Stay on Lambda (familiar)

**Cons:**
- Still limited by Lambda's connection model
- Costs ~$50-80/month for provisioned capacity
- Would still need M30 (~$228/month) for comfortable headroom
- Total: ~$280-310/month

**Verdict:** Viable but not ideal for our load pattern.

### Option 2: MongoDB Atlas Serverless

**What it is:** MongoDB manages connection pooling for you.

**Pros:**
- No code changes
- No infrastructure changes

**Cons:**
- Expensive at scale ($0.10 per million reads)
- Our load would cost significantly more than current setup
- Less predictable billing

**Verdict:** Too expensive for our usage pattern.

### Option 3: ECS Fargate (Recommended)

**What it is:** Run the FastAPI app as Docker containers with proper connection pooling.

**Pros:**
- Predictable MongoDB connections (controlled pool size)
- Can stay on M10 for most scenarios
- Lower latency (no cold starts, pooled connections)
- Similar operational model to Lambda (serverless containers)
- Auto-scaling available

**Cons:**
- Infrastructure migration required
- Learning curve for team
- ~1-2 days setup time

**Verdict:** Best long-term solution for our needs.

### Option 4: Self-Managed EC2 Instances

**What it is:** Run the FastAPI app on EC2 instances you manage, with an Application Load Balancer.

**Pros:**
- Slightly cheaper at steady-state (~$30/month vs ~$45/month for baseline)
- More control over the environment
- Can use Reserved Instances for 30-40% savings on long commitments
- Familiar to teams with traditional server experience

**Cons:**
- You manage everything: OS patching, security updates, Docker, disk space
- Slower scaling (2-5 minutes vs 30-60 seconds for Fargate)
- Need to handle instance failures, SSH keys, monitoring
- Scaling is less granular (whole instances vs fractional vCPU)

**Verdict:** Viable but adds operational overhead. Cost savings (~$15/month) don't justify the extra work.

### Why ECS Fargate Over EC2?

| Aspect | ECS Fargate | Self-Managed EC2 |
|--------|-------------|------------------|
| **Server management** | None - AWS handles host OS | You patch, update, monitor |
| **Scaling speed** | 30-60 seconds | 2-5 minutes |
| **Scaling granularity** | 0.25 vCPU increments | Whole instances |
| **Minimum running cost** | Pay only when tasks run | At least 1 instance always on |
| **SSH access needed** | No | Yes |
| **Security patching** | AWS handles it | Your responsibility |
| **Health checks** | Automatic replacement | You configure and monitor |
| **3am incident response** | Automatic recovery | Your problem |

**Cost comparison for our baseline (3 containers 24/7):**

| Setup | Monthly Cost |
|-------|--------------|
| ECS Fargate (3 × 0.5 vCPU, 1GB) | ~$45 |
| EC2 (1 × t3.medium running 3 containers) | ~$30 |
| Difference | ~$15/month |

**Hidden EC2 costs not in the $30:**
- 2-4 hours/month patching and maintenance
- Security update monitoring
- Disk space alerts setup
- Debugging instance issues
- One engineer-hour costs more than $15

**Why Fargate wins for our use case:**

1. **Variable load pattern** - We have low baseline (50-100 students) with occasional peaks (5,000+ students).
   - EC2: Either overpay with large always-on instances, or scale too slowly during peaks
   - Fargate: Scales in 30 seconds, pay only for usage

2. **Peak scaling speed** - When 5,000 students start a test simultaneously:
   - EC2: 3-5 minute boot time could cause delays
   - Fargate: 30-60 seconds, barely noticeable

3. **Operational simplicity** - Small team, focus on product not infrastructure

4. **The math** - $15/month savings = $180/year. One incident requiring manual intervention costs more in engineer time.

---

## Recommended Solution: ECS Fargate

### Architecture Overview

```
                         ┌─────────────────────────────────────┐
                         │           AWS Cloud                 │
                         │                                     │
┌──────────┐            │   ┌─────────────────────────────┐   │
│ Students │ ──HTTPS──▶ │   │  Application Load Balancer  │   │
└──────────┘            │   └──────────────┬──────────────┘   │
                         │                  │                  │
                         │   ┌──────────────┼──────────────┐   │
                         │   │         ECS Cluster         │   │
                         │   │              │              │   │
                         │   │   ┌──────────┴──────────┐   │   │
                         │   │   │                     │   │   │
                         │   │ ┌─┴─┐  ┌───┐  ┌───┐    │   │   │
                         │   │ │ T1│  │ T2│  │ T3│... │   │   │
                         │   │ └─┬─┘  └─┬─┘  └─┬─┘    │   │   │
                         │   │   │      │      │       │   │   │
                         │   └───┼──────┼──────┼───────┘   │
                         │       │      │      │           │   │
                         │       └──────┼──────┘           │   │
                         │              │                  │   │
                         └──────────────┼──────────────────┘
                                        │
                              ┌─────────┴─────────┐
                              │   MongoDB Atlas   │
                              │       (M10)       │
                              └───────────────────┘

T1, T2, T3 = ECS Tasks (Docker containers running our FastAPI app)
Each task maintains a pool of 20 MongoDB connections
```

### Scaling Strategy

| Load | Concurrent Users | ECS Tasks | MongoDB Connections |
|------|------------------|-----------|---------------------|
| Low (normal) | 50-100 | 3 | 60 |
| Medium | 300-500 | 8 | 160 |
| High (peak) | 1000-1500 | 20 | 400 |

All scenarios stay well within M10's 500 connection limit.

### Auto-Scaling Configuration

ECS will automatically scale based on CPU usage:

- **Minimum tasks:** 3 (always running for baseline load)
- **Maximum tasks:** 25 (cap for connection safety)
- **Scale out:** When average CPU > 70% for 1 minute
- **Scale in:** When average CPU < 30% for 5 minutes

For known high-load events (scheduled exams), we can pre-scale:
```bash
# Run 1-2 days before expected peak
aws ecs update-service --cluster quiz-cluster --service quiz-backend --desired-count 20
```

---

## Scaling Guide: ECS and MongoDB

This section explains when and how to scale both ECS and MongoDB.

### Important: "Active Students" vs "Concurrent Requests"

**This distinction is critical for understanding capacity.**

| Term | Definition | Example |
|------|------------|---------|
| **Active students** | Students with test window open | 5000 students taking a 3-hour test |
| **Concurrent requests** | API requests being processed *at this exact moment* | 25-100 requests |

A student taking a 3-hour test is NOT holding a connection open for 3 hours. They make a request every 30-60 seconds (submit answer, navigate, load question), and each request takes ~100-200ms to complete.

#### The Math: 5000 Active Students

```
5000 students taking tests in the same 3-hour window
│
├── Request pattern:
│   └── Each student makes 1 request every ~30 seconds
│   └── 5000 ÷ 30 = ~167 requests per second (steady state)
│
├── Request duration:
│   └── Average response time: ~150ms (0.15 seconds)
│
├── Actual concurrent requests:
│   └── Steady state: 167 RPS × 0.15s = ~25 concurrent requests
│   └── Bursts (test start/end): ~100-200 concurrent requests
│
└── What this means for infrastructure:
    └── 3-5 ECS tasks can handle 5000 active students easily
    └── MongoDB connections needed: 60-100 (well within M10's 450 limit)
```

**Key insight:** 5000 active students ≠ 5000 concurrent connections. With ECS, you likely need only 3-5 tasks and can stay on M10.

#### Why Lambda Has Connection Problems

Lambda scales differently - it spawns instances per request, not per concurrent request:

```
Burst scenario: 5000 students start test simultaneously

Lambda behavior:
├── 5000 requests arrive in ~1-2 minutes
├── Lambda spawns 100-500 instances to absorb burst
├── Each instance creates 1-5 MongoDB connections
├── Total connections: 500-2000+ → ❌ Exceeds M10's 500 limit
└── Result: Connection errors, failed test starts

ECS behavior:
├── Same 5000 requests arrive in ~1-2 minutes
├── Existing 5 ECS tasks queue and process requests
├── Each task has 20 pre-established pooled connections
├── Total connections: 100 → ✅ Well within M10's 450 limit
└── Result: Slightly higher latency during burst, but no failures
```

### Understanding the Capacity Limits

#### MongoDB Atlas Tier Limits

| Tier | Connection Limit | Monthly Cost | Reserved for Admin* | Available for App |
|------|------------------|--------------|---------------------|-------------------|
| M10 | 500 | ~$57 | 50 | **450** |
| M30 | 1000 | ~$228 | 50 | **950** |
| M40 | 1500 | ~$455 | 100 | **1400** |

*Reserved connections for: Atlas monitoring, database admin tools, data exports, other services accessing the same DB.

#### ECS Task Capacity

Each ECS task runs with:
- `maxPoolSize=20` MongoDB connections
- 4 Uvicorn workers (async, can handle many concurrent requests)
- 0.5 vCPU, 1GB RAM

**Capacity per task:** ~2000-3000 active students (or ~100-150 concurrent requests)

Each Uvicorn worker uses async I/O, meaning it can handle many requests concurrently while waiting for MongoDB responses. The limiting factor is usually CPU, not connection count.

### Scaling Thresholds

These thresholds are based on **active students** (students with tests open), not concurrent requests.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                        SCALING DECISION MATRIX                                   │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Active         Concurrent      ECS Tasks    MongoDB    Connections   Action    │
│  Students       Requests*       Needed       Tier       Used                    │
│                                                                                  │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  0 - 1,000      5 - 35          3 (min)      M10        60           None       │
│                                                                                  │
│  1,000 - 3,000  35 - 100        3 - 5        M10        60 - 100     Auto-scale │
│                                                                                  │
│  3,000 - 8,000  100 - 270       5 - 10       M10        100 - 200    Auto-scale │
│                                                                                  │
│  8,000 - 15,000 270 - 500       10 - 18      M10        200 - 360    Monitor    │
│                 ─────────────────────────────────────────────────────────────   │
│  ⚠️  THRESHOLD: Above 15,000 students, consider pre-scaling to M30              │
│                                                                                  │
│  15,000-30,000  500 - 1000      18 - 35      M30 ⬆️     360 - 700    Pre-scale  │
│                                                                                  │
│  30,000-50,000  1000 - 1700     35 - 55      M30        700 - 1100   Pre-scale  │
│                 ─────────────────────────────────────────────────────────────   │
│  ⚠️  THRESHOLD: Above 40,000 students, consider M40                             │
│                                                                                  │
│  50,000+        1700+           55+          M40+ ⬆️    1100+        Contact    │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘

* Concurrent requests = Active students ÷ 30 (assuming 1 request per 30 seconds, 150ms response)
```

### When to Scale MongoDB (Decision Tree)

```
Expected active students for upcoming event?
│
├── Less than 15,000 students
│   └── ✅ Stay on M10, ECS auto-scaling handles everything
│   └── Example: 5,000 students = ~5 ECS tasks, ~100 connections
│
├── 15,000 - 40,000 students
│   └── ⚠️  Scale MongoDB to M30 at least 1 hour before event
│   └── Pre-scale ECS to 20-40 tasks
│
├── 40,000 - 70,000 students
│   └── ⚠️  Scale MongoDB to M40 at least 1 hour before event
│   └── Pre-scale ECS to 40-60 tasks
│
└── More than 70,000 students
    └── 🚨 Contact DevOps - need M50+ or architecture review
```

### Burst Handling: Test Start/End

The highest load occurs when many students start or end tests simultaneously.

**Worst-case burst scenario: 5,000 students start a test within 2 minutes**

```
Burst analysis:
├── 5,000 requests over 2 minutes = ~42 requests/second
├── Each request (fetch quiz) takes ~200-500ms
├── Peak concurrent requests: 42 × 0.35 = ~15 concurrent
├── With safety margin (2x): ~30 concurrent requests
│
└── ECS capacity needed:
    └── 3 tasks (minimum) can handle 100+ concurrent requests each
    └── ✅ Easily handled, no pre-scaling needed
```

**Larger burst: 20,000 students start within 5 minutes**

```
Burst analysis:
├── 20,000 requests over 5 minutes = ~67 requests/second
├── Peak concurrent requests: ~25-50
├── With safety margin (2x): ~100 concurrent requests
│
└── ECS capacity needed:
    └── 5-8 tasks recommended
    └── ✅ Auto-scaling handles this, but can pre-scale for safety
```

### How to Scale: Step-by-Step Commands

#### Scaling for Expected Peak (Do This 1-2 Hours Before)

**Scenario: Expecting 1200 concurrent students for an exam**

```bash
# Step 1: Scale MongoDB M10 → M30 (takes ~10-15 minutes)
# Do this via Atlas UI:
# Atlas Dashboard → Cluster → Configuration → Edit → Select M30 → Apply

# Step 2: Pre-scale ECS to handle the load
aws ecs update-service \
  --cluster quiz-cluster \
  --service quiz-backend-prod \
  --desired-count 25

# Step 3: Verify ECS scaling is complete
aws ecs wait services-stable \
  --cluster quiz-cluster \
  --services quiz-backend-prod

# Step 4: Verify task count
aws ecs describe-services \
  --cluster quiz-cluster \
  --services quiz-backend-prod \
  --query 'services[0].{desired:desiredCount,running:runningCount}'
```

**Expected output:**
```json
{
    "desired": 25,
    "running": 25
}
```

#### Scaling Down After Peak (Do This 1-2 Hours After Event Ends)

```bash
# Step 1: Scale ECS back down
aws ecs update-service \
  --cluster quiz-cluster \
  --service quiz-backend-prod \
  --desired-count 3

# Step 2: Scale MongoDB M30 → M10 (via Atlas UI)
# Atlas Dashboard → Cluster → Configuration → Edit → Select M10 → Apply
```

### Monitoring: How to Know When to Scale

#### CloudWatch Alarms to Set Up

| Alarm | Threshold | Action |
|-------|-----------|--------|
| ECS CPU > 80% for 5 min | Warning | Auto-scale should handle, but monitor |
| ECS CPU > 90% for 2 min | Critical | Manual intervention may be needed |
| MongoDB connections > 350 (M10) | Warning | Consider scaling to M30 |
| MongoDB connections > 400 (M10) | Critical | Scale to M30 immediately |
| ALB 5xx errors > 10/min | Critical | Check logs, may need more capacity |
| ALB response time P95 > 2s | Warning | May need more ECS tasks |

#### Quick Health Check Commands

```bash
# Check current ECS task count and status
aws ecs describe-services \
  --cluster quiz-cluster \
  --services quiz-backend-prod \
  --query 'services[0].{
    desired: desiredCount,
    running: runningCount,
    pending: pendingCount,
    cpu: "check CloudWatch"
  }'

# Check MongoDB connection count (run from any ECS task or locally)
# Connect to MongoDB and run:
mongo "$MONGO_AUTH_CREDENTIALS" --eval "db.serverStatus().connections"

# Expected output:
# { "current" : 45, "available" : 455, "totalCreated" : 1234 }
#   ↑ current should be well below "available"
```

#### MongoDB Atlas Monitoring

In Atlas Dashboard → Metrics → Connections:
- **Green zone:** Current connections < 70% of limit
- **Yellow zone:** 70-85% of limit → Consider scaling up
- **Red zone:** > 85% of limit → Scale immediately

### Scaling Scenarios: Real Examples

#### Scenario 1: Regular Day (500-1000 active students)

```
Status: Normal operations
Active students: 500-1000 taking tests throughout the day
Concurrent requests: ~15-35
ECS Tasks: 3 (minimum)
MongoDB: M10
Connections used: ~60 of 450 available
Action needed: None, auto-scaling handles fluctuations
```

#### Scenario 2: Scheduled Exam (5,000 students in 3-hour window)

```
This is YOUR typical peak scenario.

Active students: 5,000 in same time window
Concurrent requests: ~25-50 steady, ~100-200 during start/end bursts
ECS Tasks needed: 3-5
MongoDB connections: 60-100

Timeline:
- No pre-scaling needed! ✅
- ECS auto-scaling handles the load
- Monitor CloudWatch dashboard during exam

MongoDB: Stay on M10 (5,000 students = ~100 connections, well within limit)

Why this works:
- 5,000 students ÷ 30 seconds = 167 RPS
- 167 RPS × 0.15s response time = 25 concurrent requests
- 3 ECS tasks can handle 300+ concurrent requests
```

#### Scenario 3: Large Exam Day (20,000 students across multiple tests)

```
Active students: 20,000 (e.g., 4 tests with 5,000 students each, overlapping)
Concurrent requests: ~100-200 steady, ~400-600 during peak bursts
ECS Tasks needed: 8-12
MongoDB connections: 160-240

Timeline:
- 1 hour before: Pre-scale ECS to 12 tasks (optional, for safety margin)
- During exam: Monitor CloudWatch dashboard
- 1 hour after: Let auto-scaling reduce tasks

Commands:
  # Optional pre-scale for safety margin
  aws ecs update-service --cluster quiz-cluster --service quiz-backend-prod --desired-count 12

MongoDB: Stay on M10 (20,000 students = ~240 connections, within M10's 450 limit)
```

#### Scenario 4: Major Exam Event (50,000+ students)

```
Active students: 50,000 in same time window
Concurrent requests: ~500-800 steady, ~1500+ during bursts
ECS Tasks needed: 35-50
MongoDB connections: 700-1000

Timeline:
- 2 hours before: Scale MongoDB M10 → M30 (via Atlas UI)
- 1.5 hours before: Scale ECS to 45 tasks
- 1 hour before: Verify both scaling complete
- During exam: Active monitoring
- 1 hour after: Scale ECS back (auto-scaling will handle)
- 2 hours after: Scale MongoDB M30 → M10

Commands:
  # Before
  aws ecs update-service --cluster quiz-cluster --service quiz-backend-prod --desired-count 45

MongoDB: M30 required (50,000 students = ~800 connections, exceeds M10's 450)
```

#### Scenario 5: Unexpected Traffic Spike

```
Symptom: Alerts firing - high CPU, slow response times
Note: With ECS, connection limit errors are very unlikely

Immediate actions (in order):

1. Check current state:
   aws ecs describe-services --cluster quiz-cluster --services quiz-backend-prod

2. Check if auto-scaling is already responding:
   aws ecs list-tasks --cluster quiz-cluster --service-name quiz-backend-prod

3. If auto-scaling is maxed out, manually increase max capacity:
   aws application-autoscaling register-scalable-target \
     --service-namespace ecs \
     --resource-id service/quiz-cluster/quiz-backend-prod \
     --scalable-dimension ecs:service:DesiredCount \
     --max-capacity 40

4. If MongoDB connections > 350 (check Atlas), scale to M30

5. Post-incident: Review logs, adjust auto-scaling thresholds if needed
```

### Comparison: Lambda vs ECS Scaling

| Aspect | Lambda (Current) | ECS (Proposed) |
|--------|------------------|----------------|
| **5,000 students scenario** | Need M40 ($455/mo) | M10 is enough ($57/mo) |
| **20,000 students scenario** | Need M40+ | M10 still works |
| **Compute Scaling** | Uncontrolled, causes connection explosion | Controlled, predictable connections |
| **MongoDB Scaling** | Manual M10→M40 for most peaks | Only needed above 15,000 students |
| **Intervention frequency** | Every significant exam | Rarely (only very large events) |

### Key Takeaways

1. **Active students ≠ Concurrent connections** - 5,000 students = ~25-50 concurrent requests
2. **Below 15,000 students:** M10 + ECS auto-scaling handles everything automatically
3. **Your typical peak (5,000 students):** No manual scaling needed at all with ECS
4. **15,000-40,000 students:** May need M30, pre-scale ECS for safety
5. **Above 40,000 students:** Need M30/M40 + pre-scaled ECS
6. **Always scale MongoDB BEFORE the event** - it takes 10-15 minutes
7. **ECS scales in ~1 minute** - can be done closer to event time
8. **When in doubt, scale up** - cost of over-provisioning is lower than cost of failed exams

---

## Technical Implementation

### Code Changes Required

#### 1. `app/database.py` (modify existing)

```python
import os
from pymongo import MongoClient

if "MONGO_AUTH_CREDENTIALS" not in os.environ:
    from dotenv import load_dotenv
    load_dotenv("../.env")

# Connection pool configuration for ECS
# These settings ensure efficient connection reuse
client = MongoClient(
    os.getenv("MONGO_AUTH_CREDENTIALS"),

    # Connection Pool Settings
    maxPoolSize=20,          # Max connections this container will use
    minPoolSize=5,           # Keep 5 connections always open

    # Timeout Settings
    maxIdleTimeMS=30000,     # Close idle connections after 30 seconds
    connectTimeoutMS=5000,   # Fail fast if can't connect in 5 seconds
    serverSelectionTimeoutMS=5000,

    # Reliability Settings
    retryWrites=True,        # Retry failed writes automatically
    retryReads=True,         # Retry failed reads automatically
)
```

**Why these settings:**
- `maxPoolSize=20`: Each container uses max 20 connections. With 25 max containers = 500 connections (exactly M10 limit)
- `minPoolSize=5`: Keep connections warm, avoid reconnection delay
- `maxIdleTimeMS=30000`: Clean up unused connections after 30s
- `retryWrites/retryReads`: Handle transient network issues gracefully

#### 2. `Dockerfile` (new file in repo root)

```dockerfile
# Use official Python image
FROM python:3.9-slim

# Set working directory inside container
WORKDIR /app

# Install dependencies first (for Docker layer caching)
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ .

# Expose port 8000 (FastAPI default)
EXPOSE 8000

# Health check - ECS uses this to know if container is healthy
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

# Run FastAPI with Uvicorn
# - 0.0.0.0: Listen on all interfaces (required for Docker)
# - workers=4: Use 4 worker processes for better CPU utilization
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

**Why these settings:**
- `python:3.9-slim`: Matches our current Lambda runtime, smaller image
- `--workers=4`: Multiple workers handle concurrent requests better
- `HEALTHCHECK`: ECS replaces unhealthy containers automatically

#### 3. `main.py` (no changes required)

The existing code works as-is. The `Mangum` wrapper is only used when running on Lambda - it's ignored when running with Uvicorn.

```python
# This line stays but is unused on ECS
handler = Mangum(app)  # Only Lambda uses this
```

### Infrastructure Files

#### 4. `ecs/task-definition.json` (new file)

```json
{
  "family": "quiz-backend",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::ACCOUNT_ID:role/ecsTaskExecutionRole",
  "containerDefinitions": [
    {
      "name": "quiz-backend",
      "image": "ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com/quiz-backend:latest",
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [],
      "secrets": [
        {
          "name": "MONGO_AUTH_CREDENTIALS",
          "valueFrom": "arn:aws:secretsmanager:ap-south-1:ACCOUNT_ID:secret:quiz/mongo-credentials"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/quiz-backend",
          "awslogs-region": "ap-south-1",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8000/docs || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ]
}
```

**Key settings explained:**
- `cpu: 512, memory: 1024`: 0.5 vCPU, 1GB RAM per container (adjust based on testing)
- `networkMode: awsvpc`: Each task gets its own IP (required for Fargate)
- `secrets`: Pulls MongoDB credentials from AWS Secrets Manager (secure)
- `logConfiguration`: Sends logs to CloudWatch for debugging

#### 5. `.github/workflows/deploy_to_prod_ecs.yml` (new file)

```yaml
name: Deploy to Production (ECS)

on:
  push:
    branches: ["release"]

jobs:
  deploy:
    name: Build and Deploy to ECS
    runs-on: ubuntu-latest
    environment: Production

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ap-south-1

      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build, tag, and push image to ECR
        id: build-image
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          ECR_REPOSITORY: quiz-backend
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG .
          docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:latest .
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:latest
          echo "image=$ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG" >> $GITHUB_OUTPUT

      - name: Deploy to ECS
        run: |
          aws ecs update-service \
            --cluster quiz-cluster \
            --service quiz-backend-prod \
            --force-new-deployment

      - name: Wait for deployment to complete
        run: |
          aws ecs wait services-stable \
            --cluster quiz-cluster \
            --services quiz-backend-prod

      - name: Notify on success
        if: success()
        run: |
          echo "Deployment successful!"
          # Add Discord/Slack notification here
```

### Scaling Commands (for operations)

```bash
# View current status
aws ecs describe-services --cluster quiz-cluster --services quiz-backend-prod

# Pre-scale for expected high load
aws ecs update-service \
  --cluster quiz-cluster \
  --service quiz-backend-prod \
  --desired-count 20

# Scale back after peak
aws ecs update-service \
  --cluster quiz-cluster \
  --service quiz-backend-prod \
  --desired-count 3

# View running tasks
aws ecs list-tasks --cluster quiz-cluster --service-name quiz-backend-prod
```

---

## Cost Comparison

### Current Costs (Lambda + M10/M40)

| Item | Monthly Cost |
|------|--------------|
| Lambda compute | ~$50-100 |
| API Gateway | ~$20-40 |
| MongoDB M10 (baseline) | $57 |
| MongoDB M40 (during peaks, ~1 week/month) | ~$115 |
| **Total** | **~$240-310/month** |

### Projected Costs (ECS + M10)

| Item | Monthly Cost |
|------|--------------|
| ECS Fargate (3 baseline tasks) | ~$45 |
| ECS Fargate (scaling overhead) | ~$30 |
| Application Load Balancer | ~$20 |
| MongoDB M10 (no more M40 needed) | $57 |
| ECR (container registry) | ~$5 |
| CloudWatch Logs | ~$10 |
| **Total** | **~$165-180/month** |

### Savings

- **Monthly savings:** ~$75-130
- **Annual savings:** ~$900-1,560
- **No more manual M40 scaling**

---

## Migration Steps

### Phase 1: Preparation (Day 1)

- [ ] Create ECR repository for Docker images
- [ ] Set up AWS Secrets Manager with MongoDB credentials
- [ ] Create ECS cluster
- [ ] Create IAM roles for ECS task execution
- [ ] Create VPC security groups for ECS tasks

### Phase 2: Development & Testing (Days 2-3)

- [ ] Update `database.py` with connection pool settings
- [ ] Create `Dockerfile`
- [ ] Build and test Docker image locally
- [ ] Deploy to staging ECS environment
- [ ] Run load tests to verify connection pooling works
- [ ] Verify all API endpoints work correctly

### Phase 3: Production Setup (Day 4)

- [ ] Create production ECS service
- [ ] Set up Application Load Balancer
- [ ] Configure auto-scaling policies
- [ ] Set up CloudWatch alarms and dashboards
- [ ] Update DNS to point to new ALB (can use weighted routing for gradual switch)

### Phase 4: Migration (Day 5)

- [ ] Deploy to production ECS
- [ ] Route 10% traffic to ECS, 90% to Lambda (weighted DNS)
- [ ] Monitor for errors
- [ ] Gradually increase ECS traffic (25% → 50% → 100%)
- [ ] Keep Lambda deployment active for 1 week as fallback

### Phase 5: Cleanup (Day 6+)

- [ ] Remove Lambda resources after 1 week of stable ECS operation
- [ ] Scale down MongoDB from M40 to M10 permanently
- [ ] Update documentation
- [ ] Archive old deployment workflows

---

## Risks and Rollback Plan

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| ECS configuration issues | Medium | High | Test thoroughly in staging |
| Higher latency than Lambda | Low | Medium | Monitor P95 latency, ALB adds only ~2ms |
| Auto-scaling too slow | Low | High | Keep minimum 3 tasks, set aggressive scale-out |
| Connection pool exhaustion | Low | Medium | Monitor pool usage, adjust maxPoolSize |
| Deployment pipeline issues | Medium | Low | Keep Lambda workflow as backup |

### Rollback Plan

If issues arise after migration:

1. **Immediate (< 5 minutes):** Switch DNS back to API Gateway/Lambda endpoint
2. **Short-term:** Lambda infrastructure remains intact for 1 week
3. **Data:** No data migration needed - both use same MongoDB

```bash
# Emergency rollback - switch DNS back to Lambda
aws route53 change-resource-record-sets \
  --hosted-zone-id ZONE_ID \
  --change-batch file://rollback-dns.json
```

---

## FAQ

### Q: Will this affect our API endpoints or require frontend changes?

**A:** No. The API endpoints, request/response formats remain identical. Frontend needs no changes. We're only changing how the backend is hosted.

### Q: What happens if a container crashes?

**A:** ECS automatically replaces unhealthy containers. With 3 minimum tasks, even if one crashes, the other 2 handle traffic while a replacement spins up (~30-60 seconds).

### Q: How do we debug issues in ECS?

**A:** Logs go to CloudWatch, same as Lambda. You can also shell into running containers:
```bash
aws ecs execute-command --cluster quiz-cluster --task TASK_ID --container quiz-backend --interactive --command "/bin/sh"
```

### Q: Will cold starts affect students?

**A:** No. Unlike Lambda, ECS containers are always running. There are no cold starts. In fact, response times should be slightly faster because connections are pre-established.

### Q: What if we need to scale urgently?

**A:** Either auto-scaling handles it (1-2 minute response time), or you can manually scale:
```bash
aws ecs update-service --cluster quiz-cluster --service quiz-backend-prod --desired-count 25
```
New containers start in ~30-60 seconds.

### Q: Can we still run the app locally the same way?

**A:** Yes. Local development is unchanged:
```bash
./startServerMac.sh  # or
uvicorn main:app --reload
```

### Q: What about the Mangum wrapper in main.py?

**A:** Leave it. It doesn't hurt anything when running on ECS - Uvicorn ignores it. This also means we can still deploy to Lambda if needed for any reason.

### Q: Why not just use EC2 instances instead of ECS Fargate?

**A:** We considered this. EC2 is ~$15/month cheaper at baseline, but:

1. **Scaling is slower** - EC2 takes 2-5 minutes to boot, Fargate takes 30-60 seconds. During exam start bursts, this matters.

2. **Operational overhead** - EC2 requires OS patching, security updates, disk monitoring, SSH key management. One incident costs more than $180/year in engineer time.

3. **Our load is variable** - Low baseline (50-100 users) with peaks (5,000+ students). Fargate's fast scaling and per-second billing fits this pattern better.

4. **Fargate is "serverless containers"** - Similar operational model to Lambda (which we're used to), just with connection pooling benefits.

See "Option 4: Self-Managed EC2 Instances" in the Solution Options section for the full comparison.

---

## Decision Required

Please review this document and provide feedback on:

1. **Proceed with ECS migration?** (Yes/No/Need more info)
2. **Timeline concerns?** (The 5-day estimate)
3. **Cost assumptions?** (Do these align with our AWS billing?)
4. **Any features or concerns not addressed?**

---

## Appendix: Useful Commands

```bash
# Build and run locally with Docker
docker build -t quiz-backend .
docker run -p 8000:8000 -e MONGO_AUTH_CREDENTIALS="mongodb://..." quiz-backend

# View ECS logs
aws logs tail /ecs/quiz-backend --follow

# Check service health
aws ecs describe-services --cluster quiz-cluster --services quiz-backend-prod \
  --query 'services[0].{desired:desiredCount,running:runningCount,pending:pendingCount}'

# List recent deployments
aws ecs describe-services --cluster quiz-cluster --services quiz-backend-prod \
  --query 'services[0].deployments'
```

---

*Document created: December 2024*
*Last updated: December 2024*
