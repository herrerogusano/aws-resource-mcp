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
from aws_resource_mcp.aws.discovery import (
    deduplicate_resources,
    group_resources_by_service,
)
from aws_resource_mcp.aws.regions import enabled_region_names, list_aws_regions
from aws_resource_mcp.aws.resource_explorer_inventory import (
    discover_with_resource_explorer,
)
from aws_resource_mcp.aws.session import create_aws_session
from aws_resource_mcp.config import AWSConfig, DEFAULT_AWS_REGION
from aws_resource_mcp.models import InventoryError

def collect_general_aws_inventory(
    region: str | None = None,
    profile_name: str | None = None,
    *,
    session: Any | None = None,
    services: Collection[str] | None = None,
    resource_types: Collection[str] | None = None,
    query: str | None = None,
    all_regions: bool = True,
) -> dict[str, Any]:
    """Discover and normalize all supported services through Resource Explorer."""
    primary_region = region or DEFAULT_AWS_REGION
    try:
        aws_session = session or create_aws_session(primary_region, profile_name)
        account = get_aws_identity(aws_session)
    except Exception as error:
        raise AWSInventoryGlobalError(describe_aws_error("sts", error)) from None

    errors: list[InventoryError] = []
    coverage_limitations: list[str] = []
    try:
        region_records = list_aws_regions(aws_session, primary_region)
        enabled_regions = enabled_region_names(region_records)
    except Exception as error:
        errors.append(describe_aws_error("ec2", error))
        enabled_regions = [primary_region]
        coverage_limitations.append(
            "Enabled Regions could not be listed; only the primary Region was used."
        )

    scan_regions = (
        enabled_regions
        if all_regions and region is None
        else [primary_region]
    )
    requested_services = (
        None if services is None else sorted(set(services))
    )
    requested_types = (
        None if resource_types is None else sorted(set(resource_types))
    )

    explorer = discover_with_resource_explorer(
        aws_session,
        enabled_regions,
        primary_region=primary_region,
        services=requested_services,
        resource_types=requested_types,
        query=query,
        region_filter=(
            region
            if region is not None
            else (None if all_regions else primary_region)
        ),
    )
    errors.extend(explorer["errors"])
    explorer_coverage = explorer["coverage"]
    explorer_coverage["limitations"] = [
        *coverage_limitations,
        *explorer_coverage["limitations"],
    ]

    resources = deduplicate_resources(explorer["resources"])
    resources_by_service = group_resources_by_service(resources)
    coverage_status = "unavailable"
    if explorer_coverage["available"] and explorer_coverage["aggregator_index"]:
        coverage_status = "complete_for_supported_resources"
    elif explorer_coverage["available"]:
        coverage_status = "partial"
    if explorer_coverage["limitations"] or explorer_coverage["permission_errors"]:
        if coverage_status == "complete_for_supported_resources":
            coverage_status = "partial"

    return {
        "account": account,
        "region": primary_region,
        "services": resources_by_service,
        "resources": resources,
        "resources_by_service": resources_by_service,
        "coverage": {
            "status": coverage_status,
            "resource_explorer": explorer_coverage,
            "regions_enabled": enabled_regions,
            "regions_scanned": scan_regions,
        },
        "errors": errors,
    }


def collect_aws_inventory(
    region: str = DEFAULT_AWS_REGION,
    profile_name: str | None = None,
    *,
    session: Any | None = None,
    services: Collection[str] | None = None,
) -> dict[str, Any]:
    """Collect the same uniform inventory exposed by the MCP tool."""
    return collect_general_aws_inventory(
        region,
        profile_name,
        session=session,
        services=services,
        all_regions=False,
    )


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
