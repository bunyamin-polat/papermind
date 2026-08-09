# A container image on Lambda, with a Function URL and response streaming.
#
# Everything here was a checkbox in the console during the manual deploy. Written down,
# the checkboxes become reviewable, repeatable and — the part that matters — deletable.

# Created explicitly rather than letting Lambda create it on first invocation. A log
# group Lambda makes for itself never expires, and "never expire" on a chatty function
# is a bill that grows quietly forever.
resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

data "aws_iam_policy_document" "assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = "${var.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
  tags               = var.tags
}

# Deliberately not AWSLambdaBasicExecutionRole: that managed policy grants writes to
# every log group in the account. This grants writes to exactly one.
data "aws_iam_policy_document" "logging" {
  statement {
    effect = "Allow"

    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    resources = ["${aws_cloudwatch_log_group.this.arn}:*"]
  }
}

resource "aws_iam_role_policy" "logging" {
  name   = "logging"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.logging.json
}

resource "aws_iam_role_policy_attachment" "additional" {
  for_each = toset(var.additional_policy_arns)

  role       = aws_iam_role.this.name
  policy_arn = each.value
}

resource "aws_lambda_function" "this" {
  function_name = var.function_name
  role          = aws_iam_role.this.arn

  package_type  = "Image"
  image_uri     = var.image_uri
  architectures = [var.architecture]

  memory_size = var.memory_size
  timeout     = var.timeout

  dynamic "environment" {
    for_each = length(var.environment_variables) > 0 ? [1] : []

    content {
      variables = var.environment_variables
    }
  }

  tags = var.tags

  # Without this the function can be created before the log group exists, Lambda makes
  # its own with no retention, and the resource here then fails on a name collision.
  depends_on = [
    aws_cloudwatch_log_group.this,
    aws_iam_role_policy.logging,
  ]
}

resource "aws_lambda_function_url" "this" {
  count = var.create_function_url ? 1 : 0

  function_name      = aws_lambda_function.this.function_name
  authorization_type = var.function_url_authorization
  invoke_mode        = var.invoke_mode

  dynamic "cors" {
    for_each = var.cors == null ? [] : [var.cors]

    content {
      allow_origins = cors.value.allow_origins
      allow_methods = cors.value.allow_methods
      allow_headers = cors.value.allow_headers
      max_age       = cors.value.max_age
    }
  }
}

# The console adds this for you when you tick "Auth type: NONE". Through the API it is a
# separate call, and without it the URL exists and answers 403 to everyone.
resource "aws_lambda_permission" "function_url" {
  count = var.create_function_url && var.function_url_authorization == "NONE" ? 1 : 0

  statement_id           = "AllowPublicFunctionUrlInvoke"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.this.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}
