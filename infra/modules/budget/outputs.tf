output "budget_name" {
  description = "Name of the budget, for looking it up in the console or the CLI."
  value       = aws_budgets_budget.this.name
}

output "budget_arn" {
  description = "ARN of the budget."
  value       = aws_budgets_budget.this.arn
}

output "sns_topic_arn" {
  description = "ARN of the alert topic, or null when create_sns_topic is false."
  value       = var.create_sns_topic ? aws_sns_topic.alerts[0].arn : null
}
