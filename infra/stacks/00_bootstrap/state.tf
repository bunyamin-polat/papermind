# Remote state bucket.
#
# Every other stack keeps its state here. This one cannot — it is the stack that
# creates the bucket — so it runs on local state until the bucket exists, then moves
# with `terraform init -backend-config=backend.hcl -migrate-state`.
#
# There is no DynamoDB lock table: since Terraform 1.10 the S3 backend locks natively
# with `use_lockfile = true`, and 1.11 deprecated the DynamoDB mechanism.

locals {
  # Bucket names are globally unique across all of AWS, so the account ID is appended.
  # It is not a secret, but it is not published either — it stays out of git via
  # backend.hcl and terraform.tfvars.
  state_bucket_name = coalesce(
    var.state_bucket_name,
    "${var.project}-tfstate-${data.aws_caller_identity.current.account_id}"
  )
}

resource "aws_s3_bucket" "state" {
  bucket = local.state_bucket_name

  # Losing this bucket means losing the record of everything Terraform has created,
  # after which recovery is manual and miserable. Deleting it has to be a deliberate
  # act: remove this block first.
  lifecycle {
    prevent_destroy = true
  }
}

# Versioning is the recovery path. A corrupted or truncated state file is restored by
# rolling back to the previous object version.
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

# SSE-S3, not SSE-KMS. A customer managed key costs $1/month plus per-request charges
# and buys nothing here; state is still encrypted at rest either way.
resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }

    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Old state versions accumulate forever otherwise. Ninety days is far longer than any
# rollback you will realistically perform, and keeps the bucket free in practice.
resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  # Versioning must be on before lifecycle rules that reference noncurrent versions.
  depends_on = [aws_s3_bucket_versioning.state]

  rule {
    id     = "expire-noncurrent-state-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = var.state_noncurrent_version_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# Refuse plain HTTP. State files contain resource identifiers and sometimes secrets;
# they have no business travelling unencrypted.
resource "aws_s3_bucket_policy" "state_tls_only" {
  bucket = aws_s3_bucket.state.id
  policy = data.aws_iam_policy_document.state_tls_only.json

  depends_on = [aws_s3_bucket_public_access_block.state]
}

data "aws_iam_policy_document" "state_tls_only" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = ["s3:*"]

    resources = [
      aws_s3_bucket.state.arn,
      "${aws_s3_bucket.state.arn}/*",
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}
