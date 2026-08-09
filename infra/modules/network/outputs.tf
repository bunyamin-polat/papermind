output "vpc_id" {
  value = aws_vpc.this.id
}

output "private_subnet_ids" {
  description = "Where the database lives. No route to the internet."
  value       = aws_subnet.private[*].id
}

output "db_subnet_group_name" {
  value = aws_db_subnet_group.this.name
}

output "database_security_group_id" {
  description = "Attached to the database itself."
  value       = aws_security_group.database.id
}

output "client_security_group_id" {
  description = <<-EOT
    Attach this to anything that must reach the database. Membership is the grant, so a
    client's address never has to be written down.
  EOT
  value       = aws_security_group.database_clients.id
}

output "public_subnet_ids" {
  description = "Hold the NAT gateway. Nothing else is placed here."
  value       = aws_subnet.public[*].id
}

output "nat_enabled" {
  value = var.enable_nat
}
