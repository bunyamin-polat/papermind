# 00_bootstrap — the plumbing every other stack depends on.
#
# Applied in two phases on a fresh account, on purpose:
#   phase 1 (applied 2026-08-04): the budget alarm, and nothing else
#   phase 2 (state.tf, ecr.tf):   remote state bucket, ECR repository
#
# The order is the point. The budget has to exist before the first billable resource,
# and splitting the commits gets that for free without `terraform apply -target`.

module "budget" {
  source = "../../modules/budget"

  name         = "${var.project}-monthly"
  limit_amount = var.budget_limit_usd
  alert_emails = var.budget_alert_emails
}
