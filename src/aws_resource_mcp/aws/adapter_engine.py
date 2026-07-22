"""Uniform execution pipeline for discovery sources and service adapters."""

from collections.abc import Collection
from dataclasses import replace
from typing import Any

from aws_resource_mcp.aws.adapters.base import AdapterContext
from aws_resource_mcp.aws.adapters.registry import ADAPTERS, get_adapters
from aws_resource_mcp.aws.discovery import deduplicate_resources
from aws_resource_mcp.aws.errors import describe_aws_error
from aws_resource_mcp.aws.operations import OperationBlockedError, OperationGuard
from aws_resource_mcp.models import InventoryError, Resource


def execute_adapters(
    session: Any,
    *,
    account_id: str | None,
    regions: list[str],
    primary_region: str,
    discovered_resources: list[Resource],
    services: Collection[str] | None,
    include_details: bool,
    include_cost_indicators: bool,
    operation_guard: OperationGuard,
) -> dict[str, Any]:
    """Execute every selected adapter through one error and coverage path."""
    selected = get_adapters(services)
    context = AdapterContext(
        session=session,
        account_id=account_id,
        regions=regions,
        primary_region=primary_region,
        operation_guard=operation_guard,
        include_details=include_details,
        include_cost_indicators=include_cost_indicators,
    )
    adapter_resources: list[Resource] = []
    executed: list[str] = []
    failed: list[str] = []
    errors: list[InventoryError] = []

    for adapter in selected:
        name = adapter.metadata.service_name
        execution_contexts = (
            [replace(context, regions=[region]) for region in regions]
            if adapter.metadata.scope == "regional"
            else [context]
        )
        succeeded = False
        adapter_failed = False
        for current_context in execution_contexts:
            try:
                discovered = adapter.discover(current_context)
                relevant = [
                    resource
                    for resource in discovered_resources
                    if resource.get("service") == name
                    and (
                        adapter.metadata.scope == "global"
                        or resource.get("region") in current_context.regions
                    )
                ]
                adapter_resources.extend(discovered)
                adapter_resources.extend(
                    adapter.enrich(relevant, current_context)
                )
                succeeded = True
            except OperationBlockedError as error:
                adapter_failed = True
                errors.append(error.error)
                break
            except Exception as error:
                adapter_failed = True
                errors.append(describe_aws_error(name, error))
        if succeeded:
            executed.append(name)
        if adapter_failed:
            failed.append(name)

    selected_names = [adapter.metadata.service_name for adapter in selected]
    return {
        "resources": deduplicate_resources(discovered_resources, adapter_resources),
        "errors": [*context.errors, *errors],
        "coverage": {
            "registered": list(ADAPTERS),
            "selected": selected_names,
            "executed": executed,
            "failed": failed,
            "operations_executed": context.operations_executed,
        },
    }
