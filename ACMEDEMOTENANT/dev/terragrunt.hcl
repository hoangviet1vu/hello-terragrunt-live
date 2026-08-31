include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "git::git@github.com:hoangviet1vu/hello-terragrunt-modules.git//?ref=main"
}

inputs = {
  tenant_name     = "ACMEDEMOTENANT"
  environment     = "dev"
  enable_dynamodb = false
  enable_ecr      = true
}
