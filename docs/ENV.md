## Environment Variables

### `MONGO_AUTH_CREDENTIALS`

MongoDB connection URI. **Required** — the app raises a `RuntimeError` at startup if this is not set.

#### Local development

Copy `.env.example` to `.env` at the repo root. The default value connects to a local MongoDB instance:

```
MONGO_AUTH_CREDENTIALS="mongodb://127.0.0.1:27017"
```

The startup scripts (`startServerMac.sh` / `startServerLinux.sh`) automatically source `.env` before launching the server. You can also export the variable manually:

```bash
export MONGO_AUTH_CREDENTIALS="mongodb://127.0.0.1:27017"
```

#### CI

The GitHub Actions CI workflow sets this explicitly in `.github/workflows/ci.yml`:

```
MONGO_AUTH_CREDENTIALS: mongodb://localhost:27017
```

#### Production / Testing (ECS)

Set `mongo_auth_credentials` in `terraform/testing/terraform.tfvars` or `terraform/prod/terraform.tfvars`, using the matching `terraform.tfvars.example` as the template. Terraform adds it to the ECS task definition as `MONGO_AUTH_CREDENTIALS`.

```
mongo_auth_credentials = "mongodb+srv://USER_NAME:PASSWORD@CLUSTER.mongodb.net/?retryWrites=true&w=majority"
```

The URI should **not** embed a database name in the path - use `MONGO_DB_NAME` (below) instead. `terraform.tfvars` is gitignored and must not be committed. The deployment workflows preserve these Terraform-managed ECS values; they do not read them from GitHub repository environments.

---

### `MONGO_DB_NAME`

Database name to use. **Optional** — defaults to `"quiz"` if not set.

#### Local development

For local development and testing, set this in `.env`:

```
MONGO_DB_NAME="quiz_test"
```

Using `quiz_test` locally avoids accidentally modifying a production-like `quiz` database.

#### CI

The GitHub Actions CI workflow sets this explicitly in `.github/workflows/ci.yml`:

```
MONGO_DB_NAME: quiz_test
```

#### Test harness override

The test harness (`app/tests/base.py`) forces `MONGO_DB_NAME=quiz_test` before constructing the app, regardless of what is set in the environment. Before cleanup it also requires a local MongoDB URI and the one-shot `ALLOW_TEST_DATABASE_RESET=1` opt-in.

#### Production / Testing (ECS)

Set via Terraform environment variables on the ECS task definition:

- **Production:** `mongo_db_name = "quiz"` in `terraform/prod/terraform.tfvars`
- **Testing:** configured in `terraform/testing/terraform.tfvars`

---

### `MONGO_MAX_POOL_SIZE`

Maximum number of connections in the AsyncMongoClient connection pool. **Optional** — defaults to `20`.

Override via environment variable if your deployment needs a larger or smaller pool:

```
MONGO_MAX_POOL_SIZE=30
```

---

### `MONGO_MIN_POOL_SIZE`

Minimum number of connections maintained in the AsyncMongoClient connection pool. **Optional** — defaults to `5`.

```
MONGO_MIN_POOL_SIZE=2
```

### Redis cache deployment settings

Terraform controls `CACHE_ENABLED` (default `false`), `CACHE_NAMESPACE` (default
`v1`), and `REDIS_MAX_CONNECTIONS` (default `10` per backend worker), using
`cache_enabled`, `cache_namespace`, and `redis_max_connections` in each
environment's tfvars. `REDIS_URL` points to the task-local Redis sidecar at
`redis://localhost:6379/0`. The sidecar must be installed through Terraform before
enabling caching; app deployments alone do not install it.

Terraform also requires `backend_image`: the exact current SHA-tagged image or
image digest. Refresh it before each infrastructure apply to avoid changing
backend code accidentally. See [Redis rollout and rollback](redis-cache-rollout.md)
for the deployment order, validation, and how to capture the running image.

`REDIS_TIMEOUT_SECONDS` defaults to `0.25` seconds (valid range: greater than zero
and at most five). It bounds each Redis connection/ping, GET, SET and client-close
operation. Socket deadlines and disabled command retries provide additional
protection. After a cache failure, requests use MongoDB during a five-second
reconnect cooldown. This setting is not the cache entry TTL or an overall HTTP
request deadline; a request can perform multiple bounded cache operations.
