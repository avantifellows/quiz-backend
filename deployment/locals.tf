locals {
  environment_prefix = terraform.workspace == "default" ? "staging-QB-" : "${terraform.workspace}-QB-"
}

data "dotenv" "env_file" {
  filename = (
    terraform.workspace == "default" || terraform.workspace == "staging"
  ) ? ".env.staging" : ".env.production"
}
