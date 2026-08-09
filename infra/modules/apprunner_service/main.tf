# The always-warm alternative to lambda_container, running the identical image.
#
# The trade, stated plainly: no cold starts, and no scale to zero. App Runner keeps at
# least one instance provisioned and bills for its memory around the clock, so an idle
# service costs a few dollars a month where an idle Lambda costs nothing. In exchange the
# first request of the day is as fast as the thousandth.

# App Runner pulls from a private ECR repository as itself, not as you, so it needs a
# role of its own. Note the principal: build.apprunner.amazonaws.com, not
# tasks.apprunner.amazonaws.com — that one is the *instance* role, for what the running
# code is allowed to do, and using the wrong one fails at pull time with a message about
# access to the repository.
data "aws_iam_policy_document" "ecr_access_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["build.apprunner.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecr_access" {
  name               = "${var.service_name}-ecr-access"
  assume_role_policy = data.aws_iam_policy_document.ecr_access_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "ecr_access" {
  role       = aws_iam_role.ecr_access.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

resource "aws_apprunner_auto_scaling_configuration_version" "this" {
  auto_scaling_configuration_name = replace(var.service_name, "_", "-")

  min_size        = var.min_size
  max_size        = var.max_size
  max_concurrency = var.max_concurrency

  tags = var.tags

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_apprunner_service" "this" {
  service_name = var.service_name

  source_configuration {
    auto_deployments_enabled = var.auto_deployments_enabled

    authentication_configuration {
      access_role_arn = aws_iam_role.ecr_access.arn
    }

    image_repository {
      image_identifier      = var.image_uri
      image_repository_type = "ECR"

      image_configuration {
        port                          = var.port
        runtime_environment_variables = var.environment_variables
      }
    }
  }

  instance_configuration {
    cpu    = var.cpu
    memory = var.memory
  }

  health_check_configuration {
    protocol = "HTTP"
    path     = var.health_check_path

    # Defaults are slow to notice a sick instance and slow to declare a new one ready.
    interval            = 10
    timeout             = 5
    healthy_threshold   = 1
    unhealthy_threshold = 3
  }

  auto_scaling_configuration_arn = aws_apprunner_auto_scaling_configuration_version.this.arn

  tags = var.tags

  depends_on = [aws_iam_role_policy_attachment.ecr_access]
}
