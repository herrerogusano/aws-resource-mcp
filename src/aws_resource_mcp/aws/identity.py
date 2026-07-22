"""AWS identity lookup through the Security Token Service."""

from typing import Any

from aws_resource_mcp.aws.operations import OperationGuard


def get_aws_identity(
    session: Any,
    operation_guard: OperationGuard | None = None,
) -> dict[str, str | None]:
    """Return a normalized, non-secret representation of the caller identity."""
    response = (operation_guard or OperationGuard()).call(
        session.client("sts"), service="sts", operation="GetCallerIdentity"
    )
    return {
        "account_id": response.get("Account"),
        "arn": response.get("Arn"),
        "user_id": response.get("UserId"),
    }
