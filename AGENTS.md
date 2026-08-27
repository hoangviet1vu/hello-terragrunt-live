# AGENTS.md — hello-terragrunt-live

## Project Overview

This is the **live infrastructure** repository for Tenant Configuration
management. Each tenant gets its own folder containing per-environment
Terragrunt units that pin a specific version of the shared modules repo.

Source modules: https://github.com/hoangviet1vu/hello-terragrunt-modules

## Repository Layout

```
terragrunt.hcl                # root: remote state backend (S3) + AWS provider
<tenant-id>/
  <env>/terragrunt.hcl        # leaf unit — pins module version + env-specific inputs
```

Example (tenant `PRDCV`):

```
terragrunt.hcl
PRDCV/
  dev/terragrunt.hcl          # module v1.0.0, dynamodb=on,  ecr=off
  prod/terragrunt.hcl         # module v1.0.0, dynamodb=on,  ecr=on
```

## Remote State Configuration

Remote state storage uses a **pre-existing S3 bucket** that is **not** created
or managed by Terragrunt. The bucket must be provisioned separately (e.g., via
a dedicated bootstrap stack or manual creation) before running any Terragrunt
commands.

### Required Environment Variables

| Variable | Purpose | Required | Example |
|----------|---------|----------|---------|
| `TG_STATE_BUCKET` | Supplies the S3 bucket name used for remote state storage | Yes | `export TG_STATE_BUCKET=<bucket-name>` |
| `AWS_REGION` | Supplies the AWS region for both the remote state backend and the AWS provider | Yes | `export AWS_REGION=ap-southeast-2` |

Both variables must be set before running `terragrunt plan` or `terragrunt apply`.
The root `terragrunt.hcl` reads these via `get_env()` and will fail with a
descriptive error if either is unset or empty.

```bash
export TG_STATE_BUCKET=<bucket-name>
export AWS_REGION=ap-southeast-2
```

## Conventions

- **One folder per tenant**, named by tenant ID (uppercase).
- **One subfolder per environment** (`dev`, `prod`, etc.).
- Each leaf `terragrunt.hcl` must include the root config and specify:
  - `source` — git URL with `?ref=<tag>` pointing at the modules repo.
  - `inputs` — `tenant_name`, `environment`, `enable_dynamodb`, `enable_ecr`.
- Module version is pinned via git tag (e.g. `?ref=v1.0.0`). Never use a
  moving branch reference for real environments.

## Adding a Tenant

Copy an existing tenant folder (e.g. `PRDCV/`) to a new directory named
after the new tenant ID, then update `tenant_name` in each leaf's inputs.

## Adding an Environment

Copy an existing environment leaf (e.g. `PRDCV/dev/`) within the tenant
folder, rename the directory, and adjust `environment` and feature flags.

## Code Quality

- **Formatting**: Run `terraform fmt` on all `.hcl`/`.tf` files after changes.
- **Checkstyle**: Run `tflint` to catch style and correctness issues.
- Always format and lint before committing:
  ```bash
  terraform fmt -recursive .
  tflint --recursive
  ```

## Running

```bash
cd <tenant-id>/<env>
terragrunt plan
terragrunt apply
```

State is stored at `s3://<state-bucket>/<tenant-id>/<env>/terraform.tfstate`,
fully isolated per tenant and environment.

## Key Rules for AI Agents

1. Do NOT modify the root `terragrunt.hcl` unless explicitly asked — it
   controls shared state configuration for all tenants.
2. Always pin module versions with `?ref=vX.Y.Z`; never use `?ref=main`.
3. After any code change, run `terraform fmt` then `tflint` and fix issues
   before considering the task complete.
4. Keep tenant/environment inputs consistent with what the module expects
   (`tenant_name`, `environment`, `enable_dynamodb`, `enable_ecr`).
5. Respect the naming convention: folder names are tenant IDs (uppercase),
   environment subfolder names are lowercase.
