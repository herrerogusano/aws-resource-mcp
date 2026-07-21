"""Aggregate read-only AWS inventory and local diagnostic command."""

import argparse
import json
from collections.abc import Collection
from typing import Any

from aws_resource_mcp.aws.errors import (
    AWSInventoryGlobalError,
    describe_aws_error,
)
from aws_resource_mcp.aws.identity import get_aws_identity
from aws_resource_mcp.aws.lambda_inventory import list_lambda_functions
from aws_resource_mcp.aws.s3_inventory import list_s3_buckets
from aws_resource_mcp.aws.session import create_aws_session
from aws_resource_mcp.config import AWSConfig, DEFAULT_AWS_REGION
from aws_resource_mcp.models import InventoryError

SUPPORTED_INVENTORY_SERVICES = frozenset({"lambda", "s3"})


def collect_aws_inventory(
    region: str = DEFAULT_AWS_REGION,
    profile_name: str | None = None,
    *,
    session: Any | None = None,
    services: Collection[str] | None = None,
) -> dict[str, Any]:
    """Collect identity, Lambda and S3 data into a JSON-compatible inventory."""
    requested_services = (
        SUPPORTED_INVENTORY_SERVICES if services is None else frozenset(services)
    )
    unknown_services = requested_services - SUPPORTED_INVENTORY_SERVICES
    if unknown_services:
        unknown = ", ".join(sorted(unknown_services))
        raise ValueError(f"Unsupported inventory services: {unknown}")

    try:
        aws_session = session or create_aws_session(region, profile_name)
        account = get_aws_identity(aws_session)
    except Exception as error:
        raise AWSInventoryGlobalError(describe_aws_error("sts", error)) from None

    errors: list[InventoryError] = []
    service_results: dict[str, list[dict[str, Any]]] = {
        service: [] for service in sorted(requested_services)
    }

    if "lambda" in requested_services:
        try:
            service_results["lambda"] = list_lambda_functions(aws_session, region)
        except Exception as error:
            errors.append(describe_aws_error("lambda", error))

    if "s3" in requested_services:
        try:
            service_results["s3"], s3_errors = list_s3_buckets(aws_session)
            errors.extend(s3_errors)
        except Exception as error:
            errors.append(describe_aws_error("s3", error))

    return {
        "account": account,
        "region": region,
        "services": service_results,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    """Run a real inventory query and print readable JSON for diagnostics."""
    parser = argparse.ArgumentParser(description="Collect a read-only AWS inventory.")
    parser.add_argument("--region", help="AWS region (default: eu-west-1).")
    parser.add_argument("--profile", help="Optional AWS shared-configuration profile.")
    arguments = parser.parse_args(argv)
    config = AWSConfig.from_sources(
        region=arguments.region,
        profile_name=arguments.profile,
    )

    try:
        inventory = collect_aws_inventory(config.region, config.profile_name)
    except AWSInventoryGlobalError as error:
        print(json.dumps({"error": error.error}, indent=2))
        return 1

    print(json.dumps(inventory, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
