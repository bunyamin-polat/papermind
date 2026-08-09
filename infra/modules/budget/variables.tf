variable "name" {
  description = "Budget name. Shown in the AWS Budgets console and in every alert email."
  type        = string
}

variable "limit_amount" {
  description = "Monthly spend limit that the thresholds are measured against, in limit_currency."
  type        = string

  validation {
    condition     = can(tonumber(var.limit_amount)) && tonumber(var.limit_amount) > 0
    error_message = "limit_amount must be a positive number, given as a string (e.g. \"10\")."
  }
}

variable "limit_currency" {
  description = "Currency of limit_amount. AWS bills in USD unless you have arranged otherwise."
  type        = string
  default     = "USD"
}

variable "alert_emails" {
  description = "Email addresses that receive the alerts. At least one, or the budget is decorative."
  type        = list(string)

  validation {
    condition     = length(var.alert_emails) > 0
    error_message = "A budget with no subscribers alerts nobody. Provide at least one email address."
  }
}

variable "actual_thresholds" {
  description = "Percentages of limit_amount that trigger an alert once actually spent."
  type        = list(number)
  default     = [50, 80, 100]
}

variable "forecast_threshold" {
  description = <<-EOT
    Percentage of limit_amount that triggers an alert when AWS *forecasts* the month will
    reach it. This is the one that warns you early — actual-spend alerts arrive after the
    money is gone. Set to null to disable.
  EOT
  type        = number
  default     = 100
}

variable "time_period_start" {
  description = "When the budget starts tracking. Format: YYYY-MM-DD_HH:MM. Any past date is fine for a monthly budget."
  type        = string
  default     = "2026-01-01_00:00"
}

variable "create_sns_topic" {
  description = <<-EOT
    Also publish alerts to an SNS topic, so alarms and automation can subscribe later.
    Email alerts do not need this. Leave false until something actually consumes the topic.
  EOT
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags applied to resources in this module that support tagging."
  type        = map(string)
  default     = {}
}
