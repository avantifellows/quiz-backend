terraform {
  required_version = ">= 1.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # TODO: Add S3 backend later for team collaboration
  # backend "s3" {
  #   bucket         = "quiz-terraform-state"
  #   key            = "testing/terraform.tfstate"
  #   region         = "ap-south-1"
  #   dynamodb_table = "terraform-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = var.environment
      Project     = "quiz-backend"
      ManagedBy   = "terraform"
    }
  }
}
