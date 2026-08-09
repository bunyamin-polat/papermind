variable "name" {
  description = "Identifier and name prefix."
  type        = string
}

variable "db_subnet_group_name" {
  type = string
}

variable "security_group_id" {
  description = "The database's own security group, from the network module."
  type        = string
}

variable "database_name" {
  type    = string
  default = "papermind"
}

variable "master_username" {
  type    = string
  default = "papermind"
}

variable "instance_class" {
  description = <<-EOT
    db.t4g.micro holds the 294 MB corpus with room to spare and is the cheapest class
    supporting Postgres 17. Raise it only against a measurement.
  EOT
  type        = string
  default     = "db.t4g.micro"
}

variable "allocated_storage" {
  description = "GB. The corpus is 294 MB; 20 is the RDS minimum."
  type        = number
  default     = 20
}

variable "max_allocated_storage" {
  description = "Ceiling for storage autoscaling. Set equal to allocated_storage to disable."
  type        = number
  default     = 50
}

variable "backup_retention_days" {
  description = "0 disables automated backups. The corpus is reproducible from the arXiv API."
  type        = number
  default     = 1
}

variable "skip_final_snapshot" {
  description = <<-EOT
    True for throwaway environments. `terraform destroy` on a demo should not leave a
    snapshot billing quietly for months after the demo ended.
  EOT
  type        = bool
  default     = true
}

variable "deletion_protection" {
  type    = bool
  default = false
}

variable "secret_recovery_days" {
  description = "0 deletes the secret immediately, so a redeploy can reuse the name."
  type        = number
  default     = 0
}

variable "tags" {
  type    = map(string)
  default = {}
}
