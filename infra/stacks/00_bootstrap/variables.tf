variable "project" {
  description = "Project name. Prefixes resource names and tags every resource."
  type        = string
  default     = "slipway"
}

variable "region" {
  description = <<-EOT
    AWS region for this stack. Pick once and keep it: Bedrock model availability varies
    by region, and you do not want the app in one region and the models in another.
  EOT
  type        = string
}

variable "budget_limit_usd" {
  description = "Monthly budget limit in USD, as a string."
  type        = string
  default     = "10"
}

variable "budget_alert_emails" {
  description = "Who gets the budget alerts."
  type        = list(string)
}

variable "state_bucket_name" {
  description = <<-EOT
    Name of the remote state bucket. Leave null to get "<project>-tfstate-<account-id>",
    which is unique without you having to invent anything. S3 bucket names are global
    across all AWS accounts, so a plain "slipway-tfstate" is almost certainly taken.
  EOT
  type        = string
  default     = null
}

variable "state_noncurrent_version_days" {
  description = "How long superseded state versions are kept before expiry."
  type        = number
  default     = 90
}

variable "ecr_repository_name" {
  description = "Name of the container repository. Leave null to get \"<project>-app\"."
  type        = string
  default     = null
}

variable "ecr_untagged_expire_days" {
  description = "Untagged images (leftovers from failed or superseded builds) expire after this many days."
  type        = number
  default     = 7
}

variable "ecr_max_image_count" {
  description = "How many images to keep in total. Older ones expire; you need a couple for rollback, not fifty."
  type        = number
  default     = 10
}

variable "github_repository" {
  description = <<-EOT
    owner/repo that is allowed to assume the deploy role, e.g. "octocat/slipway".
    The trust policy pins to this exact repository, so no other one — and no fork — can
    assume it.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[^/]+/[^/]+$", var.github_repository))
    error_message = "github_repository must be in owner/repo form."
  }
}

variable "github_oidc_thumbprints" {
  description = <<-EOT
    Certificate thumbprints for GitHub's OIDC issuer. AWS stopped validating these for
    token.actions.githubusercontent.com once it began trusting the issuer's root CA
    directly, but the API still expects the field. These are the long-published values.
  EOT
  type        = list(string)
  default = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]
}

variable "ecr_force_delete" {
  description = <<-EOT
    Allow `terraform destroy` to delete the repository while it still contains images.
    Without it destroy fails, the repository survives, and it keeps billing for storage
    that nobody remembers exists.
  EOT
  type        = bool
  default     = true
}
