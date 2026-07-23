"""Common activity signal model and conservative result classification."""

from datetime import UTC, datetime, timedelta
from typing import Any

from aws_resource_mcp.models import (
    ActivityEvidence,
    ActivityType,
    Resource,
    ResourceActivity,
)

ACTIVITY_STATUSES = frozenset(
    {
        "active",
        "inactive_candidate",
        "unknown",
        "not_supported",
        "blocked_by_cost_policy",
        "error",
    }
)
ACTIVITY_TYPES = frozenset(
    {
        "functional_usage",
        "administrative_activity",
        "configuration_change",
        "resource_state",
        "unknown",
    }
)
CONFIDENCE_LEVELS = frozenset({"high", "medium", "low", "unknown"})

_TYPE_TIMESTAMP_FIELDS: dict[ActivityType, str] = {
    "functional_usage": "last_functional_usage_at",
    "administrative_activity": "last_administrative_activity_at",
    "configuration_change": "last_configuration_change_at",
    "resource_state": "last_state_change_at",
}


def parse_timestamp(value: Any) -> datetime | None:
    """Parse SDK datetimes, ISO strings, and Unix timestamps as UTC."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)) or (
        isinstance(value, str) and value.strip().isdigit()
    ):
        try:
            parsed = datetime.fromtimestamp(float(value), tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def isoformat_utc(value: Any) -> str | None:
    parsed = parse_timestamp(value)
    return parsed.isoformat().replace("+00:00", "Z") if parsed else None


def normalize_signal(signal: dict[str, Any]) -> ActivityEvidence:
    """Return only the explainable, non-sensitive fields in an activity signal."""
    activity_type = signal.get("activity_type", "unknown")
    if activity_type not in ACTIVITY_TYPES:
        activity_type = "unknown"
    confidence = signal.get("confidence", "unknown")
    if confidence not in CONFIDENCE_LEVELS:
        confidence = "unknown"
    evidence: ActivityEvidence = {
        "timestamp": isoformat_utc(signal.get("timestamp")),
        "event_name": str(
            signal.get("event_name") or signal.get("activity_name") or "Unknown"
        ),
        "event_source": str(
            signal.get("event_source") or signal.get("source") or "unknown"
        ),
        "read_only": signal.get("read_only")
        if isinstance(signal.get("read_only"), bool)
        else None,
        "region": str(signal.get("region") or "global"),
        "resource_ids": list(
            dict.fromkeys(str(item) for item in signal.get("resource_ids", []) if item)
        ),
        "activity_type": activity_type,
        "source": str(signal.get("source") or "unknown"),
        "confidence": confidence,
        "category": str(signal.get("category") or "unknown"),
    }
    return evidence


def build_activity_result(
    resource: Resource,
    signals: list[dict[str, Any]],
    *,
    now: datetime,
    inactive_days: int,
    lookback_days: int,
    source_checked: bool,
    adapter_supported: bool,
    source_error: bool = False,
    limitations: list[str] | None = None,
    include_paid_sources: bool = False,
    max_events: int = 20,
) -> ResourceActivity:
    """Classify activity without treating weak evidence as functional use."""
    normalized = [normalize_signal(signal) for signal in signals]
    normalized.sort(
        key=lambda item: (
            parse_timestamp(item.get("timestamp")) or datetime.min.replace(tzinfo=UTC)
        ),
        reverse=True,
    )
    evidence = normalized[:max_events]
    timestamped = [
        item for item in normalized if parse_timestamp(item.get("timestamp"))
    ]
    best = timestamped[0] if timestamped else None
    latest_by_type: dict[str, str | None] = {
        field: None for field in _TYPE_TIMESTAMP_FIELDS.values()
    }
    for item in timestamped:
        field = _TYPE_TIMESTAMP_FIELDS.get(item["activity_type"])
        if field and latest_by_type[field] is None:
            latest_by_type[field] = item["timestamp"]

    threshold = now.astimezone(UTC) - timedelta(days=inactive_days)
    best_at = parse_timestamp(best.get("timestamp")) if best else None
    created_at = parse_timestamp(resource.get("created_at"))
    recent = bool(best_at and best_at >= threshold)
    old_enough = bool(created_at and created_at < threshold)
    official_last_use = any(
        item["activity_type"] == "functional_usage"
        and item["source"] != "cloudtrail_event_history"
        for item in timestamped
    )

    if not adapter_supported:
        status = "not_supported"
    elif source_error and not normalized:
        status = "error"
    elif recent:
        status = "active"
    elif source_checked and (old_enough or official_last_use) and best_at:
        status = "inactive_candidate"
    else:
        status = "unknown"

    result_limitations = list(dict.fromkeys(limitations or []))
    if any(item["activity_type"] == "resource_state" for item in normalized):
        result_limitations.append(
            "Resource state is indirect evidence and does not prove traffic or functional use."
        )
    if not timestamped:
        result_limitations.append(
            "No timestamped activity evidence was directly related to this resource."
        )
    if status == "inactive_candidate":
        result_limitations.append(
            "This is a review candidate, not proof that the resource is unused."
        )

    days_since = (now.astimezone(UTC) - best_at).days if best_at else None
    paid_available = resource.get("service") not in {"iam", "cloudformation"}
    paid_enrichment: dict[str, Any] = {
        "source": "cloudwatch",
        "purpose": "Determine recent functional usage from service metrics.",
        "operation": "GetMetricData",
        "executed": False,
        "requires_explicit_confirmation": True,
        "reason": "Metric retrieval requests can generate charges.",
    }
    return {
        "status": status,  # type: ignore[typeddict-item]
        "last_activity_at": best.get("timestamp") if best else None,
        "days_since_activity": days_since,
        "activity_type": best["activity_type"] if best else "unknown",
        "activity_name": best["event_name"] if best else None,
        "source": best["source"] if best else None,
        "confidence": best["confidence"] if best else "unknown",
        "lookback_days": lookback_days,
        **latest_by_type,
        "best_known_activity_at": best.get("timestamp") if best else None,
        "best_known_activity_type": best["activity_type"] if best else "unknown",
        "evidence": evidence,
        "limitations": list(dict.fromkeys(result_limitations)),
        "paid_data_available": paid_available,
        "paid_data_requested": include_paid_sources,
        "paid_data_executed": False,
        "paid_enrichment": paid_enrichment if paid_available else {},
    }
