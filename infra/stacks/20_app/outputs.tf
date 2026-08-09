output "environment" {
  description = "Workspace this was applied to. Check it before believing anything else here."
  value       = local.environment
}

output "account_id" {
  description = "Account this environment lives in. Worth confirming before celebrating a prod deploy."
  value       = data.aws_caller_identity.current.account_id
}

output "compute_target" {
  description = "lambda or apprunner."
  value       = var.compute_target
}

output "url" {
  description = <<-EOT
    The live URL — the whole point of the repository. CloudFront's domain when the CDN is
    enabled, otherwise the compute target's own URL. Scripts and smoke tests read this one
    and never need to know how the environment is shaped.
  EOT
  value       = var.enable_cdn ? module.site[0].url : local.app_url
}

output "origin_url" {
  description = "The compute target directly, still reachable even behind CloudFront."
  value       = local.app_url
}

output "function_name" {
  description = "Lambda function name, or null when running on App Runner."
  value       = local.on_lambda ? module.app[0].function_name : null
}

output "service_arn" {
  description = "App Runner service ARN, or null when running on Lambda."
  value       = local.on_apprunner ? module.service[0].service_arn : null
}

output "log_group_name" {
  description = "Lambda log group; `aws logs tail <this> --follow` while testing a deploy."
  value       = local.on_lambda ? module.app[0].log_group_name : null
}

output "image_uri" {
  description = "Exactly which image is deployed. Traceable to a commit."
  value       = local.image_uri
}

output "cdn_enabled" {
  description = "Whether this environment has CloudFront in front of it."
  value       = var.enable_cdn
}

output "static_bucket" {
  description = "Bucket the deploy script syncs static files into, or null without a CDN."
  value       = var.enable_cdn ? module.site[0].bucket_name : null
}

output "distribution_id" {
  description = "Distribution to invalidate after a deploy, or null without a CDN."
  value       = var.enable_cdn ? module.site[0].distribution_id : null
}

output "dashboard_url" {
  description = "CloudWatch dashboard for this environment, or null when there is none."
  value       = length(module.observability) > 0 ? module.observability[0].dashboard_url : null
}

output "alarm_topic_arn" {
  description = "SNS topic the alarms publish to, or null when there is none."
  value       = length(module.observability) > 0 ? module.observability[0].sns_topic_arn : null
}
