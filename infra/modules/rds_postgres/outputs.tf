output "endpoint" {
  value = aws_db_instance.this.address
}

output "port" {
  value = aws_db_instance.this.port
}

output "database_name" {
  value = aws_db_instance.this.db_name
}

output "secret_arn" {
  description = <<-EOT
    Connection details, including the URL. The application reads this at startup rather
    than receiving a password as an environment variable, where it would be visible in
    the console to anyone with read access to the function.
  EOT
  value       = aws_secretsmanager_secret.database.arn
}

output "secret_name" {
  value = aws_secretsmanager_secret.database.name
}
