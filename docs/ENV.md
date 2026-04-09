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

Set via Terraform environment variables on the ECS task definition. The value is a `mongodb+srv://` URI pointing to the Atlas cluster:

```
MONGO_AUTH_CREDENTIALS="mongodb+srv://USER_NAME:PASSWORD@CLUSTER.mongodb.net/DATABASE_NAME?retryWrites=true&w=majority"
```

**NOTE**: When setting this in GitHub repository environments, include the value within double quotes and escape special characters with `\` as necessary.
