# Standalone root config for the terragrunt plan dry-run harness only.
#
# This mirrors the repo-root root.hcl so a fixture leaf can `include` a parent
# root without depending on the repository root. It is NOT used by the live
# workflow; the workflow operates on real leaf units under <TENANT>/<env>/ which
# include the repo-root root.hcl. Keeping a copy here lets the manual
# terragrunt-plan harness exercise backend resolution in isolation.

remote_state {
  backend = "s3"
  config = {
    bucket  = get_env("TG_STATE_BUCKET")
    key     = "${path_relative_to_include()}/terraform.tfstate"
    region  = get_env("AWS_REGION")
    encrypt = true
  }
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
}

generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
provider "aws" {
  region = "${get_env("AWS_REGION")}"
}
EOF
}
