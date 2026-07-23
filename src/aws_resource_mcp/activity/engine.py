"""Common activity engine combining adapters and CloudTrail Event History."""

from collections.abc import Collection
from datetime import UTC, datetime
from typing import Any

from aws_resource_mcp.activity.cloudtrail_activity import lookup_events
from aws_resource_mcp.activity.models import build_activity_result
from aws_resource_mcp.aws.adapters.base import ActivityContext
from aws_resource_mcp.aws.adapters.registry import ADAPTERS, get_adapters
from aws_resource_mcp.aws.discovery import (
    deduplicate_resources,
    group_resources_by_service,
)
from aws_resource_mcp.aws.inventory import collect_general_aws_inventory
from aws_resource_mcp.aws.operations import OperationBlockedError, OperationGuard
from aws_resource_mcp.aws.session import create_aws_session
from aws_resource_mcp.config import AWSConfig, DEFAULT_AWS_REGION
from aws_resource_mcp.models import Resource

DEFAULT_MAX_RESOURCES = 100
DEFAULT_MAX_REGIONS = 5
DEFAULT_MAX_EVENTS_PER_RESOURCE = 20
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_TOTAL_CLOUDTRAIL_EVENTS = 500

_SERVICE_LIMITATIONS = {
    "lambda": "LastModified is a configuration timestamp, not the last invocation.",
    "s3": "Event History does not contain S3 object access data events; object access is unknown.",
    "ec2": "Instance state and launch time do not demonstrate workload or network activity.",
    "rds": "Database status does not demonstrate recent client connections.",
    "dynamodb": "No Scan or Query operation is performed to infer table usage.",
    "ecs": "Running tasks and desired count are state signals, not proof of traffic.",
    "apigateway": "The API is not invoked and request metrics are not queried.",
    "sqs": "Messages are not received or inspected during activity analysis.",
    "sns": "No message is published during activity analysis.",
    "cloudfront": "Distribution status does not demonstrate recent requests.",
    "route53": "Hosted-zone existence does not demonstrate recent DNS queries.",
}


def _aliases(resource: Resource) -> set[str]:
    aliases: set[str] = set()
    for value in (resource.get("arn"), resource.get("id"), resource.get("name")):
        if not value:
            continue
        text = str(value)
        aliases.add(text)
        aliases.add(text.rsplit("/", 1)[-1])
        aliases.add(text.rsplit(":", 1)[-1])
    return aliases


def _event_matches_resource(event: dict[str, Any], resource: Resource) -> bool:
    event_ids = set(str(item) for item in event.get("resource_ids", []) if item)
    if not event_ids:
        return False
    aliases = _aliases(resource)
    expanded_event_ids = set(event_ids)
    for item in event_ids:
        expanded_event_ids.add(item.rsplit("/", 1)[-1])
        expanded_event_ids.add(item.rsplit(":", 1)[-1])
    return bool(aliases & expanded_event_ids)


def _signal_matches_resource(signal: dict[str, Any], resource: Resource) -> bool:
    return bool(_aliases(resource) & set(signal.get("resource_ids", [])))


def _blocked_cloudwatch_source(include_paid_sources: bool) -> dict[str, Any]:
    guard = OperationGuard("free-only", paid_operations_confirmed=False)
    try:
        guard.require_allowed(service="cloudwatch", operation="GetMetricData")
    except OperationBlockedError as error:
        return {
            "status": "blocked_by_cost_policy",
            "source": "cloudwatch",
            "operation": "GetMetricData",
            "reason": "Metric retrieval requests can generate charges.",
            "executed": False,
            "requested": include_paid_sources,
            "consent_required": True,
            "guard_error": error.error["error_type"],
        }
    raise AssertionError("CloudWatch metric retrieval must remain blocked in Phase 6")


def _inventory_for_regions(
    session: Any,
    regions: list[str],
    services: Collection[str] | None,
) -> tuple[list[Resource], list[dict[str, Any]], list[dict[str, Any]]]:
    resource_groups: list[list[Resource]] = []
    errors: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    for index, region in enumerate(regions):
        inventory = collect_general_aws_inventory(
            region,
            session=session,
            services=services,
            all_regions=False,
            include_details=True,
            include_cost_indicators=False,
            cost_mode="free-only",
            confirm_potentially_billable_operations=False,
            include_global_resource_explorer_results=index == 0,
        )
        resource_groups.append(inventory.get("resources", []))
        errors.extend(inventory.get("errors", []))
        coverage.append(inventory.get("coverage", {}))
    resources = deduplicate_resources(*resource_groups)
    resources = [
        resource
        for resource in resources
        if resource.get("region") in {*regions, "global"}
    ]
    return resources, errors, coverage


