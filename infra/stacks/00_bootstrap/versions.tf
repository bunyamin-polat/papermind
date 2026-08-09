terraform {
  # 1.11 is the floor because state locking here is the S3 backend's own
  # (`use_lockfile`), which replaced the deprecated DynamoDB lock table.
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.60, < 7.0"
    }
  }

  # This stack ran on local state until it had created aws_s3_bucket.state, then moved
  # into it. Cloning fresh? Start the same way: comment this block out for the first
  # apply, then put it back and run
  #
  #   cp backend.hcl.example backend.hcl   # fill in from `terraform output`
  #   terraform init -backend-config=backend.hcl -migrate-state
  #
  # The settings are deliberately empty here and live in backend.hcl instead, because
  # the bucket name contains the account ID and that does not belong in the repository.
  # Locking is the backend's own (use_lockfile), set in backend.hcl.
  backend "s3" {}
}

provider "aws" {
  region = var.region

  # Every resource that supports tagging gets these, without repeating them per
  # resource. It is the only way to read a bill and know which project spent what.
  default_tags {
    tags = {
      Project     = var.project
      Environment = "shared"
      ManagedBy   = "terraform"
      Stack       = "00_bootstrap"
    }
  }
}
