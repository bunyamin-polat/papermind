# `lambda_container`

A container image running on Lambda behind a Function URL, with response streaming on.
The application inside is an ordinary HTTP server — the [AWS Lambda Web
Adapter](https://github.com/awslabs/aws-lambda-web-adapter) baked into the image does the
translating, so there is no Lambda-specific code in the app.

## Usage

```hcl
module "app" {
  source = "../../modules/lambda_container"

  function_name = "slipway-dev-app"
  image_uri     = "${data.aws_ecr_repository.app.repository_url}:${var.image_tag}"
  memory_size   = 1024
  timeout       = 30
}
```

## What it creates

| Resource | Notes |
| --- | --- |
| `aws_lambda_function` | `package_type = "Image"`, architecture must match the build |
| `aws_cloudwatch_log_group` | Created explicitly so retention is enforced |
| `aws_iam_role` + inline policy | Writes to this function's log group only |
| `aws_lambda_function_url` | Optional, with `invoke_mode` |
| `aws_lambda_permission` | Only when auth is `NONE`; without it the URL answers 403 |

## The three things that break this

**Architecture mismatch.** Lambda runs the image you give it and fails with
`Runtime.InvalidEntrypoint` — which says nothing about architecture — if it was built for
the wrong one. Build with `--platform linux/amd64` for the `x86_64` default.

**buildx attestations.** Docker 28 attaches provenance and SBOM metadata by default,
turning the push into a manifest index with an `unknown/unknown` entry. Lambda answers:

> The image manifest, config or layer media type for the source image … is not supported.

Build with `--provenance=false --sbom=false`. `scripts/deploy.py` does.

**Half-configured streaming.** Response streaming needs *both* `invoke_mode =
"RESPONSE_STREAM"` here and `AWS_LWA_INVOKE_MODE=response_stream` inside the image. With
either missing the response still arrives and still looks right — just all at once at the
end. Verify from the deployed URL, never locally.

## Cost shape

Lambda bills wall-clock time, not CPU. A streaming endpoint holds its invocation open for
the whole response, so an app that streams for 30 seconds is billed for 30 seconds even
while it waits on a model. Measured on the example app: a 1957 ms streaming request billed
1957 ms with the CPU essentially idle, against 2 ms for a warm non-streaming request.

That is the real reason to consider App Runner for anything interactive and long-running.
Lambda is excellent when requests are short or traffic is spiky enough that scale-to-zero
pays for itself.

## Inputs

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `function_name` | string | — | Names the function, its role and its log group |
| `image_uri` | string | — | Full ECR URI including tag |
| `architecture` | string | `"x86_64"` | Must match the build platform |
| `memory_size` | number | `1024` | CPU scales with this; it is a speed dial |
| `timeout` | number | `30` | Seconds; also a cost ceiling for streaming |
| `environment_variables` | map(string) | `{}` | Overrides what is baked into the image |
| `log_retention_days` | number | `14` | Lambda's own default is "never expire" |
| `create_function_url` | bool | `true` | Off when it sits behind API Gateway or CloudFront |
| `function_url_authorization` | string | `"NONE"` | `NONE` or `AWS_IAM` |
| `invoke_mode` | string | `"RESPONSE_STREAM"` | Half of what streaming needs |
| `cors` | object | `null` | Not needed when one origin serves page and API |
| `additional_policy_arns` | list(string) | `[]` | Extra permissions for the execution role |
| `tags` | map(string) | `{}` | On top of provider `default_tags` |

## Outputs

`function_name`, `function_arn`, `function_url`, `role_arn`, `role_name`,
`log_group_name`.
