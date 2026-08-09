#!/usr/bin/env python3
"""Tear an environment down completely, with a confirmation you have to mean.

    uv run python scripts/destroy.py dev

This is not the afterthought half of deploy. Every environment you cannot confidently
destroy is a subscription you did not intend to buy, and the way you find out whether
destroy works is by running it — ideally the same day you built the thing.

Afterwards it checks AWS directly rather than trusting Terraform's word for it.
"""

from __future__ import annotations

import argparse
import sys

import boto3
from _common import (
    APP_STACK,
    DeployError,
    aws_identity,
    backend_config,
    detail,
    fail,
    load_config,
    select_workspace,
    step,
    terraform,
    terraform_outputs,
    timed,
)


def confirm(environment: str, name: str, target: str, has_cdn: bool) -> bool:
    """Make the user type the environment name. A y/n prompt is muscle memory; this is not."""
    print(f"\n\033[1mAbout to destroy the {environment} environment.\033[0m")
    print(f"  Compute ({target}) : {name}")
    print("  Its log group, IAM role and URL go with it.")
    if has_cdn:
        print("  CloudFront and the static bucket go too — expect this to take ~15 minutes,")
        print("  because a distribution must be disabled and propagated before it can be deleted.")
    print("  The ECR images and the state bucket are NOT touched.\n")

    answer = input(f"Type {environment!r} to confirm: ").strip()
    return answer == environment


def survivors(name: str, region: str, bucket: str | None) -> list[str]:
    """Ask AWS what is left, instead of believing the exit code.

    Checks both compute targets by name rather than trusting the state we just deleted —
    the point of this function is to distrust what Terraform said.
    """
    remaining: list[str] = []

    lambda_client = boto3.client("lambda", region_name=region)
    try:
        lambda_client.get_function(FunctionName=name)
        remaining.append(f"lambda function {name}")
    except lambda_client.exceptions.ResourceNotFoundException:
        pass

    apprunner = boto3.client("apprunner", region_name=region)
    for service in apprunner.list_services().get("ServiceSummaryList", []):
        # A deleted service lingers in the list as DELETED for a while; that is fine.
        if service["ServiceName"] == name and service["Status"] != "DELETED":
            remaining.append(f"app runner service {name} ({service['Status']})")

    logs = boto3.client("logs", region_name=region)
    groups = logs.describe_log_groups(logGroupNamePrefix=f"/aws/lambda/{name}")
    remaining += [f"log group {g['logGroupName']}" for g in groups.get("logGroups", [])]

    if bucket:
        s3 = boto3.client("s3")
        try:
            s3.head_bucket(Bucket=bucket)
            remaining.append(f"s3 bucket {bucket}")
        except s3.exceptions.ClientError:
            pass

    return remaining


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("environment", help="dev, test or prod")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt. For CI teardown only.",
    )
    args = parser.parse_args()

    try:
        config = load_config(args.environment)
        environment = config.environment
        backend = backend_config(APP_STACK)

        step("Checking AWS credentials")
        account_id, region = aws_identity()
        detail(f"account {account_id} · region {region} · environment {environment}")

        name = f"{config.resource_prefix}-app"

        # Read the state before destroying it, so the confirmation can say what is
        # actually there and the verification afterwards knows what to look for.
        terraform(["init", "-input=false", f"-backend-config={backend}"], APP_STACK)
        select_workspace(environment, APP_STACK)
        outputs = terraform_outputs(APP_STACK)
        bucket = outputs.get("static_bucket")
        has_cdn = bool(outputs.get("cdn_enabled"))
        target = str(outputs.get("compute_target") or "lambda")

        if not args.yes and not confirm(environment, name, target, has_cdn):
            print("Not confirmed. Nothing was destroyed.")
            return 1

        step("Destroying")

        with timed("terraform destroy"):
            # image_tag is irrelevant to a destroy, but Terraform still evaluates the
            # configuration, so it needs a value.
            terraform(
                ["destroy", "-input=false", "-auto-approve", *config.terraform_vars("latest")],
                APP_STACK,
            )

        step("Verifying against AWS")
        left = survivors(name, region, str(bucket) if bucket else None)
        if left:
            print("\n\033[31mStill present:\033[0m", file=sys.stderr)
            for item in left:
                print(f"  - {item}", file=sys.stderr)
            print(
                "\nDestroy reported success but AWS disagrees. Check the console.",
                file=sys.stderr,
            )
            return 1

        detail("nothing left: no function, no service, no log group")
        detail("ECR images remain, subject to the lifecycle policy that keeps the last 10")
        detail("the budget alarm and the state bucket are account-level and stay")

    except DeployError as exc:
        return fail(exc)
    except KeyboardInterrupt:
        print(
            "\nInterrupted. The environment may be half-destroyed — run this again.",
            file=sys.stderr,
        )
        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
