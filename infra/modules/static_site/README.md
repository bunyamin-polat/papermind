# `static_site`

A private S3 bucket behind CloudFront, optionally with a second origin so one hostname
serves both the static files and the API.

One hostname is the point. Splitting them — CloudFront for assets, a Function URL for the
API — means CORS, a preflight on every call, and two things to configure instead of one.

## Usage

```hcl
module "site" {
  source = "../../modules/static_site"

  name              = "slipway-dev"
  api_origin_domain = replace(replace(module.app.function_url, "https://", ""), "/", "")
}
```

## What it creates

| Resource | Notes |
| --- | --- |
| `aws_s3_bucket` | Private, encrypted, `force_destroy = true` |
| `aws_s3_bucket_public_access_block` | All four blocks on |
| `aws_cloudfront_origin_access_control` | SigV4; replaces the deprecated OAI |
| `aws_s3_bucket_policy` | Read access for this distribution only, via `AWS:SourceArn` |
| `aws_cloudfront_distribution` | Static default behaviour, plus one behaviour per API path |

## `compress = false` on the API behaviour is not an optimisation

CloudFront buffers a response in order to compress it, and buffering is what kills
server-sent events. The stream arrives complete, at the end, in one piece — the same
silent failure as a missing `AWS_LWA_INVOKE_MODE`, one layer further out, and invisible to
any test that only checks the final body.

Streaming therefore needs three things aligned, and any one of them alone will look fine:

1. `AWS_LWA_INVOKE_MODE=response_stream` in the image
2. `invoke_mode = "RESPONSE_STREAM"` on the Function URL
3. `compress = false` on the CloudFront behaviour that carries it

## Slow by nature

Creating the distribution takes 5–15 minutes, and changing its configuration takes
another 5–10. **Deploying content does not**: a deploy syncs S3 and files an invalidation,
which is seconds, because it never touches the distribution itself.

Destroying is the expensive one — CloudFront must be disabled and propagated before it can
be deleted, so a teardown that used to take 22 seconds takes about 15 minutes. That is why
`enable_cdn` is per environment: `dev` runs without it for a fast build-destroy loop, and
turns it on when the CDN path itself is what is being tested.

## Inputs

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `name` | string | — | Names the bucket and the OAC |
| `bucket_name` | string | `null` | Defaults to `<name>-static-<account-id>` |
| `api_origin_domain` | string | `null` | Function URL host; null means static only |
| `api_path_patterns` | list(string) | `["/api/*", "/healthz"]` | Routed to the API origin |
| `default_root_object` | string | `"index.html"` | Served for `/` |
| `price_class` | string | `"PriceClass_100"` | NA + Europe, the cheapest |
| `tags` | map(string) | `{}` | On top of provider `default_tags` |

## Outputs

`bucket_name`, `distribution_id`, `domain_name`, `url`.
