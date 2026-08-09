variable "name" {
  description = "Base name for the dashboard, alarms and topic. Usually <project>-<environment>."
  type        = string
}

variable "function_name" {
  description = "Lambda function to watch."
  type        = string
}

variable "log_group_name" {
  description = "Its log group. The cold-start widget reads Init Duration out of the REPORT lines here."
  type        = string
}

variable "region" {
  description = "Region the metrics live in."
  type        = string
}

variable "alert_emails" {
  description = <<-EOT
    Addresses subscribed to the alarm topic. Empty means the alarms still fire and still
    show in the console, they just do not reach anybody — fine for dev, wrong for prod.

    Unlike budget alerts, SNS email subscriptions must be confirmed from the inbox before
    they deliver anything.
  EOT
  type        = list(string)
  default     = []
}

variable "cdn_distribution_id" {
  description = "CloudFront distribution to add to the dashboard, or null when there is none."
  type        = string
  default     = null
}

variable "error_threshold" {
  description = "Errors in a five-minute window before the alarm fires. One is the honest number for a low-traffic app."
  type        = number
  default     = 1
}

variable "duration_threshold_ms" {
  description = <<-EOT
    p95 duration that counts as too slow. The default is a third of the usual 30 s
    timeout: by the time p95 reaches it, timeouts are coming.

    Note that a streaming endpoint holds its invocation open for the whole response, so
    this is measuring the length of the answer as much as the speed of the code.
  EOT
  type        = number
  default     = 10000
}

variable "create_dashboard" {
  description = "CloudWatch gives three dashboards free per account; the fourth costs $3/month."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Extra tags on top of the provider's default_tags."
  type        = map(string)
  default     = {}
}
