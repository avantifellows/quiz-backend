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

Set via Terraform environment variables on the ECS task definition (`terraform/testing/ecs.tf` and `terraform/prod/ecs.tf`). The value is a `mongodb+srv://` URI pointing to the Atlas cluster:

```
MONGO_AUTH_CREDENTIALS="mongodb+srv://USER_NAME:PASSWORD@CLUSTER.mongodb.net/?retryWrites=true&w=majority"
```

The URI should **not** embed a database name in the path — use `MONGO_DB_NAME` (below) instead.

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

The test harness (`app/tests/base.py`) forces `MONGO_DB_NAME=quiz_test` before constructing the app, regardless of what is set in the environment. A safety guard refuses to run cleanup operations if the effective database name is `quiz`.

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
