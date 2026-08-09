variable "function_name" {
  description = "Name of the Lambda function. Also names its log group and IAM role."
  type        = string
}

variable "image_uri" {
  description = <<-EOT
    Full ECR image URI including the tag, e.g.
    123456789012.dkr.ecr.us-east-1.amazonaws.com/slipway-app:a1b2c3d.

    The image must be built for the architecture below and pushed without buildx
    attestations (`--provenance=false --sbom=false`), or Lambda rejects the manifest.
  EOT
  type        = string
}

variable "architecture" {
  description = "x86_64 or arm64. Must match how the image was built."
  type        = string
  default     = "x86_64"

  validation {
    condition     = contains(["x86_64", "arm64"], var.architecture)
    error_message = "architecture must be either x86_64 or arm64."
  }
}

variable "memory_size" {
  description = <<-EOT
    Megabytes of memory. CPU is allocated in proportion, so this is really a speed dial:
    lowering it saves money per millisecond and lengthens cold starts. Measured on the
    example app at 1024 MB: 3391 ms cold start, 88 MB actually used.
  EOT
  type        = number
  default     = 1024
}

variable "timeout" {
  description = <<-EOT
    Seconds before Lambda kills the invocation. Streaming responses hold the invocation
    open for their whole duration and are billed for it, so this is a cost ceiling as
    much as a safety one.
  EOT
  type        = number
  default     = 30
}

variable "environment_variables" {
  description = <<-EOT
    Extra environment variables. The Lambda Web Adapter settings are baked into the
    image; anything set here overrides them, which is the escape hatch for changing
    behaviour without a rebuild.
  EOT
  type        = map(string)
  default     = {}
}

variable "log_retention_days" {
  description = <<-EOT
    CloudWatch log retention. The default when Lambda creates its own log group is
    "never expire", which is a bill that grows forever and is the single most common
    piece of forgotten AWS spend.
  EOT
  type        = number
  default     = 14
}

variable "create_function_url" {
  description = "Create a Function URL. Turn this off when the function sits behind API Gateway or CloudFront only."
  type        = bool
  default     = true
}

variable "function_url_authorization" {
  description = <<-EOT
    NONE means anyone with the URL can invoke it. That is right for a public web app and
    wrong for everything else — AWS_IAM requires SigV4-signed requests instead.
  EOT
  type        = string
  default     = "NONE"

  validation {
    condition     = contains(["NONE", "AWS_IAM"], var.function_url_authorization)
    error_message = "function_url_authorization must be NONE or AWS_IAM."
  }
}

variable "invoke_mode" {
  description = <<-EOT
    RESPONSE_STREAM or BUFFERED. This is half of what streaming needs — the other half is
    AWS_LWA_INVOKE_MODE=response_stream inside the image. With either one missing the
    response still arrives and still looks correct, just all at once at the end, which is
    exactly what makes it easy to ship broken.
  EOT
  type        = string
  default     = "RESPONSE_STREAM"

  validation {
    condition     = contains(["RESPONSE_STREAM", "BUFFERED"], var.invoke_mode)
    error_message = "invoke_mode must be RESPONSE_STREAM or BUFFERED."
  }
}

variable "cors" {
  description = <<-EOT
    CORS rules for the Function URL. Null disables CORS entirely, which is correct when
    the page and the API share an origin — as they do here, since FastAPI serves both.
  EOT
  type = object({
    allow_origins = list(string)
    allow_methods = list(string)
    allow_headers = optional(list(string), [])
    max_age       = optional(number, 0)
  })
  default = null
}

variable "additional_policy_arns" {
  description = "IAM policies to attach beyond logging, e.g. read access to a data bucket."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Extra tags. Provider default_tags already covers project and environment."
  type        = map(string)
  default     = {}
}
