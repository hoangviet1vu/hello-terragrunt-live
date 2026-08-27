---
inclusion: auto
---

# Tech Stack

## Infrastructure as Code

| Tool        | Role                                      |
|-------------|-------------------------------------------|
| Terraform   | Resource provisioning engine              |
| Terragrunt  | DRY orchestration, remote state, includes |
| HCL         | Configuration language for both tools     |

## Cloud Providers

| Provider | Usage                                        |
|----------|----------------------------------------------|
| AWS      | Primary — S3, DynamoDB, ECR                  |
| Azure    | Secondary / future — supported by modules    |

## Code Quality Tools

| Tool           | Purpose                          | Command                    |
|----------------|----------------------------------|----------------------------|
| terraform fmt  | Formatting HCL source code       | `terraform fmt -recursive .` |
| tflint         | Linting and checkstyle for HCL   | `tflint --recursive`         |

## Workflow

After any code change:
1. Format: `terraform fmt -recursive .`
2. Lint: `tflint --recursive`
3. Fix any reported issues before committing.

## State Management

- Backend: S3 bucket with DynamoDB lock table.
- State key derived from folder path: `<tenant-id>/<env>/terraform.tfstate`.
- Encryption enabled.

## Module Source

- Repository: https://github.com/hoangviet1vu/hello-terragrunt-modules
- Pinned via git tag: `?ref=vX.Y.Z`
- Protocol: HTTPS (public) or SSH (private).
