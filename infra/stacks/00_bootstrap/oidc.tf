# GitHub Actions → AWS without a single long-lived credential.
#
# GitHub mints a short-lived OIDC token for each workflow run; AWS trusts the issuer and
# exchanges it for temporary credentials. Nothing durable is stored in the repository, so
# there is nothing in it to leak. AWS_SECRET_ACCESS_KEY in repo secrets is the most common
# way portfolio projects lose their account, and this is the reason it never appears here.

# The provider is an account-level singleton: AWS permits exactly one for
# token.actions.githubusercontent.com. Slipway created it, and this repository is the
# second project in the same account — so it is adopted rather than declared.
#
# This is the first thing the blueprint did not survive being copied twice. Everything
# else in `00_bootstrap` is per-project (a budget, a bucket, a registry) and duplicates
# happily; this one resource is shared by construction, and vendoring it as a `resource`
# means the second adopter's first `apply` fails with EntityAlreadyExists.
#
# Set `create_oidc_provider = true` on a fresh account where nothing has created it yet.
resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 1 : 0

  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = var.github_oidc_thumbprints
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 0 : 1

  url = "https://token.actions.githubusercontent.com"
}

locals {
  github_oidc_provider_arn = (
    var.create_oidc_provider
    ? aws_iam_openid_connect_provider.github[0].arn
    : data.aws_iam_openid_connect_provider.github[0].arn
  )
}

locals {
  github_owner = split("/", var.github_repository)[0]
  github_repo  = split("/", var.github_repository)[1]

  # GitHub issues subject claims in two shapes, and which one you get is not something
  # the workflow controls:
  #
  #   repo:owner/repo:environment:dev
  #   repo:owner@78386903/repo@1323385694:environment:dev
  #
  # The second carries immutable numeric IDs so a token keeps meaning the same repository
  # after a rename. Almost no example policy shows it, and the failure it causes is a bare
  # "Not authorized to perform sts:AssumeRoleWithWebIdentity" that names nothing.
  #
  # The `@*` wildcards stay safe: GitHub logins and repository names cannot contain "@",
  # so nothing but this repository can match either pattern.
  github_subject_prefixes = [
    "repo:${var.github_repository}",
    "repo:${local.github_owner}@*/${local.github_repo}@*",
  ]

  # The triggers allowed to assume the role: the default branch, pull requests, and named
  # environments. A workflow on a fork's branch matches none of them.
  github_subjects = flatten([
    for prefix in local.github_subject_prefixes : [
      "${prefix}:ref:refs/heads/main",
      "${prefix}:pull_request",
      "${prefix}:environment:*",
    ]
  ])
}

data "aws_iam_policy_document" "github_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }

    # Without this the role would trust every GitHub repository in existence.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # And this pins it to one repository and to specific triggers within it — see the
    # locals above for why there are two spellings of the same repository.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = local.github_subjects
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "${var.project}-github-actions"
  description        = "Assumed by GitHub Actions via OIDC to plan, deploy and destroy ${var.project}"
  assume_role_policy = data.aws_iam_policy_document.github_assume_role.json

  # A workflow run is minutes, not hours. Shorter than the default hour, long enough for a
  # CloudFront apply.
  max_session_duration = 3600
}

