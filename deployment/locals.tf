locals {
  environment_prefix = terraform.workspace == "default" ? "staging-QB-" : "${terraform.workspace}-QB-"
}
