output "service_url" {
  description = "Public HTTPS URL of the service."
  value       = "https://${aws_apprunner_service.this.service_url}"
}

output "service_arn" {
  description = "ARN of the service."
  value       = aws_apprunner_service.this.arn
}

output "service_id" {
  description = "Service ID, used as the dimension for its CloudWatch metrics."
  value       = aws_apprunner_service.this.service_id
}

output "status" {
  description = "RUNNING once it is serving. Anything else and the URL will not answer."
  value       = aws_apprunner_service.this.status
}
