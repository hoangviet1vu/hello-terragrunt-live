include "root" {
  path = find_in_parent_folders()
}

terraform {
  source = "git::https://github.com/hoangviet1vu/hello-terragrunt-modules.git//tenant-base?ref=v1.0.0"
}

inputs = {
  tenant_name     = "EXAMPLE"
  environment     = "dev"
  enable_dynamodb = false
  enable_ecr      = true
}
