"""Anonymous identity helpers shared by health and coverage diagnostics."""

from typing import Any


def mask_account_id(account_id: Any) -> str | None:
    """Keep only the final four account digits."""
    value = str(account_id or "")
    if not value:
        return None
    visible = min(4, len(value))
    return ("*" * (len(value) - visible)) + value[-visible:]


def principal_type_from_arn(arn: Any) -> str:
    """Return only the general AWS principal type encoded by an ARN."""
    resource = str(arn or "").partition(":")[2]
    if ":assumed-role/" in str(arn):
        return "assumed-role"
    if ":federated-user/" in str(arn):
        return "federated"
    if ":user/" in str(arn):
        return "user"
    if ":role/" in str(arn):
        return "role"
    if resource:
        return "unknown"
    return "unknown"


def anonymous_identity(identity: dict[str, Any]) -> dict[str, Any]:
    """Remove full AWS identity values from a normalized STS response."""
    return {
        "identity_available": True,
        "account_id_masked": mask_account_id(identity.get("account_id")),
        "principal_type": principal_type_from_arn(identity.get("arn")),
    }
