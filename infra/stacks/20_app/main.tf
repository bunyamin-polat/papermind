# 20_app — the deployable application, one workspace per environment.
#
# `terraform workspace select dev` and `... prod` keep two isolated state files under one
# configuration. Everything that differs between them arrives as variables generated from
# `slipway.yaml` by the deploy scripts; nothing in this file knows which environment it is
# beyond terraform.workspace.

locals {
  environment = terraform.workspace
  name_prefix = "${var.project}-${local.environment}"

  on_lambda    = var.compute_target == "lambda"
  on_apprunner = var.compute_target == "apprunner"

  image_uri = "${data.aws_ecr_repository.app.repository_url}:${var.image_tag}"

  # Whichever target is in use, the rest of the stack — CloudFront, the outputs, the
  # smoke test — talks to this one value and never asks which.
  app_url = local.on_lambda ? module.app[0].function_url : module.service[0].service_url
}

# The workspace is load-bearing here: it names resources and separates state. Applying
# from `default` would create resources called "slipway-default-app" and quietly put
# them in the wrong state file, which is the kind of mistake that is discovered later.
data "aws_caller_identity" "current" {
  lifecycle {
    postcondition {
      condition     = terraform.workspace != "default"
      error_message = "Select a workspace first: terraform workspace select dev (or prod). The default workspace is not used in this stack."
    }
  }
}

# Created once by 00_bootstrap and shared by every environment; environments are told
# apart by image tag, not by having a registry each.
data "aws_ecr_repository" "app" {
  name = var.ecr_repository_name
}

module "app" {
  count  = local.on_lambda ? 1 : 0
  source = "../../modules/lambda_container"

  function_name = "${local.name_prefix}-app"
  image_uri     = local.image_uri

  architecture = "x86_64"
  memory_size  = var.memory_size
  timeout      = var.timeout

  log_retention_days = var.log_retention_days

  create_function_url = true
  invoke_mode         = "RESPONSE_STREAM"

  # No CORS block: one origin serves both the page and the API, whether that origin is
  # the Function URL directly or CloudFront in front of it.
}

module "service" {
  count  = local.on_apprunner ? 1 : 0
  source = "../../modules/apprunner_service"

  service_name = "${local.name_prefix}-app"
  image_uri    = local.image_uri

  cpu    = var.apprunner_cpu
  memory = var.apprunner_memory
}

module "site" {
  count  = var.enable_cdn ? 1 : 0
  source = "../../modules/static_site"

  name        = local.name_prefix
  price_class = var.cdn_price_class

  # CloudFront wants a bare host: no scheme, no trailing slash.
  api_origin_domain = replace(replace(local.app_url, "https://", ""), "/", "")
}

# Lambda only for now. App Runner publishes a different set of metrics under a different
# namespace, and a dashboard whose panels are silently empty is worse than no dashboard.
module "observability" {
  count  = var.enable_observability && local.on_lambda ? 1 : 0
  source = "../../modules/observability"

  name           = local.name_prefix
  function_name  = module.app[0].function_name
  log_group_name = module.app[0].log_group_name
  region         = var.region
  alert_emails   = var.alert_emails

  cdn_distribution_id = var.enable_cdn ? module.site[0].distribution_id : null
}
