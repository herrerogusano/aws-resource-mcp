"""Bounded, anonymized access to free CloudTrail Event History."""

import json
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any

from aws_resource_mcp.activity.classifier import classify_cloudtrail_event
from aws_resource_mcp.activity.models import isoformat_utc
from aws_resource_mcp.aws.errors import describe_aws_error
from aws_resource_mcp.aws.operations import OperationGuard

MAX_CLOUDTRAIL_LOOKBACK_DAYS = 90
MAX_CLOUDTRAIL_PAGE_SIZE = 50
DEFAULT_MAX_EVENTS = 500


def _safe_event_fields(event: dict[str, Any], region: str) -> dict[str, Any]:
    """Extract only read-only and Region from the raw event envelope."""
    read_only: bool | None = None
    event_region = region
    raw = event.get("CloudTrailEvent")
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            payload = {}
        if isinstance(payload.get("readOnly"), bool):
            read_only = payload["readOnly"]
        if payload.get("awsRegion"):
            event_region = str(payload["awsRegion"])
    return {"ReadOnly": read_only, "Region": event_region}


def normalize_cloudtrail_event(event: dict[str, Any], region: str) -> dict[str, Any]:
    """Normalize one event without identities, IPs, keys, agents, or payloads."""
    safe = _safe_event_fields(event, region)
    classified = classify_cloudtrail_event({**event, **safe})
    resource_ids = [
        str(item.get("ResourceName"))
        for item in event.get("Resources", [])
        if item.get("ResourceName")
    ]
    return {
        "timestamp": isoformat_utc(event.get("EventTime")),
        "event_name": str(event.get("EventName") or "Unknown"),
        "event_source": str(event.get("EventSource") or "unknown"),
        "read_only": safe["ReadOnly"],
        "region": safe["Region"],
        "resource_ids": list(dict.fromkeys(resource_ids)),
        "activity_type": classified["activity_type"],
        "source": "cloudtrail_event_history",
        "confidence": classified["confidence"],
        "category": classified["category"],
    }


def _activity_error(region: str, error: Exception) -> dict[str, Any]:
    described = describe_aws_error("cloudtrail", error)
    error_type = (
        "activity_permission_denied"
        if described["error_type"] == "access_denied"
        else "activity_lookup_failed"
    )
    return {
        "service": "cloudtrail",
        "region": region,
        "error_type": error_type,
        "message": described["message"],
    }


def lookup_events(
    session: Any,
    *,
    regions: list[str],
    operation_guard: OperationGuard,
    lookback_days: int,
    max_events: int = DEFAULT_MAX_EVENTS,
    timeout_seconds: float = 30.0,
    resource_name: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Read and reuse Event History by Region with pagination and hard bounds."""
    bounded_lookback = min(max(lookback_days, 1), MAX_CLOUDTRAIL_LOOKBACK_DAYS)
    end_time = (now or datetime.now(UTC)).astimezone(UTC)
    start_time = end_time - timedelta(days=bounded_lookback)
    deadline = monotonic() + timeout_seconds
    normalized_events: list[dict[str, Any]] = []
    checked_regions: list[str] = []
    errors: list[dict[str, Any]] = []
    operations_executed: list[dict[str, str]] = []
    truncated = False

    region_count = max(len(regions), 1)
    base_region_budget = max_events // region_count
    budget_remainder = max_events % region_count
    timed_out = False
    for region_index, region in enumerate(regions):
        token: str | None = None
        region_succeeded = False
        region_event_count = 0
        region_budget = base_region_budget + (
            1 if region_index < budget_remainder else 0
        )
        try:
            client = session.client("cloudtrail", region_name=region)
            while True:
                if monotonic() >= deadline:
                    raise TimeoutError(
                        "The CloudTrail activity lookup reached its timeout."
                    )
                remaining = region_budget - region_event_count
                if remaining <= 0:
                    truncated = True
                    break
                parameters: dict[str, Any] = {
                    "StartTime": start_time,
                    "EndTime": end_time,
                    "MaxResults": min(MAX_CLOUDTRAIL_PAGE_SIZE, remaining),
                }
                if resource_name:
                    parameters["LookupAttributes"] = [
                        {
                            "AttributeKey": "ResourceName",
                            "AttributeValue": resource_name,
                        }
                    ]
                if token:
                    parameters["NextToken"] = token
                response = operation_guard.call(
                    client,
                    service="cloudtrail",
                    operation="LookupEvents",
                    **parameters,
                )
                operations_executed.append(
                    {
                        "service": "cloudtrail",
                        "operation": "LookupEvents",
                        "region": region,
                    }
                )
                page_events = [
                    normalize_cloudtrail_event(event, region)
                    for event in response.get("Events", [])
                ]
                normalized_events.extend(page_events)
                region_event_count += len(page_events)
                region_succeeded = True
                token = response.get("NextToken")
                if not token:
                    break
            if region_succeeded:
                checked_regions.append(region)
        except Exception as error:
            errors.append(_activity_error(region, error))
            timed_out = isinstance(error, TimeoutError)
        if timed_out or monotonic() >= deadline:
            if not any(
                item["error_type"] == "activity_lookup_failed" for item in errors
            ):
                errors.append(
                    {
                        "service": "cloudtrail",
                        "region": region,
                        "error_type": "activity_lookup_failed",
                        "message": "The activity lookup timed out and returned partial results.",
                    }
                )
            break

    return {
        "events": normalized_events[:max_events],
        "checked_regions": checked_regions,
        "errors": errors,
        "operations_executed": operations_executed,
        "lookback_days": bounded_lookback,
        "truncated": truncated,
        "max_concurrency": 1,
    }
