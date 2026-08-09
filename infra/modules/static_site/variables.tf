variable "name" {
  description = "Base name for the bucket and the distribution comment."
  type        = string
}

variable "bucket_name" {
  description = <<-EOT
    S3 bucket for the static files. Leave null for "<name>-static-<account-id>", since
    bucket names are global across all of AWS and a plain one is almost certainly taken.
  EOT
  type        = string
  default     = null
}

variable "api_origin_domain" {
  description = <<-EOT
    Host of the dynamic origin — a Lambda Function URL with the scheme and trailing slash
    removed, e.g. abc123.lambda-url.us-east-1.on.aws. Null serves only static files.
  EOT
  type        = string
  default     = null
}

variable "api_path_patterns" {
  description = <<-EOT
    Paths routed to the dynamic origin instead of S3. Everything else comes from the
    bucket. `/healthz` is here because smoke tests should check the application, not the
    CDN's copy of a static file.
  EOT
  type        = list(string)
  default     = ["/api/*", "/healthz"]
}

variable "default_root_object" {
  description = "Object served for a request to /."
  type        = string
  default     = "index.html"
}

variable "price_class" {
  description = <<-EOT
    PriceClass_100 is North America and Europe only, and is the cheapest. PriceClass_All
    adds Asia, South America and Oceania at a higher per-request rate — worth it only when
    you have users there.
  EOT
  type        = string
  default     = "PriceClass_100"

  validation {
    condition     = contains(["PriceClass_100", "PriceClass_200", "PriceClass_All"], var.price_class)
    error_message = "price_class must be PriceClass_100, PriceClass_200 or PriceClass_All."
  }
}

variable "tags" {
  description = "Extra tags on top of the provider's default_tags."
  type        = map(string)
  default     = {}
}
