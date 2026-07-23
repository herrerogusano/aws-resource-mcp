"""Aggregate read-only AWS inventory and local diagnostic command."""

import argparse
import json
from collections.abc import Collection
from time import monotonic
from typing import Any

from aws_resource_mcp.aws.adapter_engine import execute_adapters
from aws_resource_mcp.aws.consent import (
    ConsentRecord,
    ConsentValidationError,
    identity_fingerprint,
)
from aws_resource_mcp.aws.discovery import (
    deduplicate_resources,
    group_resources_by_service,
)
from aws_resource_mcp.aws.errors import (
    AWSInventoryGlobalError,
    describe_aws_error,
)
from aws_resource_mcp.aws.identity import get_aws_identity
from aws_resource_mcp.aws.regions import enabled_region_names, list_aws_regions
from aws_resource_mcp.aws.resource_explorer_inventory import (
    discover_with_resource_explorer,
)
from aws_resource_mcp.aws.session import create_aws_session
from aws_resource_mcp.aws.operations import (
    OperationGuard,
    OperationTimeoutError,
    ScopedOperationAuthorization,
)
from aws_resource_mcp.config import AWSConfig, DEFAULT_AWS_REGION
from aws_resource_mcp.models import InventoryError


def _matches_resource_type(resource: dict[str, Any], allowed: set[str]) -> bool:
    resource_type = str(resource.get("resource_type") or "")
    candidates = {resource_type.lower()}
    if resource_type.startswith("AWS::"):
        _, service, kind = resource_type.split("::", 2)
        candidates.add(f"{service}:{kind}".lower())
    return bool(candidates & allowed)


