# Copy to terraform.tfvars and fill in. terraform.tfvars is gitignored — it is where
# real values live, and they never reach the repository.
#
#   cp terraform.tfvars.example terraform.tfvars

project = "slipway"
region  = "us-east-1"

budget_limit_usd    = "10"
budget_alert_emails = ["bunyaminpolatch@gmail.com"]
github_repository   = "bunyamin-polat/slipway"
