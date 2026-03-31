terraform {
  required_version = ">= 1.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Intentionally local — this bootstrap config manages only the state backend resources.
  # Commit terraform.tfstate to git so the team can manage the bucket/table.
}

provider "aws" {
  region  = "ap-south-1"
  profile = "deepansh-af"

  default_tags {
    tags = {
      Project   = "quiz-backend"
      ManagedBy = "terraform"
    }
  }
}
