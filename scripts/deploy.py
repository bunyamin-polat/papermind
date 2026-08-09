#!/usr/bin/env python3
"""Build, push and apply — one command from a local repo to a live URL.

    uv run python scripts/deploy.py dev

`terraform apply` is never the whole story: there is a build, a push to a registry and
later a CDN invalidation, and that sequence has to be one command or it will eventually
be done wrong at 11pm.

The image is tagged with the git commit SHA, so what is running is always traceable to a
commit, and a rollback is applying an older tag rather than rebuilding.
"""

from __future__ import annotations

import argparse
import sys

from _common import (
    APP_STACK,
    LAMBDA_PLATFORM,
    Config,
    DeployError,
    aws_identity,
    backend_config,
    detail,
    ecr_login,
    fail,
    git_tag,
    invalidate,
    load_config,
    registry_url,
    run,
    select_workspace,
    step,
    sync_static,
    terraform,
    terraform_outputs,
    timed,
)


def build_and_push(config: Config, image: str) -> None:
    run(
        [
            "docker",
            "buildx",
            "build",
            "--platform",
            LAMBDA_PLATFORM,
            # Lambda runs x86_64; an image built natively on Apple Silicon dies there
            # with Runtime.InvalidEntrypoint, which mentions nothing about architecture.
            "--provenance=false",
            "--sbom=false",
            # Docker 28 attaches provenance and SBOM attestations by default, which makes
            # the push a manifest index containing an unknown/unknown entry. Lambda then
            # rejects the image: "media type ... is not supported". These two flags are
            # the entire fix, and the error never hints at them.
            "-f",
            str(config.dockerfile),
            "-t",
            image,
            "--push",
            str(config.context),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("environment", help="dev, test or prod")
    parser.add_argument(
        "--tag",
        help="Deploy an existing image tag instead of building. This is the rollback path.",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Skip terraform's confirmation prompt. For CI, not for prod at 11pm.",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Show what would change and stop. Builds nothing, pushes nothing, changes "
        "nothing. This is what the pull request workflow runs.",
    )
    args = parser.parse_args()

    try:
        config = load_config(args.environment)
        environment = config.environment
        backend = backend_config(APP_STACK)

        step("Checking AWS credentials")
        account_id, region = aws_identity()
        detail(f"account {account_id} · region {region} · environment {environment}")
        if region != config.region:
            detail(f"warning: slipway.yaml says {config.region}, your session says {region}")

        registry = registry_url(account_id, region)
        tag = args.tag or git_tag()
        image = f"{registry}/{config.repository}:{tag}"

        if args.plan:
            step(f"Planning {environment}")
            terraform(["init", "-input=false", f"-backend-config={backend}"], APP_STACK)
            select_workspace(environment, APP_STACK)
            terraform(
                ["plan", "-input=false", "-no-color", *config.terraform_vars(tag)],
                APP_STACK,
            )
            return 0

        if args.tag:
            step(f"Skipping build, deploying existing tag {tag}")
        else:
            step(f"Building and pushing {image}")
            if tag.endswith("-dirty"):
                detail("Working tree is dirty — this tag will not match any commit exactly.")
            ecr_login(region)
            with timed("build and push"):
                build_and_push(config, image)

        step("Applying Terraform")
        terraform(["init", "-input=false", f"-backend-config={backend}"], APP_STACK)
        select_workspace(environment, APP_STACK)

        apply_cmd = ["apply", "-input=false", *config.terraform_vars(tag)]
        if args.auto_approve:
            apply_cmd.append("-auto-approve")

        with timed("terraform apply"):
            terraform(apply_cmd, APP_STACK)

        outputs = terraform_outputs(APP_STACK)
        bucket = outputs.get("static_bucket")
        distribution_id = outputs.get("distribution_id")

        # Only when this environment has a CDN. Without one the container serves its own
        # static files and there is nothing to sync.
        if bucket:
            step(f"Syncing static files to {bucket}")
            count = sync_static(config.static_dir, str(bucket))
            detail(f"{count} file(s)")

            if distribution_id:
                invalidation = invalidate(str(distribution_id))
                detail(f"invalidation {invalidation} filed, not waited on")

        step("Deployed")
        detail(f"url    {outputs.get('url')}")
        detail(f"on     {outputs.get('compute_target')}")
        detail(f"image  {image}")
        detail(f"verify uv run python scripts/smoke.py {environment}")
        if outputs.get("log_group_name"):
            detail(f"logs   aws logs tail {outputs['log_group_name']} --follow")
        detail(f"remove uv run python scripts/destroy.py {environment}")

    except DeployError as exc:
        return fail(exc)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
