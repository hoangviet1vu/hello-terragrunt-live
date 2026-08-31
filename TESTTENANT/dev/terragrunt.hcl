include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "git::git@github.com:hoangviet1vu/hello-terragrunt-modules.git//?ref=main"
}

inputs = {
  tenant_name     = "TESTTENANT"
  environment     = "dev"
  enable_dynamodb = true
  enable_ecr      = false
}
