variable "service_name" {
  description = "Name of the App Runner service. Also names its ECR access role."
  type        = string
}

variable "image_uri" {
  description = <<-EOT
    Full ECR image URI including the tag. The same image Lambda runs — App Runner simply
    starts the container and sends it HTTP, and the Lambda Web Adapter baked into it never
    activates outside Lambda.
  EOT
  type        = string
}

variable "port" {
  description = "Port the container listens on. Must match what the image serves."
  type        = string
  default     = "8080"
}

variable "cpu" {
  description = <<-EOT
    vCPU per instance: "0.25 vCPU", "0.5 vCPU", "1 vCPU", "2 vCPU" or "4 vCPU".

    Unlike Lambda you are billed for provisioned memory continuously and for CPU only
    while a request is being served — so the floor is never zero, and this number is the
    ceiling on how fast a single request can be.
  EOT
  type        = string
  default     = "0.25 vCPU"
}

variable "memory" {
  description = "Memory per instance: \"0.5 GB\", \"1 GB\", \"2 GB\", \"3 GB\" or \"4 GB\"."
  type        = string
  default     = "0.5 GB"
}

variable "environment_variables" {
  description = "Environment variables for the container."
  type        = map(string)
  default     = {}
}

variable "health_check_path" {
  description = "Path App Runner polls to decide whether an instance is healthy."
  type        = string
  default     = "/healthz"
}

variable "min_size" {
  description = <<-EOT
    Minimum instances. App Runner's floor is 1: it does not scale to zero, which is the
    entire trade — no cold starts, and a bill that never reaches zero either.
  EOT
  type        = number
  default     = 1

  validation {
    condition     = var.min_size >= 1
    error_message = "App Runner cannot scale to zero; min_size must be at least 1."
  }
}

variable "max_size" {
  description = <<-EOT
    Maximum instances. AWS defaults this to 25, which is a large bill waiting for a
    traffic spike or a retry loop. Two is a deliberate ceiling for a portfolio project.
  EOT
  type        = number
  default     = 2
}

variable "max_concurrency" {
  description = "Requests one instance handles before another is started."
  type        = number
  default     = 100
}

variable "auto_deployments_enabled" {
  description = <<-EOT
    Let App Runner redeploy by itself whenever the image tag is overwritten in ECR.

    Off on purpose: deploys belong to `deploy.py` and the pipeline, where they are
    recorded, gated and reversible. An infrastructure component that redeploys itself on
    a registry push is a deploy nobody approved and nobody can find afterwards.
  EOT
  type        = bool
  default     = false
}

variable "tags" {
  description = "Extra tags on top of the provider's default_tags."
  type        = map(string)
  default     = {}
}
