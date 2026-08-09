# `budget`

An account-wide monthly cost budget with email alerts. **Apply this before anything else
in a new AWS account.** A NAT gateway you forgot about is about $32 a month, forever, for
nothing; this module is what tells you.

The budget itself is free. It costs nothing to leave in place, and there is no reason to
ever destroy it.

## Usage

```hcl
module "budget" {
  source = "../../modules/budget"

  name         = "slipway-monthly"
  limit_amount = "10"
  alert_emails = ["you@example.com"]
}
```

## What it creates

| Resource | Purpose |
|----------|---------|
| `aws_budgets_budget` | Monthly `COST` budget, account-wide |
| Notifications | One per threshold: actual spend at 50/80/100 %, plus a forecast alert at 100 % |
| `aws_sns_topic` (optional) | Only when `create_sns_topic = true`, for automation that subscribes later |

`include_credit` and `include_refund` are both `false`, so free-tier credits cannot hide
what the account is genuinely costing.

## Prerequisites

**Billing access must be activated for IAM.** In the root account: *Account → IAM user and
role access to billing information → Activate*. Without it every `aws budgets` call fails
with `AccessDenied`, no matter what the principal's IAM policy says.

## Notes

- Budgets is a **global** service reached through `us-east-1`. The budget is not scoped to
  the region you apply from, and there is no point creating one per region.
- Forecast alerts need a few days of usage history before AWS will produce a forecast.
  Actual-spend alerts work immediately.
- Email subscribers do not need to confirm a subscription; SNS subscribers do.
- `aws_budgets_budget` does not accept tags, so the module's `tags` variable applies only
  to the optional SNS topic. Set tags for everything else via the provider's
  `default_tags`.

## Inputs

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `name` | string | — | Budget name, appears in alert emails |
| `limit_amount` | string | — | Monthly limit, e.g. `"10"` |
| `limit_currency` | string | `"USD"` | Currency of the limit |
| `alert_emails` | list(string) | — | Recipients; at least one is required |
| `actual_thresholds` | list(number) | `[50, 80, 100]` | Percentages of the limit that alert on actual spend |
| `forecast_threshold` | number | `100` | Percentage that alerts on forecast spend; `null` disables |
| `time_period_start` | string | `"2026-01-01_00:00"` | Tracking start, `YYYY-MM-DD_HH:MM` |
| `create_sns_topic` | bool | `false` | Also publish alerts to a new SNS topic |
| `tags` | map(string) | `{}` | Tags for the SNS topic |

## Outputs

`budget_name`, `budget_arn`, `sns_topic_arn` (null unless the topic is created).
