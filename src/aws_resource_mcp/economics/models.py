"""Uniform economic states and safe result helpers."""

from typing import Literal, TypedDict

EconomicRiskLevel = Literal[
    "none_detected", "low", "medium", "high", "critical", "unknown"
]
ActualCostStatus = Literal[
    "confirmed",
    "zero_reported",
    "not_checked",
    "pending_consent",
    "blocked_by_cost_policy",
    "unavailable",
    "permission_denied",
    "truncated",
    "error",
]
FreeTierStatus = Literal[
    "within_limit",
    "approaching_limit",
    "limit_exceeded",
    "credit_available",
    "credit_exhausted",
    "not_eligible",
    "not_applicable",
    "unknown",
    "unavailable",
    "permission_denied",
    "error",
]


class EconomicAssessment(TypedDict):
    """Same economic result shape for every normalized AWS resource."""

    risk_level: EconomicRiskLevel
    priority_score: int
    indicators: list[dict]
    activity_status: str
    actual_cost_status: ActualCostStatus
    actual_cost: dict | None
    free_tier_status: FreeTierStatus
    evidence: list[dict]
    limitations: list[str]
    recommendations: list[str]
