include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "git::git@github.com:hoangviet1vu/hello-terragrunt-modules.git//?ref=v1.0.0"
}

inputs = {
  tenant_name     = "FIXTURESSH"
  environment     = "dev"
  enable_dynamodb = true
  enable_ecr      = false
}
