# Alarms and one dashboard.
#
# Deliberately small. An observability setup nobody reads is worse than none, because it
# costs money and creates the impression of coverage. Three alarms that mean something,
# and one page that answers "is it up, is it slow, is it cold".

locals {
  has_cdn = var.cdn_distribution_id != null
}

resource "aws_sns_topic" "alerts" {
  name = "${var.name}-alerts"
  tags = var.tags
}

resource "aws_sns_topic_subscription" "email" {
  for_each = toset(var.alert_emails)

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = each.value
}

# ---------------------------------------------------------------------------
# Alarms
# ---------------------------------------------------------------------------

# treat_missing_data = "notBreaching" throughout: a function that scales to zero produces
# no datapoints when idle, and "no traffic" must not read as "broken".

resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name        = "${var.name}-errors"
  alarm_description = "The function returned errors. Check the log group before anything else."

  namespace   = "AWS/Lambda"
  metric_name = "Errors"
  dimensions  = { FunctionName = var.function_name }

  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = var.error_threshold
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "throttles" {
  alarm_name        = "${var.name}-throttles"
  alarm_description = "Invocations were rejected for lack of concurrency. Either traffic grew or a limit is too low."

  namespace   = "AWS/Lambda"
  metric_name = "Throttles"
  dimensions  = { FunctionName = var.function_name }

  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "duration" {
  alarm_name        = "${var.name}-slow"
  alarm_description = "p95 duration crossed the threshold. On a streaming endpoint this measures answer length as much as speed."

  namespace   = "AWS/Lambda"
  metric_name = "Duration"
  dimensions  = { FunctionName = var.function_name }

  extended_statistic  = "p95"
  period              = 300
  evaluation_periods  = 2 # two windows, so one long answer does not page anyone
  threshold           = var.duration_threshold_ms
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_dashboard" "this" {
  count = var.create_dashboard ? 1 : 0

  dashboard_name = var.name

  dashboard_body = jsonencode({
    widgets = concat(
      [
        {
          type   = "metric"
          x      = 0
          y      = 0
          width  = 12
          height = 6
          properties = {
            title  = "Invocations and errors"
            region = var.region
            view   = "timeSeries"
            stat   = "Sum"
            period = 300
            metrics = [
              ["AWS/Lambda", "Invocations", "FunctionName", var.function_name],
              [".", "Errors", ".", ".", { color = "#d62728" }],
              [".", "Throttles", ".", "."],
            ]
          }
        },
        {
          type   = "metric"
          x      = 12
          y      = 0
          width  = 12
          height = 6
          properties = {
            title  = "Duration (ms)"
            region = var.region
            view   = "timeSeries"
            period = 300
            metrics = [
              ["AWS/Lambda", "Duration", "FunctionName", var.function_name, { stat = "Average" }],
              ["...", { stat = "p95" }],
              ["...", { stat = "Maximum" }],
            ]
          }
        },
        {
          # Cold starts are not a CloudWatch metric. They only exist in the REPORT line
          # Lambda writes at the end of an invocation, so the only way to chart them is to
          # query the logs.
          type   = "log"
          x      = 0
          y      = 6
          width  = 24
          height = 6
          properties = {
            title  = "Cold starts (Init Duration, ms)"
            region = var.region
            view   = "table"
            # `bin(1h)` cannot be referenced from a `sort` clause — Logs Insights rejects
            # the whole query with "unexpected symbol found (", and a dashboard widget
            # shows that as a red box you only notice by looking. Aliasing the bin and
            # sorting the alias is what makes it legal.
            query = <<-QUERY
              SOURCE '${var.log_group_name}'
              | filter @type = "REPORT" and ispresent(@initDuration)
              | stats count() as coldStarts,
                      avg(@initDuration) as avgInitMs,
                      max(@initDuration) as maxInitMs
                by bin(1h) as hour
              | sort hour desc
              | limit 24
            QUERY
          }
        },
      ],
      local.has_cdn ? [
        {
          type   = "metric"
          x      = 0
          y      = 12
          width  = 24
          height = 6
          properties = {
            title = "CloudFront"
            # CloudFront metrics are global and only readable from us-east-1, whatever
            # region the rest of the stack lives in.
            region = "us-east-1"
            view   = "timeSeries"
            period = 300
            metrics = [
              ["AWS/CloudFront", "Requests", "DistributionId", var.cdn_distribution_id, "Region", "Global", { stat = "Sum" }],
              [".", "4xxErrorRate", ".", ".", ".", ".", { stat = "Average" }],
              [".", "5xxErrorRate", ".", ".", ".", ".", { stat = "Average", color = "#d62728" }],
            ]
          }
        },
      ] : []
    )
  })
}
