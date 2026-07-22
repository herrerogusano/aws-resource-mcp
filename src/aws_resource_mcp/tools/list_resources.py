"""MCP presentation layer for the read-only AWS inventory."""

from typing import Any

from aws_resource_mcp.aws.errors import AWSInventoryGlobalError
from aws_resource_mcp.aws.inventory import (
    SUPPORTED_INVENTORY_SERVICES,
    collect_aws_inventory,
)
from aws_resource_mcp.config import DEFAULT_AWS_REGION

SENSITIVE_FIELD_NAMES = frozenset(
    {
        "aws_access_key_id",
        "aws_secret_access_key",
        "session_token",
        "credentials",
    }
)


def _error_response(
    region: str,
    error_type: str,
    message: str,
    *,
    service: str = "input",
) -> dict[str, Any]:
    return {
        "status": "error",
        "summary": {"region": region},
        "resources": {},
        "errors": [
            {"service": service, "type": error_type, "message": message}
        ],
    }


def _normalize_services(services: list[str] | None) -> list[str]:
    if services is None:
        return sorted(SUPPORTED_INVENTORY_SERVICES)
    if not services:
        raise ValueError("services must contain at least one supported service")
    if any(not isinstance(service, str) for service in services):
        raise ValueError("every service name must be a string")

    normalized = list(dict.fromkeys(service.strip().lower() for service in services))
    if any(not service for service in normalized):
        raise ValueError("service names must not be empty")

    unknown = set(normalized) - SUPPORTED_INVENTORY_SERVICES
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(
            f"Unsupported services: {names}. Supported services: lambda, s3"
        )
    return normalized


def _remove_sensitive_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _remove_sensitive_fields(item)
            for key, item in value.items()
            if key.lower() not in SENSITIVE_FIELD_NAMES
        }
    if isinstance(value, list):
        return [_remove_sensitive_fields(item) for item in value]
    return value


def listar_recursos_aws(
    region: str = DEFAULT_AWS_REGION,
    services: list[str] | None = None,
    include_account_id: bool = True,
) -> dict[str, Any]:
    """List AWS resources through the locally available credentials, read-only.

    Use this tool to inspect deployed resources or list Lambda functions and S3
    buckets. Filter with ``services`` using ``lambda`` and/or ``s3``; omitted
    services queries both. Results may be partial when one service is not
    accessible. Set ``include_account_id`` to false to anonymize the account.
    This tool never modifies resources and does not calculate costs or Free Tier.
    """
    if not isinstance(region, str):
        return _error_response(
            "",
            "invalid_region",
            "region must be a non-empty AWS region name",
        )
    normalized_region = region.strip()
    if not normalized_region:
        return _error_response(
            region,
            "invalid_region",
            "region must be a non-empty AWS region name",
        )

    try:
        requested_services = _normalize_services(services)
    except (AttributeError, ValueError) as error:
        return _error_response(
            normalized_region,
            "invalid_services",
            str(error),
        )

    try:
        inventory = collect_aws_inventory(
            normalized_region,
            services=requested_services,
        )
    except AWSInventoryGlobalError as error:
        return _error_response(
            normalized_region,
            error.error["error_type"],
            error.error["message"],
            service="aws",
        )
    except Exception:
        return _error_response(
            normalized_region,
            "inventory_error",
            "The AWS inventory could not be collected. Check the local AWS configuration.",
            service="aws",
        )

    resources = {
        service: inventory.get("services", {}).get(service, [])
        for service in requested_services
    }
    inventory_errors = [
        {
            "service": error.get("service", "aws"),
            "type": error.get("error_type", "aws_error"),
            "message": error.get("message", "An AWS query failed."),
        }
        for error in inventory.get("errors", [])
    ]
    summary: dict[str, Any] = {
        "region": normalized_region,
        "partial": bool(inventory_errors),
    }
    account_id = inventory.get("account", {}).get("account_id")
    if include_account_id and account_id:
        summary["account_id"] = account_id
    if "lambda" in resources:
        summary["lambda_count"] = len(resources["lambda"])
    if "s3" in resources:
        summary["s3_bucket_count"] = len(resources["s3"])

    return _remove_sensitive_fields(
        {
            "status": "partial" if inventory_errors else "ok",
            "summary": summary,
            "resources": resources,
            "errors": inventory_errors,
        }
    )
