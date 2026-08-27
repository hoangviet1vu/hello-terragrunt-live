---
inclusion: auto
---

# Project Layout & Design

## Directory Structure

```
hello-terragrunt-live/
├── terragrunt.hcl                 # Root config: S3 backend + AWS provider
├── <TENANT-ID>/                   # One folder per tenant (UPPERCASE)
│   ├── dev/
│   │   └── terragrunt.hcl        # Dev environment unit
│   └── prod/
│       └── terragrunt.hcl        # Prod environment unit
├── AGENTS.md                      # AI agent guidance
├── README.md                      # Project documentation
└── .kiro/
    └── steering/                  # Kiro steering files
```

## Design Principles

1. **One tenant = one folder** — tenant ID as the folder name, uppercase.
2. **One environment = one subfolder** — lowercase (`dev`, `prod`).
3. **Leaf units are self-contained** — each `terragrunt.hcl` includes the
   root and declares its own source + inputs.
4. **Version pinning** — every leaf pins `?ref=vX.Y.Z` on the modules repo.
5. **State isolation** — state key is `<tenant>/<env>/terraform.tfstate`,
   no cross-contamination between tenants or environments.

## Root Configuration (`terragrunt.hcl`)

Responsibilities:
- Define S3 remote state backend (bucket, region, DynamoDB lock table).
- Generate `provider.tf` with the AWS provider block.
- Shared by all leaves via `include {}`.

## Leaf Configuration (`<tenant>/<env>/terragrunt.hcl`)

Each leaf must specify:
- `include` — pulls in the root config.
- `terraform.source` — git URL to the module with pinned tag.
- `inputs` — tenant_name, environment, enable_dynamodb, enable_ecr.

## Adding a New Tenant

1. Create `<NEW-TENANT-ID>/` at the repo root.
2. Copy environment subfolders from an existing tenant.
3. Update `tenant_name` input in each leaf.

## Adding a New Environment

1. Copy an existing env folder within the tenant directory.
2. Rename to the new environment (e.g. `staging`).
3. Update `environment` and feature flag inputs.

## Module Interface (tenant-base)

| Input            | Type   | Description                    |
|------------------|--------|--------------------------------|
| tenant_name      | string | Tenant identifier              |
| environment      | string | Environment name (dev, prod)   |
| enable_dynamodb  | bool   | Create DynamoDB table          |
| enable_ecr       | bool   | Create ECR repository          |
