"""Uniform execution pipeline for discovery sources and service adapters."""

from collections.abc import Collection
from dataclasses import replace
from typing import Any

from aws_resource_mcp.aws.adapters.base import AdapterContext
from aws_resource_mcp.aws.adapters.registry import ADAPTERS, get_adapters
from aws_resource_mcp.aws.discovery import deduplicate_resources
from aws_resource_mcp.aws.errors import describe_aws_error
from aws_resource_mcp.aws.operations import (
    OPERATION_REGISTRY,
    OperationBlockedError,
    OperationGuard,
    OperationTimeoutError,
)
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
    resume_tokens: dict[str, str] | None = None,
    skip_discovery_services: Collection[str] | None = None,
) -> dict[str, Any]:
    """Execute every selected adapter through one error and coverage path."""
    selected = sorted(
        get_adapters(services),
        key=lambda adapter: adapter.metadata.scope != "global",
    )
    context = AdapterContext(
        session=session,
        account_id=account_id,
        regions=regions,
        primary_region=primary_region,
        operation_guard=operation_guard,
        include_details=include_details,
        include_cost_indicators=include_cost_indicators,
        resume_tokens=dict(resume_tokens or {}),
    )
    adapter_resources: list[Resource] = []
    executed: list[str] = []
    failed: list[str] = []
    errors: list[InventoryError] = []
    pending_operations: list[dict[str, Any]] = []
    enrichment_pending_operations: list[dict[str, Any]] = []
    permission_denied: list[str] = []
    timed_out: list[str] = []
    unavailable: list[str] = []
    skip_discovery = set(skip_discovery_services or ())

    def pending_for(
        adapter: Any,
        operations: tuple[tuple[str, str], ...],
        *,
        stage: str,
        operation_regions: list[str] | None = None,
        request_multiplier: int = 1,
    ) -> list[dict[str, Any]]:
        pending: list[dict[str, Any]] = []
        scope_regions = operation_regions or (
            ["global"] if adapter.metadata.scope == "global" else list(regions)
        )
        for service, operation in operations:
            spec = OPERATION_REGISTRY.get((service, operation))
            if spec is None or spec.cost_classification != "potentially_billable":
                continue
            blocked_regions = []
            for region_name in scope_regions:
                try:
                    operation_guard.require_allowed(
                        service=service,
                        operation=operation,
                        region=region_name,
                    )
                except OperationBlockedError:
                    blocked_regions.append(region_name)
            if blocked_regions:
                pending.append(
                    {
                        "service": service,
                        "operation": operation,
                        "adapter": adapter.metadata.service_name,
                        "stage": stage,
                        "scope": adapter.metadata.scope,
                        "regions": blocked_regions,
                        "purpose": (
                            f"Enumerate {adapter.metadata.service_name} resources"
                            if stage == "discovery"
                            else f"Enrich {adapter.metadata.service_name} resources"
                        ),
                        "cost_classification": spec.cost_classification,
                        "estimated_max_requests": max(
                            1, len(blocked_regions) * request_multiplier
                        ),
                        "pagination_possible": (
                            (service, operation)
                            in adapter.metadata.paginated_operations
                        ),
                        "executed": False,
                    }
                )
        return pending

    for adapter_index, adapter in enumerate(selected):
        name = adapter.metadata.service_name
        discovery_pending = (
            []
            if name in skip_discovery
            else pending_for(
                adapter,
                adapter.metadata.discovery_operations,
                stage="discovery",
            )
        )
        if discovery_pending:
            pending_operations.extend(discovery_pending)
            continue
        execution_contexts = (
            [replace(context, regions=[region]) for region in regions]
            if adapter.metadata.scope == "regional"
            else [context]
        )
        succeeded = False
        adapter_failed = False
        for current_context in execution_contexts:
            try:
                discovered = (
                    [] if name in skip_discovery else adapter.discover(current_context)
                )
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
                enrichment_candidates = deduplicate_resources(relevant, discovered)
                enrichment_pending = pending_for(
                    adapter,
                    adapter.metadata.enrichment_operations,
                    stage="enrichment",
                    operation_regions=(
                        ["global"]
                        if adapter.metadata.scope == "global"
                        else current_context.regions
                    ),
                    request_multiplier=max(1, len(enrichment_candidates)),
                )
                if enrichment_pending:
                    enrichment_pending_operations.extend(enrichment_pending)
                    adapter_resources.extend(enrichment_candidates)
                else:
                    adapter_resources.extend(
                        adapter.enrich(enrichment_candidates, current_context)
                    )
                succeeded = True
            except OperationTimeoutError as error:
                adapter_failed = True
                errors.append(error.error)
                timed_out.extend(
                    item.metadata.service_name for item in selected[adapter_index:]
                )
                break
            except OperationBlockedError as error:
                adapter_failed = True
                errors.append(error.error)
                break
            except Exception as error:
                adapter_failed = True
                described = describe_aws_error(name, error)
                errors.append(described)
                if described["error_type"] == "access_denied":
                    permission_denied.append(name)
                else:
                    unavailable.append(name)
        if succeeded:
            executed.append(name)
        if adapter_failed:
            failed.append(name)
        if timed_out:
            break

    def aggregate_pending(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for item in items:
            key = (
                item["service"],
                item["operation"],
                item["adapter"],
                item["stage"],
            )
            if key not in grouped:
                grouped[key] = dict(item)
                grouped[key]["regions"] = list(item["regions"])
                continue
            current = grouped[key]
            current["regions"] = sorted(set(current["regions"]) | set(item["regions"]))
            current["estimated_max_requests"] += item["estimated_max_requests"]
        return list(grouped.values())

    pending_operations = aggregate_pending(pending_operations)
    enrichment_pending_operations = aggregate_pending(enrichment_pending_operations)
    selected_names = [adapter.metadata.service_name for adapter in selected]
    return {
        "resources": deduplicate_resources(discovered_resources, adapter_resources),
        "errors": [*context.errors, *errors],
        "coverage": {
            "registered": list(ADAPTERS),
            "selected": selected_names,
            "executed": executed,
            "failed": failed,
            "pending_consent": sorted({item["adapter"] for item in pending_operations}),
            "pending_operations": pending_operations,
            "enrichment_pending_operations": enrichment_pending_operations,
            "permission_denied": sorted(set(permission_denied)),
            "timed_out": list(dict.fromkeys(timed_out)),
            "unavailable": sorted(set(unavailable)),
            "truncated": bool(context.truncations),
            "truncations": context.truncations,
            "continuation_tokens": context.continuation_tokens,
            "operations_executed": context.operations_executed,
        },
    }
