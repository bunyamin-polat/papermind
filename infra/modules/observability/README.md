# `observability`

Three alarms and one dashboard for a Lambda function, plus the CloudFront panel when
there is a distribution in front of it.

Deliberately small. An observability setup nobody reads is worse than none: it costs
money and it creates the impression of coverage. Three alarms that mean something, and
one page that answers *is it up, is it slow, is it cold*.

## Usage

```hcl
module "observability" {
  source = "../../modules/observability"

  name           = "slipway-dev"
  function_name  = module.app.function_name
  log_group_name = module.app.log_group_name
  region         = var.region
  alert_emails   = var.alert_emails
}
```

## The alarms

| Alarm | Fires when | Why it is worth waking up for |
| --- | --- | --- |
| `-errors` | ≥ 1 error in 5 minutes | On a low-traffic app one error is a real error, not noise |
| `-throttles` | ≥ 1 throttle in 5 minutes | Either traffic grew or a concurrency limit is set too low |
| `-slow` | p95 duration over the threshold for two windows | Two windows so one long answer does not page anyone |

Every alarm uses `treat_missing_data = "notBreaching"`. A function that scales to zero
emits no datapoints while idle, and "no traffic" must never read as "broken" — otherwise
the alarms fire every night and get muted, which is how monitoring dies.

`-errors` also sends an `ok_action`, so the recovery arrives in the same inbox as the
alert. An alarm that only tells you about breakage leaves you refreshing a console.

## Cold starts are not a metric

CloudWatch has no cold-start metric. The number exists only in the `REPORT` line Lambda
writes at the end of an invocation, as `Init Duration`, so the dashboard charts it with a
Logs Insights query rather than a metric. Measured on this app: 3391 ms at 1024 MB for a
317 MB image.

## Cost

- **Alarms**: $0.10/month each. The AWS free tier covers ten, so three is free in practice.
- **Dashboard**: the first three per account are free; the fourth is $3/month.
- **Logs Insights**: charged per GB scanned. The widget scans one log group over the
  dashboard's time range, which is pennies here and would not be on a chatty service.

## Inputs

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `name` | string | — | Names the dashboard, alarms and topic |
| `function_name` | string | — | Lambda to watch |
| `log_group_name` | string | — | Source for the cold-start widget |
| `region` | string | — | Region the metrics live in |
| `alert_emails` | list(string) | `[]` | Subscribed to the topic; must be confirmed by email |
| `cdn_distribution_id` | string | `null` | Adds the CloudFront panel |
| `error_threshold` | number | `1` | Errors per 5 minutes before alarming |
| `duration_threshold_ms` | number | `10000` | p95 that counts as too slow |
| `create_dashboard` | bool | `true` | Off to stay under the free three |
| `tags` | map(string) | `{}` | On top of provider `default_tags` |

## Outputs

`sns_topic_arn`, `alarm_names`, `dashboard_name`, `dashboard_url`.
