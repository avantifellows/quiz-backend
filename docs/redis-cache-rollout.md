# Redis cache rollout

PR #142 adds Terraform infrastructure and application support separately. A normal
GitHub Actions deployment updates the backend image using the service's current
task definition. It does not run Terraform, add Redis, or enable caching.

## Configuration ownership

Terraform owns the Redis sidecar and cache environment settings in both
`terraform/testing` and `terraform/prod`. Set these in the corresponding gitignored
`terraform.tfvars`:

```hcl
# Required: exact deployed image, refreshed before EVERY infrastructure apply.
backend_image         = "<ECR repository>:<full 40-character commit SHA>"
cache_enabled         = false
cache_namespace       = "v1"
redis_max_connections = 10
```

An image digest (`<repository>@sha256:<64 hex characters>`) is also supported.
`latest` is deliberately rejected. Terraform previously used that moving tag;
applying an infrastructure change could therefore select unrelated backend code.
The namespace must be nonempty, using letters, numbers, underscores or hyphens.
Ten Redis connections is an initial pool limit **per backend worker**, not a user
limit. Tune it from measured pool errors, hit rates, latency and MongoDB load.
Redis remains nonessential and local to each task at `redis://localhost:6379/0`.
No public Redis ingress is needed.

## Capture the active configuration before each apply

The following commands are read-only and target testing. Production uses its own
cluster/service, directory and tfvars; do not reuse testing configuration there.

```bash
REGION=ap-south-1
CLUSTER=quiz-backend-testing
SERVICE=quiz-backend-testing
TASK_DEFINITION=$(aws ecs describe-services --region "$REGION" \
  --cluster "$CLUSTER" --services "$SERVICE" \
  --query 'services[0].taskDefinition' --output text)
aws ecs describe-task-definition --region "$REGION" \
  --task-definition "$TASK_DEFINITION" \
  --query 'taskDefinition.containerDefinitions[?name==`quiz-backend`].image | [0]' \
  --output text
```

Record the task-definition ARN for rollback and put the returned image in
`backend_image`. First confirm the service is stable and all running tasks use
that image. If a legacy task references `latest`, resolve the running task's
`imageDigest` and pin that digest instead. Refresh this value after every app
rollout, before the next Terraform apply: an old tfvars image can roll back code.
Do not overlap an infrastructure apply with a GitHub Actions deployment.

## Staging sequence

1. Capture the active task definition/image as above. Keep `cache_enabled=false`.
2. From `terraform/testing`, initialize Terraform, create a saved plan, and inspect
   it. Expect a new task definition with Redis/cache configuration and a service
   revision update. Verify the backend image stays pinned to the captured image.
   Resolve unrelated changes before applying. Local tfvars and saved plans may
   contain credentials; keep them out of commits, attachments and public logs.
3. Apply the reviewed plan and wait for ECS stability. Verify the backend and
   Redis containers are healthy. The existing backend image remains selected.
4. Deploy #142 through its testing workflow. Confirm the exact image and run the
   cache-disabled functional baseline. Missing cache settings are treated as off;
   the workflow clearly labels this as **not testing Redis caching**.
5. Capture the newly deployed #142 image again and update `backend_image`.
   Set a dedicated staging namespace and `cache_enabled=true`; plan/apply only
   after reviewing the new revision. This step must preserve #142's image.
6. Verify the running image, Redis health and active settings. Run the
   [staging test plan](pr142-staging-test-plan.md). Capture an actual cold miss,
   warm hit, matching responses, TTL and per-family telemetry from the running
   task's Redis. Repeat per task if scaled out. `/health` and healthy Redis alone
   do not demonstrate that requests use the cache.
7. Keep production caching disabled until the correctness, freshness, failure
   recovery and performance gates pass. The unresolved lack of invalidation is
   a separate gate; this infrastructure change does not fix stale quiz settings.

For steps 2 and 5, use the normal reviewed plan/apply sequence:

```bash
terraform init
terraform plan -out=rollout.tfplan
terraform show rollout.tfplan
terraform apply rollout.tfplan
```

Run these from the intended environment directory. Do not blindly apply a plan
that reverts app configuration, scales services unexpectedly or changes unrelated
resources. Do not add automatic Terraform apply to the app deployment workflow.

## Deployment checks

Both app workflows inspect the **service-selected** task definition before
rendering the new image. `scripts/check_cache_deployment.py` rejects cache-enabled
configuration without a nonessential Redis sidecar, health check, local URL,
explicit namespace or positive pool limit. After rollout it checks the expected
backend image and health on each running task, and Redis health when enabled.
A service scaled to zero is explicitly reported as unvalidated at runtime.

These checks establish deployment prerequisites, not cache effectiveness. The
staging plan's cache-hit evidence is still mandatory before rollout sign-off.
A failed post-deployment check marks the job failed; it does not automatically
restore the prior task definition. Follow rollback below if needed.

## Rollback

- To disable caching while keeping #142, capture its current image, set
  `cache_enabled=false`, review/apply the testing Terraform plan, and verify the
  session read/save/submit flow. Leave the nonessential Redis sidecar in place.
- For an application regression, restore the recorded known-good task-definition
  ARN via ECS and wait for service stability. Verify the previous image and
  MongoDB-backed flows. Reconcile `backend_image` and cache settings in local
  tfvars before any subsequent Terraform apply, or it can undo the rollback.
- A namespace change produces cold caches on replacement tasks; it does not solve
  cache invalidation for edits while requests continue to use an existing cache.

## Local validation

```bash
python3 -m unittest discover -s scripts/tests -v
terraform -chdir=terraform/testing validate
terraform -chdir=terraform/prod validate
```

Run Terraform init for each environment before validate. Neither validation nor
unit tests deploy resources. The live cache tests use tracked synthetic fixtures;
never run the repository's destructive Redis/database test harness on staging.
