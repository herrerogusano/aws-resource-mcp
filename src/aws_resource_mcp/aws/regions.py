"""Read-only discovery of AWS Regions enabled for an account."""

from typing import Any

from aws_resource_mcp.aws.operations import OperationGuard
from aws_resource_mcp.config import DEFAULT_AWS_REGION

ENABLED_REGION_STATUSES = frozenset({"opt-in-not-required", "opted-in"})


def list_aws_regions(
    session: Any,
    endpoint_region: str = DEFAULT_AWS_REGION,
    operation_guard: OperationGuard | None = None,
) -> list[dict[str, Any]]:
    """Return all AWS Regions with normalized opt-in and enabled state."""
    client = session.client("ec2", region_name=endpoint_region)
    response = (operation_guard or OperationGuard()).call(
        client,
        service="ec2",
        operation="DescribeRegions",
        AllRegions=True,
    )
    regions = [
        {
            "name": item.get("RegionName"),
            "opt_in_status": item.get("OptInStatus"),
            "enabled": item.get("OptInStatus") in ENABLED_REGION_STATUSES,
        }
        for item in response.get("Regions", [])
        if item.get("RegionName")
    ]
    return sorted(regions, key=lambda item: item["name"])


def enabled_region_names(regions: list[dict[str, Any]]) -> list[str]:
    """Extract sorted enabled Region names from normalized Region records."""
    return sorted(item["name"] for item in regions if item.get("enabled"))
