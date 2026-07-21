"""AWS identity lookup through the Security Token Service."""

from typing import Any


def get_aws_identity(session: Any) -> dict[str, str | None]:
    """Return a normalized, non-secret representation of the caller identity."""
    response = session.client("sts").get_caller_identity()
    return {
        "account_id": response.get("Account"),
        "arn": response.get("Arn"),
        "user_id": response.get("UserId"),
    }