def _adapter_signals(
    resources: list[Resource],
    context: ActivityContext,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    signals: list[dict[str, Any]] = []
    services_with_signals: list[str] = []
    errors: list[dict[str, Any]] = []
    for adapter in get_adapters():
        relevant = [
            resource
            for resource in resources
            if resource.get("service") == adapter.metadata.service_name
        ]
        if not relevant:
            continue
        try:
            current = adapter.get_free_activity_signals(relevant, context)
            signals.extend(current)
            if current:
                services_with_signals.append(adapter.metadata.service_name)
        except Exception:
            errors.append(
                {
                    "service": adapter.metadata.service_name,
                    "error_type": "activity_data_unavailable",
                    "message": "Free service activity signals could not be normalized.",
                }
            )
    return signals, services_with_signals, errors


def attach_free_activity_summaries(
    resources: list[Resource],
    *,
    now: datetime | None = None,
) -> list[Resource]:
    """Attach a compact summary from fields already present; never query AWS."""
    context = ActivityContext(30, 90, True, 1)
    signals, _, _ = _adapter_signals(resources, context)
    current_time = now or datetime.now(UTC)
    for resource in resources:
        relevant = [
            signal for signal in signals if _signal_matches_resource(signal, resource)
        ]
        result = build_activity_result(
            resource,
            relevant,
            now=current_time,
            inactive_days=30,
            lookback_days=90,
            source_checked=False,
            adapter_supported=resource.get("service") in ADAPTERS,
            limitations=[
                "This summary uses only fields already returned by service APIs."
            ],
            max_events=1,
        )
        resource["activity"] = {
            "status": result["status"],
            "best_known_activity_at": result["best_known_activity_at"],
            "best_known_activity_type": result["best_known_activity_type"],
            "confidence": result["confidence"],
            "source": result["source"],
            "limitations": result["limitations"],
            "paid_data_executed": False,
        }
    return resources


def analyze_resource_activity(
    *,
    services: Collection[str] | None = None,
    regions: list[str] | None = None,
    resource_ids: Collection[str] | None = None,
    inactive_days: int = 30,
    lookback_days: int = 90,
    include_administrative_events: bool = True,
    include_paid_sources: bool = False,
    max_resources: int = DEFAULT_MAX_RESOURCES,
    max_regions: int = DEFAULT_MAX_REGIONS,
    max_events_per_resource: int = DEFAULT_MAX_EVENTS_PER_RESOURCE,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Analyze resources through one adapter model and reusable Event History."""
    requested_regions = list(dict.fromkeys(regions or [DEFAULT_AWS_REGION]))
    selected_regions = requested_regions[:max_regions]
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    config = AWSConfig.from_sources(region=selected_regions[0], cost_mode="free-only")
    aws_session = session or create_aws_session(config.region, config.profile_name)
    resources, inventory_errors, inventory_coverage = _inventory_for_regions(
        aws_session, selected_regions, services
    )
    requested_ids = set(resource_ids or [])
    if requested_ids:
        resources = [
            resource for resource in resources if _aliases(resource) & requested_ids
        ]
    matching_resource_count = len(resources)
    resources = resources[:max_resources]

    context = ActivityContext(
        inactive_days,
        lookback_days,
        include_administrative_events,
        max_events_per_resource,
    )
    service_signals, signal_services, signal_errors = _adapter_signals(
        resources, context
    )
    cloudtrail = (
        lookup_events(
            aws_session,
            regions=selected_regions,
            operation_guard=OperationGuard("free-only"),
            lookback_days=lookback_days,
            max_events=min(
                MAX_TOTAL_CLOUDTRAIL_EVENTS,
                max(max_events_per_resource, len(resources) * max_events_per_resource),
            ),
            timeout_seconds=timeout_seconds,
            resource_name=next(iter(requested_ids))
            if len(requested_ids) == 1
            else None,
            now=current_time,
        )
        if resources
        else {
            "events": [],
            "checked_regions": [],
            "errors": [],
            "operations_executed": [],
            "lookback_days": lookback_days,
            "truncated": False,
            "max_concurrency": 1,
        }
    )

    event_signals = [
        event
        for event in cloudtrail["events"]
        if include_administrative_events
        or event.get("activity_type") != "administrative_activity"
    ]
    all_errors = [*inventory_errors, *signal_errors, *cloudtrail["errors"]]
    for resource in resources:
        relevant_service = [
            signal
            for signal in service_signals
            if _signal_matches_resource(signal, resource)
        ]
        relevant_events = [
            event
            for event in event_signals
            if _event_matches_resource(event, resource)
            and (
                resource.get("region") == "global"
                or event.get("region") == resource.get("region")
            )
        ]
        resource_region = str(resource.get("region") or "global")
        trail_checked = (
            bool(cloudtrail["checked_regions"])
            if resource_region == "global"
            else resource_region in cloudtrail["checked_regions"]
        )
        source_error = any(
            error.get("service") in {"cloudtrail", resource.get("service")}
            and error.get("error_type")
            not in {
                "access_denied",
                "activity_permission_denied",
                "cost_permission_required",
                "activity_source_blocked_by_cost",
            }
            for error in all_errors
        )
        limitations = [
            "CloudTrail Event History covers management events for at most 90 days and may not prove functional usage.",
            "CloudWatch metric enrichment was not executed because it is blocked by the zero-cost policy.",
        ]
        service_limitation = _SERVICE_LIMITATIONS.get(str(resource.get("service")))
        if service_limitation:
            limitations.append(service_limitation)
        resource["activity"] = build_activity_result(
            resource,
            [*relevant_service, *relevant_events],
            now=current_time,
            inactive_days=inactive_days,
            lookback_days=lookback_days,
            source_checked=trail_checked
            or any(
                signal.get("activity_type") == "functional_usage"
                for signal in relevant_service
            ),
            adapter_supported=resource.get("service") in ADAPTERS,
            source_error=source_error,
            limitations=limitations,
            include_paid_sources=include_paid_sources,
            max_events=max_events_per_resource,
        )

    counts = {
        "active": 0,
        "inactive_candidate": 0,
        "unknown": 0,
        "not_supported": 0,
        "blocked_by_cost_policy": 0,
        "error": 0,
    }
    for resource in resources:
        counts[resource["activity"]["status"]] += 1
    limitations: list[str] = []
    if len(requested_regions) > len(selected_regions):
        limitations.append(
            f"Region limit applied: analyzed {len(selected_regions)} of {len(requested_regions)} requested Regions."
        )
    if matching_resource_count > max_resources:
        limitations.append(
            f"Resource limit applied: at most {max_resources} resources were analyzed."
        )
    if cloudtrail["truncated"]:
        limitations.append("CloudTrail events were truncated by the execution limit.")
    if any(
        item.get("status") != "complete_for_supported_resources"
        for item in inventory_coverage
    ):
        limitations.append(
            "Resource inventory coverage was partial in at least one Region."
        )
    blocked_source = _blocked_cloudwatch_source(include_paid_sources)
    status = "partial" if all_errors or limitations else "ok"
    return {
        "status": status,
        "summary": {
            "resources_analyzed": len(resources),
            "active": counts["active"],
            "inactive_candidates": counts["inactive_candidate"],
            "unknown": counts["unknown"],
            "not_supported": counts["not_supported"],
            "errors": counts["error"],
            "lookback_days": lookback_days,
            "inactive_days": inactive_days,
            "paid_operations_executed": 0,
        },
        "resources": resources,
        "resources_by_service": group_resources_by_service(resources),
        "coverage": {
            "cloudtrail_regions_checked": cloudtrail["checked_regions"],
            "service_api_signals": signal_services,
            "sources_used": [
                *(
                    ["cloudtrail_event_history"]
                    if cloudtrail["checked_regions"]
                    else []
                ),
                *(["service_apis"] if signal_services else []),
            ],
            "blocked_sources": [blocked_source],
            "missing_permissions": [
                error
                for error in all_errors
                if error.get("error_type")
                in {"access_denied", "activity_permission_denied"}
            ],
            "limitations": limitations,
            "cloudtrail_events_reused": len(cloudtrail["events"]),
            "cloudtrail_operations_executed": len(cloudtrail["operations_executed"]),
            "max_concurrency": cloudtrail["max_concurrency"],
        },
        "errors": all_errors,
    }
