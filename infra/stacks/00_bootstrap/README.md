# `00_bootstrap`

One-time plumbing for an AWS account: the budget alarm, and later the remote state
bucket, its lock table and the ECR repository. Applied once per account, not per
environment.

Its state is **local** for now. This is the stack that creates the remote state bucket,
so it cannot keep its state there on the first apply — the classic chicken-and-egg. Once
the bucket exists the backend block is added and the state moved with
`terraform init -migrate-state`.

## Phase 1 — budget only (current)

Nothing here is billable. That is deliberate: the alarm goes up before the first resource
that can cost money.

```bash
cd terraform/stacks/00_bootstrap
cp terraform.tfvars.example terraform.tfvars   # then edit it
terraform init
terraform fmt -check -recursive ../..
terraform validate
terraform plan
terraform apply
```

Expect one resource: `module.budget.aws_budgets_budget.this`.

### Before you apply

Billing access must be activated for IAM, in the **root** account:
*Account → IAM user and role access to billing information → Activate*. Without it the
apply fails with `AccessDenied` on `budgets:CreateBudget`, regardless of the principal's
IAM policy.

### Verify

```bash
aws budgets describe-budgets --account-id "$(aws sts get-caller-identity --query Account --output text)"
```

The AWS Budgets console should show one monthly budget with four notifications: actual
spend at 50 %, 80 % and 100 %, and forecast at 100 %.

## Phase 2 — state and the registry

Adds the S3 state bucket and the ECR repository, then migrates this stack's own state
into the bucket.

```bash
terraform plan     # expect 8 to add: bucket + its 5 settings + policy, ECR repo + lifecycle policy
terraform apply
```

Then move the state off the local disk:

```bash
cp backend.hcl.example backend.hcl
terraform output state_bucket_name          # paste this into backend.hcl
```

Uncomment `backend "s3" {}` in `versions.tf`, then:

```bash
terraform init -backend-config=backend.hcl -migrate-state
```

Terraform asks whether to copy the existing state to the new backend. Answer `yes`. After
it succeeds, `terraform.tfstate` on disk is a leftover copy — `terraform plan` should
report no changes, and only then is it safe to delete the local file.

### What gets created, and why

| Resource | Why |
| --- | --- |
| `aws_s3_bucket.state` | Holds every stack's state. `prevent_destroy` is set — losing it means losing the record of everything Terraform built. |
| Versioning | The recovery path for a corrupted or truncated state file. |
| SSE-S3 encryption | Encrypted at rest without the $1/month of a customer managed KMS key. |
| Public access block | State files list your infrastructure. All four blocks on. |
| Lifecycle rule | Superseded versions expire after 90 days, so the bucket stays effectively free. |
| Bucket policy | Denies non-TLS requests. |
| `aws_ecr_repository.app` | One repository for every environment; environments differ by tag, not by registry. Scan on push is free. |
| ECR lifecycle policy | Untagged images expire after 7 days, at most 10 kept. Images are hundreds of MB and ECR bills $0.10/GB/month. |

**Cost:** a few cents a month. The state file is kilobytes; ECR storage is the only real
line, and the lifecycle policy is what keeps it small.

**There is no DynamoDB lock table.** Terraform 1.10 taught the S3 backend to lock on its
own and 1.11 deprecated the DynamoDB mechanism, so the table would be a resource to pay
for, permission and eventually forget to delete.

## Destroying

Don't. The budget is free, and an account without one is how a forgotten NAT gateway
bills for six months. If the account itself is being closed, `terraform destroy` works —
but the state bucket must be emptied by hand first, because versioned buckets refuse to
delete while objects remain.
