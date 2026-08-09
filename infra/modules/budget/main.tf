# AWS Budgets is a global service whose API lives in us-east-1. The provider handles
# that, but note that a budget is account-wide: it is not scoped to the region you
# happen to be applying from.

locals {
  # Budgets notifications are one resource block each, so build the full set first:
  # every actual-spend threshold, plus the forecast threshold when enabled.
  actual_notifications = [
    for t in var.actual_thresholds : {
      key            = "actual-${t}"
      notification   = "ACTUAL"
      threshold      = t
      comparison     = "GREATER_THAN"
      threshold_type = "PERCENTAGE"
    }
  ]

  forecast_notifications = var.forecast_threshold == null ? [] : [
    {
      key            = "forecasted-${var.forecast_threshold}"
      notification   = "FORECASTED"
      threshold      = var.forecast_threshold
      comparison     = "GREATER_THAN"
      threshold_type = "PERCENTAGE"
    }
  ]

  notifications = {
    for n in concat(local.actual_notifications, local.forecast_notifications) :
    n.key => n
  }
}

resource "aws_budgets_budget" "this" {
  name         = var.name
  budget_type  = "COST"
  limit_amount = var.limit_amount
  limit_unit   = var.limit_currency
  time_unit    = "MONTHLY"

  time_period_start = var.time_period_start

  cost_types {
    # Credits and refunds are excluded so a free-tier credit cannot mask real spend.
    # You want the alarm to fire on what the account is actually costing.
    include_credit = false
    include_refund = false
  }

  dynamic "notification" {
    for_each = local.notifications

    content {
      comparison_operator        = notification.value.comparison
      notification_type          = notification.value.notification
      threshold                  = notification.value.threshold
      threshold_type             = notification.value.threshold_type
      subscriber_email_addresses = var.alert_emails
      subscriber_sns_topic_arns  = var.create_sns_topic ? [aws_sns_topic.alerts[0].arn] : []
    }
  }
}

resource "aws_sns_topic" "alerts" {
  count = var.create_sns_topic ? 1 : 0

  name = "${var.name}-alerts"
  tags = var.tags
}

# AWS Budgets must be allowed to publish to the topic; without this the budget
# creates fine and then silently never delivers.
resource "aws_sns_topic_policy" "allow_budgets" {
  count = var.create_sns_topic ? 1 : 0

  arn    = aws_sns_topic.alerts[0].arn
  policy = data.aws_iam_policy_document.sns_topic_policy[0].json
}

data "aws_iam_policy_document" "sns_topic_policy" {
  count = var.create_sns_topic ? 1 : 0

  statement {
    sid     = "AllowBudgetsToPublish"
    effect  = "Allow"
    actions = ["SNS:Publish"]

    principals {
      type        = "Service"
      identifiers = ["budgets.amazonaws.com"]
    }

    resources = [aws_sns_topic.alerts[0].arn]
  }
}