# Scoped by hand rather than reaching for PowerUserAccess. It is more work, and it is the
# difference between a leaked token being an inconvenience and being an incident.
data "aws_iam_policy_document" "github_actions" {
  # Terraform state.
  statement {
    sid    = "TerraformState"
    effect = "Allow"

    actions = [
      "s3:ListBucket",
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]

    resources = [
      aws_s3_bucket.state.arn,
      "${aws_s3_bucket.state.arn}/*",
    ]
  }

  # The registry. GetAuthorizationToken cannot be scoped to a repository — it is the call
  # that hands out the login token, and AWS defines it account-wide.
  statement {
    sid       = "EcrLogin"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "EcrPushPull"
    effect = "Allow"

    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeImages",
      "ecr:DescribeRepositories",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      # Reading the repository reads its tags too — data.aws_ecr_repository fails
      # without this, before a single byte is pushed.
      "ecr:ListTagsForResource",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]

    resources = [aws_ecr_repository.app.arn]
  }

  statement {
    sid    = "Lambda"
    effect = "Allow"

    actions = [
      "lambda:AddPermission",
      "lambda:CreateFunction",
      "lambda:CreateFunctionUrlConfig",
      "lambda:DeleteFunction",
      "lambda:DeleteFunctionUrlConfig",
      "lambda:GetFunction",
      "lambda:GetFunctionCodeSigningConfig",
      "lambda:GetFunctionConfiguration",
      "lambda:GetFunctionUrlConfig",
      "lambda:GetPolicy",
      # Reading a function reads its tags, the same trap as the ECR repository above.
      "lambda:ListTags",
      "lambda:ListVersionsByFunction",
      "lambda:RemovePermission",
      "lambda:TagResource",
      "lambda:UntagResource",
      "lambda:UpdateFunctionCode",
      "lambda:UpdateFunctionConfiguration",
      "lambda:UpdateFunctionUrlConfig",
    ]

    resources = ["arn:aws:lambda:*:${data.aws_caller_identity.current.account_id}:function:${var.project}-*"]
  }

  # DescribeLogGroups is a list operation: it asks the account, not a group, so AWS
  # evaluates it against an empty resource (`log-group::log-stream:` in the denial
  # message) and a prefix-scoped ARN never matches. It has to be granted broadly. It is
  # read-only, and every call that *changes* a log group stays scoped below.
  statement {
    sid       = "LogsDiscovery"
    effect    = "Allow"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["arn:aws:logs:*:${data.aws_caller_identity.current.account_id}:log-group:*"]
  }

  statement {
    sid    = "LogsManage"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:DeleteLogGroup",
      "logs:ListTagsForResource",
      "logs:PutRetentionPolicy",
      "logs:TagResource",
      "logs:UntagResource",
    ]

    resources = ["arn:aws:logs:*:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project}-*"]
  }

  # Roles the deploy creates for the functions. Narrowed by name prefix so this role
  # cannot mint itself a more powerful one.
  statement {
    sid    = "IamForLambdaRoles"
    effect = "Allow"

    actions = [
      "iam:AttachRolePolicy",
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:DeleteRolePolicy",
      "iam:DetachRolePolicy",
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
      "iam:ListRolePolicies",
      "iam:PassRole",
      "iam:PutRolePolicy",
      "iam:TagRole",
      "iam:UntagRole",
    ]

    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.project}-*"]
  }

  # Static site buckets, by name prefix.
  statement {
    sid    = "StaticSiteBuckets"
    effect = "Allow"

    actions = ["s3:*"]

    resources = [
      "arn:aws:s3:::${var.project}-*-static-*",
      "arn:aws:s3:::${var.project}-*-static-*/*",
    ]
  }

  # CloudFront's create and list calls are not resource-scopable — there is no ARN yet at
  # creation time, and the distribution list is account-wide by design.
  statement {
    sid    = "CloudFront"
    effect = "Allow"

    actions = [
      "cloudfront:CreateDistribution",
      "cloudfront:CreateInvalidation",
      "cloudfront:CreateOriginAccessControl",
      "cloudfront:DeleteDistribution",
      "cloudfront:DeleteOriginAccessControl",
      "cloudfront:GetCachePolicy",
      "cloudfront:GetDistribution",
      "cloudfront:GetInvalidation",
      "cloudfront:GetOriginAccessControl",
      "cloudfront:GetOriginRequestPolicy",
      "cloudfront:ListCachePolicies",
      "cloudfront:ListDistributions",
      "cloudfront:ListOriginRequestPolicies",
      "cloudfront:ListTagsForResource",
      "cloudfront:TagResource",
      "cloudfront:UntagResource",
      "cloudfront:UpdateDistribution",
    ]

    resources = ["*"]
  }

  # Alarms and the dashboard. Alarm ARNs are scoped by name; dashboards and the
  # Describe/List calls are not resource-scopable.
  statement {
    sid    = "CloudWatchAlarms"
    effect = "Allow"

    actions = [
      "cloudwatch:DeleteAlarms",
      "cloudwatch:ListTagsForResource",
      "cloudwatch:PutMetricAlarm",
      "cloudwatch:TagResource",
      "cloudwatch:UntagResource",
    ]

    resources = ["arn:aws:cloudwatch:*:${data.aws_caller_identity.current.account_id}:alarm:${var.project}-*"]
  }

  statement {
    sid    = "CloudWatchDashboardsAndReads"
    effect = "Allow"

    actions = [
      "cloudwatch:DeleteDashboards",
      "cloudwatch:DescribeAlarms",
      "cloudwatch:GetDashboard",
      "cloudwatch:ListDashboards",
      "cloudwatch:PutDashboard",
    ]

    resources = ["*"]
  }

  # The alarm topic. Same lesson as ECR and Lambda: reading it reads its tags, and its
  # attributes and subscriptions are separate calls again.
  statement {
    sid    = "SnsAlertTopic"
    effect = "Allow"

    actions = [
      "sns:CreateTopic",
      "sns:DeleteTopic",
      "sns:GetTopicAttributes",
      "sns:ListSubscriptionsByTopic",
      "sns:ListTagsForResource",
      "sns:SetTopicAttributes",
      "sns:Subscribe",
      "sns:TagResource",
      "sns:UntagResource",
      "sns:Unsubscribe",
    ]

    resources = ["arn:aws:sns:*:${data.aws_caller_identity.current.account_id}:${var.project}-*"]
  }

  # App Runner, for environments that pick it as their compute target. Creation and the
  # list calls carry no resource ARN, so they cannot be scoped.
  statement {
    sid    = "AppRunner"
    effect = "Allow"

    actions = [
      "apprunner:CreateAutoScalingConfiguration",
      "apprunner:CreateService",
      "apprunner:DeleteAutoScalingConfiguration",
      "apprunner:DeleteService",
      "apprunner:DescribeAutoScalingConfiguration",
      "apprunner:DescribeService",
      "apprunner:ListServices",
      "apprunner:ListTagsForResource",
      "apprunner:TagResource",
      "apprunner:UntagResource",
      "apprunner:UpdateService",
    ]

    resources = ["*"]
  }

  # App Runner needs its own service-linked role the first time it runs in an account.
  statement {
    sid       = "AppRunnerServiceLinkedRole"
    effect    = "Allow"
    actions   = ["iam:CreateServiceLinkedRole"]
    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/aws-service-role/apprunner.amazonaws.com/*"]
  }

  # Read-only calls Terraform makes on every plan.
  statement {
    sid    = "ReadOnlyLookups"
    effect = "Allow"

    actions = [
      "sts:GetCallerIdentity",
      "ecr:GetRepositoryPolicy",
      "iam:GetOpenIDConnectProvider",
    ]

    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_actions" {
  name   = "deploy"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions.json
}
