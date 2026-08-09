output "sns_topic_arn" {
  description = "Topic the alarms publish to. Subscribe automation here later."
  value       = aws_sns_topic.alerts.arn
}

output "alarm_names" {
  description = "Every alarm this module created."
  value = [
    aws_cloudwatch_metric_alarm.errors.alarm_name,
    aws_cloudwatch_metric_alarm.throttles.alarm_name,
    aws_cloudwatch_metric_alarm.duration.alarm_name,
  ]
}

output "dashboard_name" {
  description = "Dashboard name, or null when it was not created."
  value       = var.create_dashboard ? aws_cloudwatch_dashboard.this[0].dashboard_name : null
}

output "dashboard_url" {
  description = "Direct link to the dashboard."
  value = var.create_dashboard ? format(
    "https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#dashboards/dashboard/%s",
    var.region, var.region, aws_cloudwatch_dashboard.this[0].dashboard_name
  ) : null
}
