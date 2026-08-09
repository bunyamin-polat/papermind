data "aws_caller_identity" "current" {}

output "account_id" {
  description = "The AWS account this stack was applied to. Worth checking before you celebrate."
  value       = data.aws_caller_identity.current.account_id
}

output "region" {
  description = "Region this stack was applied in."
  value       = var.region
}

output "budget_name" {
  description = "Name of the account budget."
  value       = module.budget.budget_name
}

output "state_bucket_name" {
  description = "Remote state bucket. Goes into backend.hcl for every stack, including this one."
  value       = aws_s3_bucket.state.bucket
}

output "ecr_repository_url" {
  description = "Registry URL to build and push against, e.g. <account>.dkr.ecr.<region>.amazonaws.com/slipway-app."
  value       = aws_ecr_repository.app.repository_url
}

output "ecr_repository_name" {
  description = "Repository name, for the deploy scripts and the CI workflow."
  value       = aws_ecr_repository.app.name
}

output "github_actions_role_arn" {
  description = <<-EOT
    Role GitHub Actions assumes. Store it as the AWS_ROLE_ARN repository secret — not
    because an ARN is secret, but because it names the account, which does not belong in
    a public repository.
  EOT
  value       = aws_iam_role.github_actions.arn
}
