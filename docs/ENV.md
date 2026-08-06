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
mongo_auth_credentials = "mongodb+srv://USER_NAME:PASSWORD@CLUSTER.mongodb.net/DATABASE_NAME?retryWrites=true&w=majority"
```

`terraform.tfvars` is gitignored and must not be committed. The deployment workflows preserve these Terraform-managed ECS values; they do not read them from GitHub repository environments.
