include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "git::https://github.com/hoangviet1vu/hello-terragrunt-modules.git//?ref=v1.0.0"
}

inputs = {
  tenant_name     = "FIXTUREHTTPS"
  environment     = "dev"
  enable_dynamodb = false
  enable_ecr      = true
}
