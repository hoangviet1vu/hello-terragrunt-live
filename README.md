# hello-terragrunt-live

Live infrastructure: one Terragrunt unit per tenant + environment. Pulls
modules from
[hello-terragrunt-modules](https://github.com/hoangviet1vu/hello-terragrunt-modules).

## Layout

```
terragrunt.hcl            # root: state backend + AWS provider
PRDCV/
  dev/terragrunt.hcl      # module v1.0.0, dynamodb=on,  ecr=off
  prod/terragrunt.hcl     # module v1.0.0, dynamodb=on,  ecr=on
```

Each leaf pins a module version (`?ref=`) and passes the per-env inputs.
Add a tenant by copying `PRDCV/` to a new folder; add an environment by
copying a leaf.

## Before you run

Remote state is stored in a **pre-existing S3 bucket** that is not created
or managed by Terragrunt. You must provision the bucket separately before
running any Terragrunt commands.

Set the following environment variables:

| Variable | Required | Purpose |
|----------|----------|---------|
| `TG_STATE_BUCKET` | Yes | S3 bucket name used for remote state storage |
| `AWS_REGION` | Yes | AWS region for the remote state backend and AWS provider |

```bash
export TG_STATE_BUCKET=<bucket-name>
export AWS_REGION=ap-southeast-2
```

Then ensure:

1. AWS credentials are available (e.g. via `aws configure` or environment variables).
2. Git can read the modules repo (see auth note below).

## Run

```bash
cd PRDCV/dev
terragrunt plan
terragrunt apply
```

State lands at `s3://<state-bucket>/PRDCV/dev/terraform.tfstate`
(the key is derived from the folder path), fully isolated per tenant/env.

## Auth note — private modules repo

`git::https://...` over HTTPS needs a credential for a **private** repo.
Options:

- Use SSH instead:
  `source = "git::git@github.com:hoangviet1vu/hello-terragrunt-modules.git//tenant-base?ref=v1.0.0"`
- Or configure a token, e.g. a git URL rewrite:
  `git config --global url."https://<TOKEN>@github.com/".insteadOf "https://github.com/"`

If the modules repo is public, plain HTTPS works with no setup.