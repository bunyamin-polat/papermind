terraform {
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.60, < 7.0"
    }
  }

  # Values live in backend.hcl, which is gitignored because the bucket name contains the
  # account ID:
  #
  #   cp backend.hcl.example backend.hcl && terraform init -backend-config=backend.hcl
  #
  # With workspaces, each one gets its own key under env:/<workspace>/, so dev and prod
  # never share a state file.
  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = var.project
      Environment = terraform.workspace
      ManagedBy   = "terraform"
      Stack       = "20_app"
    }
  }
}
