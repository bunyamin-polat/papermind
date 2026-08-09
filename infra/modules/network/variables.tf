variable "name" {
  description = "Prefix for every resource in this module."
  type        = string
}

variable "cidr_block" {
  description = "VPC CIDR. /20 leaves room for the four /24 subnets cidrsubnet() carves out."
  type        = string
  default     = "10.20.0.0/20"
}

variable "enable_nat" {
  description = <<-EOT
    A NAT gateway costs ~$32/month — more than the db.t4g.micro it exists to keep
    private. It is required only because the compute must sit inside the VPC to reach a
    private database, and from there it still has to call OpenAI. Set false for a
    deployment whose compute makes no outbound calls; the private subnets then have no
    default route at all.
  EOT
  type        = bool
  default     = true
}

variable "tags" {
  description = "Extra tags. Provider default_tags already covers project and environment."
  type        = map(string)
  default     = {}
}
