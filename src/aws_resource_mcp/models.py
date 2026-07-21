"""JSON-compatible structures shared by the AWS inventory modules."""

from datetime import date, datetime
from typing import Any, TypedDict


class InventoryError(TypedDict):
    """A safe, user-facing description of an AWS query failure."""

    service: str
    error_type: str
    message: str


def to_iso8601(value: Any) -> str | None:
    """Convert date-like SDK values to ISO 8601 strings."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return None