def collect_general_aws_inventory(
    region: str | None = None,
    profile_name: str | None = None,
    *,
    session: Any | None = None,
    services: Collection[str] | None = None,
    resource_types: Collection[str] | None = None,
    query: str | None = None,
    all_regions: bool = True,
    include_details: bool = True,
    include_cost_indicators: bool = True,
    cost_mode: str | None = None,
    confirm_potentially_billable_operations: bool = False,
    include_global_resource_explorer_results: bool = False,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Run general discovery and every selected adapter through one pipeline."""
    primary_region = region or DEFAULT_AWS_REGION
    config = AWSConfig.from_sources(
        region=primary_region,
        profile_name=profile_name,
        cost_mode=cost_mode,
    )
    del confirm_potentially_billable_operations
    deadline = monotonic() + timeout_seconds
    operation_guard = OperationGuard(config.cost_mode, deadline=deadline)
    try:
        aws_session = session or create_aws_session(config.region, config.profile_name)
        account = get_aws_identity(aws_session, operation_guard)
    except Exception as error:
        raise AWSInventoryGlobalError(describe_aws_error("sts", error)) from None

    errors: list[InventoryError] = []
    coverage_limitations: list[str] = []
    try:
        region_records = list_aws_regions(aws_session, primary_region, operation_guard)
        enabled_regions = enabled_region_names(region_records)
    except Exception as error:
        errors.append(describe_aws_error("ec2", error))
        enabled_regions = [primary_region]
        coverage_limitations.append(
            "Enabled Regions could not be listed; only the primary Region was used."
        )

    scan_regions = (
        enabled_regions if all_regions and region is None else [primary_region]
    )
    requested_services = None if services is None else sorted(set(services))
    requested_types = None if resource_types is None else sorted(set(resource_types))

    adapter_result = execute_adapters(
        aws_session,
        account_id=account.get("account_id"),
        regions=scan_regions,
        primary_region=primary_region,
        discovered_resources=[],
        services=requested_services,
        include_details=include_details,
        include_cost_indicators=include_cost_indicators,
        operation_guard=operation_guard,
    )
    errors.extend(adapter_result["errors"])
    try:
        explorer = discover_with_resource_explorer(
            aws_session,
            enabled_regions,
            primary_region=primary_region,
            services=requested_services,
            resource_types=requested_types,
            query=query,
            region_filter=(
                None
                if include_global_resource_explorer_results
                else region
                if region is not None
                else (None if all_regions else primary_region)
            ),
            operation_guard=operation_guard,
        )
    except OperationTimeoutError:
        explorer = {
            "resources": [],
            "coverage": {
                "available": False,
                "aggregator_index": False,
                "regions_indexed": [],
                "supported_resource_type_count": 0,
                "services_recognized": [],
                "permission_errors": [],
                "limitations": [
                    "Resource Explorer was skipped because the inventory time budget expired."
                ],
            },
            "errors": [],
        }
    errors.extend(explorer["errors"])
    explorer_coverage = explorer["coverage"]
    explorer_coverage["limitations"] = [
        *coverage_limitations,
        *explorer_coverage["limitations"],
    ]
    resources = deduplicate_resources(
        explorer["resources"], adapter_result["resources"]
    )
    if resource_types is not None:
        allowed_types = {item.lower() for item in resource_types}
        resources = [
            resource
            for resource in resources
            if _matches_resource_type(resource, allowed_types)
        ]
    if query and query.strip():
        search_text = query.strip().lower()
        resources = [
            resource
            for resource in resources
            if search_text in str(resource.get("name") or "").lower()
            or search_text in str(resource.get("id") or "").lower()
            or search_text in str(resource.get("arn") or "").lower()
        ]
    if not include_details:
        for resource in resources:
            resource["details"] = {}
    if not include_cost_indicators:
        for resource in resources:
            resource["cost_indicators"] = []
    resources_by_service = group_resources_by_service(resources)
    coverage_status = "unavailable"
    if explorer_coverage["available"] and explorer_coverage["aggregator_index"]:
        coverage_status = "complete_for_supported_resources"
    elif explorer_coverage["available"]:
        coverage_status = "partial"
    if explorer_coverage["limitations"] or explorer_coverage["permission_errors"]:
        if coverage_status == "complete_for_supported_resources":
            coverage_status = "partial"
    adapter_coverage = adapter_result["coverage"]
    if adapter_coverage["failed"]:
        coverage_status = "partial"
    if not explorer_coverage["available"] and adapter_coverage["executed"]:
        coverage_status = "partial"
        explorer_coverage["limitations"].append(
            "General discovery was unavailable; all selected discovery-capable adapters were used as a uniform fallback."
        )

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
            "adapters": adapter_coverage,
            "cost_mode": config.cost_mode,
            "timeout_seconds": timeout_seconds,
        },
        "errors": errors,
    }


def complete_inventory_with_consent(
    record: ConsentRecord,
    approved_services: Collection[str],
    *,
    session: Any | None = None,
    timeout_seconds: float = 30.0,
) -> tuple[dict[str, Any], ScopedOperationAuthorization]:
    """Resume only approved pending adapters under a single-use request budget."""
    scope = record.scope
    primary_region = str(scope["primary_region"])
    config = AWSConfig.from_sources(region=primary_region)
    deadline = monotonic() + timeout_seconds
    identity_guard = OperationGuard(config.cost_mode, deadline=deadline)
    aws_session = session or create_aws_session(config.region, config.profile_name)
    identity = get_aws_identity(aws_session, identity_guard)
    if identity_fingerprint(identity) != record.identity_hash:
        raise ConsentValidationError(
            "consent_identity_mismatch",
            "The current AWS identity does not match the consent request.",
        )

    selected_pending = [
        item
        for item in record.pending_operations
        if item["adapter"] in set(approved_services)
    ]
    allowed_operations = frozenset(
        (item["service"], item["operation"]) for item in selected_pending
    )
    allowed_regions = frozenset(
        {region for item in selected_pending for region in item.get("regions", [])}
    )
    authorization = ScopedOperationAuthorization(
        allowed_operations=allowed_operations,
        allowed_regions=allowed_regions,
        max_requests=sum(item["estimated_max_requests"] for item in selected_pending),
        max_additional_pages=0,
    )
    guard = OperationGuard(
        config.cost_mode,
        scoped_authorization=authorization,
        deadline=deadline,
    )
    skip_discovery_services = {
        adapter_name
        for adapter_name in approved_services
        if {
            item["stage"]
            for item in selected_pending
            if item["adapter"] == adapter_name
        }
        == {"enrichment"}
    }
    provisional = record.provisional_inventory
    adapter_result = execute_adapters(
        aws_session,
        account_id=identity.get("account_id"),
        regions=list(scope["regions_scanned"]),
        primary_region=primary_region,
        discovered_resources=list(provisional.get("resources", [])),
        services=approved_services,
        include_details=bool(scope["include_details"]),
        include_cost_indicators=bool(scope["include_cost_indicators"]),
        operation_guard=guard,
        resume_tokens=record.continuation_tokens,
        skip_discovery_services=skip_discovery_services,
    )
    resources = deduplicate_resources(
        list(provisional.get("resources", [])),
        adapter_result["resources"],
    )
    if scope.get("include_account_id") and identity.get("account_id"):
        for resource in resources:
            resource["account_id"] = identity["account_id"]
    resources_by_service = group_resources_by_service(resources)
    coverage = dict(provisional.get("coverage", {}))
    previous_adapters = coverage.get("adapters", {})
    current_adapters = adapter_result["coverage"]
    merged_adapters = dict(current_adapters)
    for key in (
        "registered",
        "selected",
        "executed",
        "failed",
        "permission_denied",
        "timed_out",
        "unavailable",
    ):
        merged_adapters[key] = list(
            dict.fromkeys(
                [
                    *previous_adapters.get(key, []),
                    *current_adapters.get(key, []),
                ]
            )
        )
    merged_adapters["operations_executed"] = [
        *previous_adapters.get("operations_executed", []),
        *current_adapters.get("operations_executed", []),
    ]
    coverage["adapters"] = merged_adapters
    return (
        {
            "account": identity,
            "region": primary_region,
            "services": resources_by_service,
            "resources": resources,
            "resources_by_service": resources_by_service,
            "coverage": coverage,
            "errors": [
                *list(provisional.get("errors", [])),
                *adapter_result["errors"],
            ],
        },
        authorization,
    )


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
