"""MCP presentation layer for the read-only AWS inventory."""

import re
from typing import Any

from aws_resource_mcp.activity.engine import attach_free_activity_summaries
from aws_resource_mcp.aws.errors import AWSInventoryGlobalError
from aws_resource_mcp.aws.inventory import collect_general_aws_inventory
from aws_resource_mcp.config import DEFAULT_AWS_REGION
from aws_resource_mcp.models import remove_sensitive_fields


def _error_response(
    region: str,
    error_type: str,
    message: str,
    *,
    service: str = "input",
) -> dict[str, Any]:
    return {
        "status": "error",
        "summary": {"region": region},
        "resources": {},
        "all_resources": [],
        "resources_by_service": {},
        "coverage": {"status": "unavailable"},
        "errors": [
            {"service": service, "type": error_type, "message": message}
        ],
    }


def _normalize_services(services: list[str] | None) -> list[str]:
    if services is None:
        return []
    if not services:
        raise ValueError("services must contain at least one supported service")
    if any(not isinstance(service, str) for service in services):
        raise ValueError("every service name must be a string")

    normalized = list(dict.fromkeys(service.strip().lower() for service in services))
    if any(not service for service in normalized):
        raise ValueError("service names must not be empty")
    if any(not re.fullmatch(r"[a-z0-9-]+", service) for service in normalized):
        raise ValueError("service names may contain only letters, numbers, and hyphens")
    return normalized


def _normalize_resource_types(resource_types: list[str] | None) -> list[str]:
    if resource_types is None:
        return []
    if not resource_types:
        raise ValueError("resource_types must contain at least one resource type")
    if any(not isinstance(resource_type, str) for resource_type in resource_types):
        raise ValueError("every resource type must be a string")
    normalized = list(
        dict.fromkeys(resource_type.strip() for resource_type in resource_types)
    )
    if any(
        not resource_type
        or not re.fullmatch(r"[A-Za-z0-9:_-]+", resource_type)
        for resource_type in normalized
    ):
        raise ValueError("resource types contain an invalid value")
    return normalized


def _remove_account_ids(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _remove_account_ids(item)
            for key, item in value.items()
            if key.lower() != "account_id"
        }
    if isinstance(value, list):
        return [_remove_account_ids(item) for item in value]
    return value


def listar_recursos_aws(
    region: str | None = None,
    services: list[str] | None = None,
    include_account_id: bool = True,
    resource_types: list[str] | None = None,
    query: str | None = None,
    all_regions: bool = True,
    include_details: bool = True,
    include_cost_indicators: bool = True,
    confirm_potentially_billable_operations: bool = False,
    include_activity_summary: bool = False,
) -> dict[str, Any]:
    """Discover AWS resources through locally available credentials, read-only.

    Uses Resource Explorer for uniform, multi-Region discovery. Every service is
    represented with the same resource model and discovery path. Filter by
    service, resource type, Region, or search text. Optional details and
    potential-cost indicators use the same model for every service. An optional
    activity summary uses only fields already returned by those service APIs;
    it does not run CloudTrail analysis or CloudWatch queries. Coverage
    depends on accessible Resource Explorer indexes, views, Regions, and IAM
    permissions, so the response always includes a coverage diagnosis and may be
    partial. Set ``include_account_id`` to false to anonymize the account. This
    tool never modifies resources and does not calculate costs or Free Tier.
    """
    if region is not None and not isinstance(region, str):
        return _error_response(
            "",
            "invalid_region",
            "region must be null or a non-empty AWS region name",
        )
    normalized_region = region.strip() if region is not None else None
    if region is not None and not normalized_region:
        return _error_response(
            "",
            "invalid_region",
            "region must be null or a non-empty AWS region name",
        )

    try:
        requested_services = _normalize_services(services)
        requested_types = _normalize_resource_types(resource_types)
    except (AttributeError, ValueError) as error:
        return _error_response(
            normalized_region or DEFAULT_AWS_REGION,
            "invalid_filters",
            str(error),
        )
    if query is not None and not isinstance(query, str):
        return _error_response(
            normalized_region or DEFAULT_AWS_REGION,
            "invalid_query",
            "query must be null or a string",
        )
    normalized_query = query.strip() if query and query.strip() else None
    if not isinstance(all_regions, bool):
        return _error_response(
            normalized_region or DEFAULT_AWS_REGION,
            "invalid_filters",
            "all_regions must be a boolean",
        )
    if (
        not isinstance(include_details, bool)
        or not isinstance(include_cost_indicators, bool)
        or not isinstance(confirm_potentially_billable_operations, bool)
        or not isinstance(include_activity_summary, bool)
    ):
        return _error_response(
            normalized_region or DEFAULT_AWS_REGION,
            "invalid_filters",
            "detail, cost, activity-summary, and confirmation flags must be booleans",
        )

    try:
        inventory = collect_general_aws_inventory(
            normalized_region,
            services=requested_services or None,
            resource_types=requested_types or None,
            query=normalized_query,
            all_regions=all_regions,
            include_details=include_details,
            include_cost_indicators=include_cost_indicators,
            confirm_potentially_billable_operations=(
                confirm_potentially_billable_operations
            ),
        )
    except AWSInventoryGlobalError as error:
        return _error_response(
            normalized_region or DEFAULT_AWS_REGION,
            error.error["error_type"],
            error.error["message"],
            service="aws",
        )
    except Exception:
        return _error_response(
            normalized_region or DEFAULT_AWS_REGION,
            "inventory_error",
            "The AWS inventory could not be collected. Check the local AWS configuration.",
            service="aws",
        )

    resources = inventory.get("services", {})
    all_resources = inventory.get("resources", [])
    resources_by_service = inventory.get("resources_by_service", {})
    if include_activity_summary:
        all_resources = attach_free_activity_summaries(all_resources)
        resources_by_service = {}
        for resource in all_resources:
            resources_by_service.setdefault(
                resource.get("service", "unknown"), []
            ).append(resource)
        resources = resources_by_service
    inventory_errors = [
        {
            "service": error.get("service", "aws"),
            "type": error.get("error_type", "aws_error"),
            "message": error.get("message", "An AWS query failed."),
        }
        for error in inventory.get("errors", [])
    ]
    summary: dict[str, Any] = {
        "region": inventory.get("region", normalized_region or DEFAULT_AWS_REGION),
        "total_resources": len(all_resources),
        "services_detected": len(resources_by_service),
        "regions_scanned": len(inventory.get("coverage", {}).get("regions_scanned", [])),
        "partial": bool(inventory_errors)
        or inventory.get("coverage", {}).get("status")
        != "complete_for_supported_resources",
    }
    adapter_coverage = inventory.get("coverage", {}).get("adapters", {})
    summary["adapters_executed"] = adapter_coverage.get("executed", [])
    summary["adapters_failed"] = adapter_coverage.get("failed", [])
    account_id = inventory.get("account", {}).get("account_id")
    if include_account_id and account_id:
        summary["account_id"] = account_id
    status = "partial" if summary["partial"] else "ok"
    response = remove_sensitive_fields(
        {
            "status": status,
            "summary": summary,
            "resources": resources,
            "all_resources": all_resources,
            "resources_by_service": resources_by_service,
            "coverage": inventory.get("coverage", {"status": "unavailable"}),
            "coverage_summary": {
                "status": inventory.get("coverage", {}).get(
                    "status", "unavailable"
                ),
                "diagnostic_tool_available": True,
                "full_diagnostic_executed": False,
            },
            "errors": inventory_errors,
        }
    )
    return response if include_account_id else _remove_account_ids(response)
