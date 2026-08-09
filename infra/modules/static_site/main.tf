# S3 + CloudFront + Origin Access Control, with an optional dynamic origin so one
# hostname serves both the static page and the API.
#
# One hostname is the point. Two — a CloudFront domain for assets and a Function URL for
# the API — means CORS, a preflight on every call, and two things to configure instead of
# one.

data "aws_caller_identity" "current" {}

locals {
  bucket_name = coalesce(var.bucket_name, "${var.name}-static-${data.aws_caller_identity.current.account_id}")
  has_api     = var.api_origin_domain != null

  s3_origin_id  = "s3-static"
  api_origin_id = "lambda-api"
}

# ---------------------------------------------------------------------------
# The bucket. Private: CloudFront reaches it through OAC, nobody else reaches it at all.
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "static" {
  bucket = local.bucket_name

  # These are deploy artifacts, rebuildable from the repository in seconds. Refusing to
  # destroy them would mean an environment that cannot be torn down cleanly, which costs
  # more than the files are worth.
  force_destroy = true

  tags = var.tags
}

resource "aws_s3_bucket_public_access_block" "static" {
  bucket = aws_s3_bucket.static.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "static" {
  bucket = aws_s3_bucket.static.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# OAC replaces the old Origin Access Identity. CloudFront signs each request to S3 with
# SigV4, so the bucket can stay entirely private — no public objects, no bucket-level
# website hosting, no way to reach the files except through the distribution.
resource "aws_cloudfront_origin_access_control" "static" {
  name                              = "${var.name}-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "aws_iam_policy_document" "bucket_policy" {
  statement {
    sid       = "AllowCloudFrontRead"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.static.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    # Scoped to this distribution, so another account's distribution cannot read it.
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.this.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "static" {
  bucket = aws_s3_bucket.static.id
  policy = data.aws_iam_policy_document.bucket_policy.json

  depends_on = [aws_s3_bucket_public_access_block.static]
}

# ---------------------------------------------------------------------------
# Managed policies, looked up by name rather than pasted as UUIDs.
# ---------------------------------------------------------------------------

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}

# Forwards everything the viewer sent except Host — the origin has to see its own host to
# route correctly, and a Lambda Function URL rejects requests carrying someone else's.
data "aws_cloudfront_origin_request_policy" "all_viewer_except_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

# ---------------------------------------------------------------------------
# The distribution.
# ---------------------------------------------------------------------------

resource "aws_cloudfront_distribution" "this" {
  enabled             = true
  comment             = var.name
  default_root_object = var.default_root_object
  price_class         = var.price_class
  is_ipv6_enabled     = true

  origin {
    origin_id                = local.s3_origin_id
    domain_name              = aws_s3_bucket.static.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.static.id
  }

  dynamic "origin" {
    for_each = local.has_api ? [var.api_origin_domain] : []

    content {
      origin_id   = local.api_origin_id
      domain_name = origin.value

      custom_origin_config {
        http_port              = 80
        https_port             = 443
        origin_protocol_policy = "https-only"
        origin_ssl_protocols   = ["TLSv1.2"]
      }
    }
  }

  # Static files: cached hard, compressed. This is the cheap path — a cache hit never
  # touches S3 and never starts a Lambda.
  default_cache_behavior {
    target_origin_id       = local.s3_origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
  }

  dynamic "ordered_cache_behavior" {
    for_each = local.has_api ? var.api_path_patterns : []

    content {
      path_pattern           = ordered_cache_behavior.value
      target_origin_id       = local.api_origin_id
      viewer_protocol_policy = "redirect-to-https"
      allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
      cached_methods         = ["GET", "HEAD"]

      # compress = false is load-bearing, not an optimisation.
      #
      # CloudFront has to buffer a response to compress it, and buffering is exactly what
      # kills server-sent events: the stream arrives complete, at the end, in one piece.
      # It is the same silent failure as a missing AWS_LWA_INVOKE_MODE, one layer further
      # out, and it looks correct in every test that only checks the final body.
      compress = false

      cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
      origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = var.tags
}
