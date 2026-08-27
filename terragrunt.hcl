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
