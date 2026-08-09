output "function_name" {
  description = "Name of the Lambda function."
  value       = aws_lambda_function.this.function_name
}

output "function_arn" {
  description = "ARN of the Lambda function."
  value       = aws_lambda_function.this.arn
}

output "function_url" {
  description = "Public URL of the function, or null when create_function_url is false."
  value       = var.create_function_url ? aws_lambda_function_url.this[0].function_url : null
}

output "role_arn" {
  description = "ARN of the execution role, for attaching further permissions."
  value       = aws_iam_role.this.arn
}

output "role_name" {
  description = "Name of the execution role."
  value       = aws_iam_role.this.name
}

output "log_group_name" {
  description = "CloudWatch log group. `aws logs tail <this> --follow` is the fastest way to debug a deploy."
  value       = aws_cloudwatch_log_group.this.name
}
