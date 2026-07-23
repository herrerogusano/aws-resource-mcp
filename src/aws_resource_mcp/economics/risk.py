"""Transparent economic-risk scoring over the normalized resource model."""

from collections import Counter
from typing import Any

from aws_resource_mcp.models import Resource

_WEIGHTS = {"low": 20, "medium": 45, "high": 70}
_LEVELS = (
    (90, "critical"),
    (65, "high"),
    (40, "medium"),
    (1, "low"),
    (0, "none_detected"),
)


def _resource_key(resource: Resource) -> tuple[str, str, str]:
    return (
        str(resource.get("service") or ""),
        str(resource.get("region") or "global"),
        str(resource.get("arn") or resource.get("id") or resource.get("name") or ""),
    )


def merge_activity(
    resources: list[Resource], activity_resources: list[Resource]
) -> list[Resource]:
    """Merge activity by normalized identity without service-specific paths."""
    activity_by_key = {
        _resource_key(item): item.get("activity", {}) for item in activity_resources
    }
    for resource in resources:
        if _resource_key(resource) in activity_by_key:
            resource["activity"] = activity_by_key[_resource_key(resource)]
    return resources


def assess_resource(resource: Resource) -> dict[str, Any]:
    """Assess potential cost without claiming that any spend was incurred."""
    indicators = list(resource.get("cost_indicators", []))
    activity = resource.get("activity", {})
    score = max(
        (_WEIGHTS.get(str(item.get("severity")), 0) for item in indicators),
        default=0,
    )
    reasons: list[dict[str, Any]] = [
        {
            "source": "inventory_cost_indicator",
            "type": item.get("type"),
            "severity": item.get("severity"),
            "description": item.get("description"),
        }
        for item in indicators
    ]
    activity_status = str(activity.get("status") or "unknown")
    if activity_status == "inactive_candidate" and indicators:
        score += 15
        reasons.append(
            {
                "source": "activity_analysis",
                "type": "inactive_candidate",
                "description": "Potential cost indicators coexist with no recent known activity.",
            }
        )
    if len(indicators) > 1:
        score += min(15, (len(indicators) - 1) * 5)
    score = min(score, 100)
    level = next(level for threshold, level in _LEVELS if score >= threshold)
    recommendations = []
    if indicators:
        recommendations.append(
            "Review this resource and its pricing configuration before changing or deleting it."
        )
    if activity_status == "inactive_candidate":
        recommendations.append(
            "Validate functional usage with the owner; inactivity is a candidate signal, not proof."
        )
    limitations = [
        "Inventory indicators show potential cost, not billed spend.",
        "No resource is modified, stopped, or deleted.",
    ]
    if activity_status in {"unknown", "not_supported"}:
        limitations.append(
            "Recent functional usage is not known with sufficient confidence."
        )
    return {
        "risk_level": level,
        "priority_score": score,
        "indicators": indicators,
        "activity_status": activity_status,
        "actual_cost_status": "not_checked",
        "actual_cost": None,
        "free_tier_status": "unknown",
        "evidence": reasons,
        "limitations": limitations,
        "recommendations": recommendations,
    }


def analyze_resources(resources: list[Resource]) -> dict[str, Any]:
    """Return deterministic risk ordering and aggregate counts."""
    assessed = [
        {"resource": resource, "economics": assess_resource(resource)}
        for resource in resources
    ]
    assessed.sort(
        key=lambda item: (
            -item["economics"]["priority_score"],
            str(item["resource"].get("service")),
            str(item["resource"].get("name") or item["resource"].get("id")),
        )
    )
    counts = Counter(item["economics"]["risk_level"] for item in assessed)
    return {
        "resources": assessed,
        "summary": {
            "resources_analyzed": len(assessed),
            "risk_levels": {
                level: counts[level]
                for level in (
                    "critical",
                    "high",
                    "medium",
                    "low",
                    "none_detected",
                    "unknown",
                )
            },
        },
    }
