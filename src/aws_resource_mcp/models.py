"""JSON-compatible structures shared by the AWS inventory modules."""

from datetime import date, datetime
from typing import Any, Literal, NotRequired, TypedDict

SENSITIVE_FIELD_NAMES = frozenset(
    {
        "aws_access_key_id",
        "aws_secret_access_key",
        "session_token",
        "credentials",
        "environment",
        "environmentvariables",
        "policy",
        "policydocument",
        "templatebody",
        "secretstring",
    }
)


class InventoryError(TypedDict):
    """A safe, user-facing description of an AWS query failure."""

    service: str
    error_type: str
    message: str
    operation: NotRequired[str]
    executed: NotRequired[bool]


class CostIndicator(TypedDict):
    """A potential cost signal, never a statement of actual spend."""

    type: str
    severity: Literal["low", "medium", "high"]
    description: str
    actual_cost_confirmed: Literal[False]


class ResourceActivity(TypedDict):
    """Uniform activity placeholder until activity analysis is implemented."""

    status: Literal["not_analyzed"]


class Resource(TypedDict):
    """Uniform JSON-compatible representation shared by every source."""

    id: str | None
    arn: str | None
    name: str | None
    service: str
    resource_type: str
    region: str
    account_id: str | None
    state: str | None
    created_at: str | None
    sources: list[str]
    details: dict[str, Any]
    cost_indicators: list[CostIndicator]
    activity: ResourceActivity


def to_iso8601(value: Any) -> str | None:
    """Convert date-like SDK values to ISO 8601 strings."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return None


def make_resource(
    *,
    service: str,
    resource_type: str,
    region: str,
    source: str,
    identifier: str | None = None,
    arn: str | None = None,
    name: str | None = None,
    account_id: str | None = None,
    state: str | None = None,
    created_at: Any = None,
    details: dict[str, Any] | None = None,
    cost_indicators: list[CostIndicator] | None = None,
) -> Resource:
    """Create a resource with every common root field present."""
    return {
        "id": identifier,
        "arn": arn,
        "name": name or identifier,
        "service": service,
        "resource_type": resource_type,
        "region": region or "global",
        "account_id": account_id,
        "state": state,
        "created_at": to_iso8601(created_at),
        "sources": [source],
        "details": remove_sensitive_fields(details or {}),
        "cost_indicators": cost_indicators or [],
        "activity": {"status": "not_analyzed"},
    }


def cost_indicator(
    indicator_type: str,
    severity: Literal["low", "medium", "high"],
    description: str,
) -> CostIndicator:
    """Build a uniform potential-cost indicator."""
    return {
        "type": indicator_type,
        "severity": severity,
        "description": description,
        "actual_cost_confirmed": False,
    }


def remove_sensitive_fields(value: Any) -> Any:
    """Recursively remove fields that can contain credentials or payloads."""
    if isinstance(value, dict):
        return {
            key: remove_sensitive_fields(item)
            for key, item in value.items()
            if str(key).lower() not in SENSITIVE_FIELD_NAMES
        }
    if isinstance(value, list):
        return [remove_sensitive_fields(item) for item in value]
    return value
