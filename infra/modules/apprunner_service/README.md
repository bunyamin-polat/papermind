# `apprunner_service`

The always-warm alternative to [`lambda_container`](../lambda_container/), running the
**identical image**. The Lambda Web Adapter baked into that image simply never activates
outside Lambda, so what App Runner starts is an ordinary uvicorn process.

## The trade, stated plainly

| | `lambda_container` | `apprunner_service` |
| --- | --- | --- |
| Idle cost | $0 | Provisioned memory, billed around the clock |
| Cold start | 2.2–3.5 s measured on this app | None after the first deploy |
| Billing | Per invocation-millisecond, including time spent waiting | Memory continuously, CPU while serving |
| Scale to zero | Yes | No — the floor is one instance |
| Streaming | Needs invoke mode set in two places | Ordinary HTTP, nothing to configure |

Pick per project, not per portfolio. Lambda wins for spiky or occasional traffic. App
Runner wins for anything interactive where a user waits — and for anything that streams
for a long time, because Lambda bills wall-clock and a 30-second answer is 30 seconds of
Lambda.

## Usage

```hcl
module "service" {
  source = "../../modules/apprunner_service"

  service_name = "slipway-dev-app"
  image_uri    = "${data.aws_ecr_repository.app.repository_url}:${var.image_tag}"
}
```

## Things that are easy to get wrong

**The access role principal.** App Runner pulls from a private ECR repository as itself.
That role trusts `build.apprunner.amazonaws.com` — *not* `tasks.apprunner.amazonaws.com`,
which is the instance role governing what the running code may do. Using the wrong one
fails at pull time with a message about repository access that never mentions roles.

**`auto_deployments_enabled` is off here.** App Runner can watch the tag and redeploy
whenever the image is overwritten. That sounds convenient and is a deploy nobody approved,
nobody reviewed and nobody can find afterwards. Deploys belong to `deploy.py` and the
pipeline.

**`max_size` defaults to 25 in AWS.** This module sets 2. A retry loop against the default
is a large bill arriving quietly.

**Creation is slow.** Expect several minutes for the first deploy and a couple more for
each image change, against seconds for Lambda.

## Inputs

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `service_name` | string | — | Names the service and its access role |
| `image_uri` | string | — | Full ECR URI including tag |
| `port` | string | `"8080"` | Must match what the image serves |
| `cpu` | string | `"0.25 vCPU"` | Ceiling on single-request speed |
| `memory` | string | `"0.5 GB"` | Billed continuously |
| `environment_variables` | map(string) | `{}` | Passed to the container |
| `health_check_path` | string | `"/healthz"` | Polled to decide readiness |
| `min_size` | number | `1` | Cannot be zero |
| `max_size` | number | `2` | A deliberate cost ceiling |
| `max_concurrency` | number | `100` | Requests per instance before scaling out |
| `auto_deployments_enabled` | bool | `false` | Leave off; deploys belong to the pipeline |
| `tags` | map(string) | `{}` | On top of provider `default_tags` |

## Outputs

`service_url`, `service_arn`, `service_id`, `status`.
