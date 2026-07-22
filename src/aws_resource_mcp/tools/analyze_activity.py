"""MCP presentation layer for zero-cost AWS resource activity analysis."""

import re
from typing import Any

from aws_resource_mcp.activity.engine import analyze_resource_activity
from aws_resource_mcp.aws.errors import AWSInventoryGlobalError
from aws_resource_mcp.config import DEFAULT_AWS_REGION
from aws_resource_mcp.models import remove_sensitive_fields
from aws_resource_mcp.tools.list_resources import _normalize_services


def _error_response(
    error_type: str, message: str, lookback_days: int
) -> dict[str, Any]:
    return {
        "status": "error",
        "summary": {
            "resources_analyzed": 0,
            "lookback_days": lookback_days,
            "paid_operations_executed": 0,
        },
        "resources": [],
        "coverage": {
            "cloudtrail_regions_checked": [],
            "service_api_signals": [],
            "blocked_sources": ["cloudwatch"],
            "limitations": [],
        },
        "errors": [{"service": "input", "error_type": error_type, "message": message}],
    }


def _normalize_regions(regions: list[str] | None) -> list[str]:
    if regions is None:
        return [DEFAULT_AWS_REGION]
    if not regions or any(not isinstance(region, str) for region in regions):
        raise ValueError("regions must contain at least one AWS Region name")
    normalized = list(dict.fromkeys(region.strip().lower() for region in regions))
    if any(
        not region or not re.fullmatch(r"[a-z0-9-]+", region) for region in normalized
    ):
        raise ValueError("regions contains an invalid AWS Region name")
    return normalized


def _normalize_resource_ids(resource_ids: list[str] | None) -> list[str]:
    if resource_ids is None:
        return []
    if not resource_ids or any(not isinstance(item, str) for item in resource_ids):
        raise ValueError("resource_ids must contain at least one string")
    normalized = list(dict.fromkeys(item.strip() for item in resource_ids))
    if any(not item or len(item) > 2048 for item in normalized):
        raise ValueError("resource_ids contains an invalid identifier")
    return normalized


def analizar_actividad_recursos(
    services: list[str] | None = None,
    regions: list[str] | None = None,
    resource_ids: list[str] | None = None,
    inactive_days: int = 30,
    lookback_days: int = 90,
    include_administrative_events: bool = True,
    include_paid_sources: bool = False,
    max_resources: int = 100,
    max_regions: int = 5,
    max_events_per_resource: int = 20,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Analyze last known AWS resource activity with conservative semantics.

    Free service API fields and CloudTrail Event History management events are
    combined through the common adapter pipeline. Functional usage,
    administrative activity, configuration changes, and state signals remain
    separate. Event History is regional, limited to 90 days, and does not
    normally include data events such as S3 GetObject, so unknown results are
    expected. CloudWatch could improve functional-usage coverage but is always
    blocked in this phase: setting ``include_paid_sources`` only requests a
    structured explanation and never grants consent or executes a metric call.
    The operation is read-only, bounded, and may return partial results.
    """
    try:
        normalized_services = _normalize_services(services)
        normalized_regions = _normalize_regions(regions)
        normalized_ids = _normalize_resource_ids(resource_ids)
        if type(inactive_days) is not int or inactive_days < 1 or inactive_days > 3650:
            raise ValueError("inactive_days must be an integer between 1 and 3650")
        if type(lookback_days) is not int or lookback_days < 1 or lookback_days > 90:
            raise ValueError("lookback_days must be an integer between 1 and 90")
        if not isinstance(include_administrative_events, bool) or not isinstance(
            include_paid_sources, bool
        ):
            raise ValueError("activity source flags must be booleans")
        if type(max_resources) is not int or not 1 <= max_resources <= 500:
            raise ValueError("max_resources must be an integer between 1 and 500")
        if type(max_regions) is not int or not 1 <= max_regions <= 10:
            raise ValueError("max_regions must be an integer between 1 and 10")
        if (
            type(max_events_per_resource) is not int
            or not 1 <= max_events_per_resource <= 50
        ):
            raise ValueError(
                "max_events_per_resource must be an integer between 1 and 50"
            )
        if (
            not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or not 1 <= timeout_seconds <= 120
        ):
            raise ValueError("timeout_seconds must be between 1 and 120")
    except (AttributeError, ValueError) as error:
        safe_lookback = lookback_days if type(lookback_days) is int else 0
        return _error_response("invalid_activity_parameters", str(error), safe_lookback)

    try:
        response = analyze_resource_activity(
            services=normalized_services or None,
            regions=normalized_regions,
            resource_ids=normalized_ids or None,
            inactive_days=inactive_days,
            lookback_days=lookback_days,
            include_administrative_events=include_administrative_events,
            include_paid_sources=include_paid_sources,
            max_resources=max_resources,
            max_regions=max_regions,
            max_events_per_resource=max_events_per_resource,
            timeout_seconds=float(timeout_seconds),
        )
    except AWSInventoryGlobalError as error:
        return _error_response(
            error.error["error_type"], error.error["message"], lookback_days
        )
    except Exception:
        return _error_response(
            "activity_lookup_failed",
            "The activity analysis could not be completed. Check the local AWS configuration.",
            lookback_days,
        )
    return remove_sensitive_fields(response)
