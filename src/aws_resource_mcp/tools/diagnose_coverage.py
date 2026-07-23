"""MCP presentation layer for bounded AWS coverage diagnostics."""

import re
from typing import Any

from aws_resource_mcp.aws.adapters.registry import ADAPTERS
from aws_resource_mcp.diagnostics.engine import collect_coverage_diagnostics
from aws_resource_mcp.models import remove_sensitive_fields


def _invalid(message: str) -> dict[str, Any]:
    return {
        "status": "error",
        "summary": {"billable_operations_executed": 0},
        "identity": {"status": "not_checked"},
        "regions": {"status": "not_checked"},
        "adapters": [],
        "discovery": {"status": "not_checked"},
        "enrichment": {"status": "not_checked"},
        "activity": {"status": "not_checked"},
        "permissions": {"status": "not_checked"},
        "cost_policy": {"billable_operations_executed": 0},
        "limitations": [],
        "errors": [
            {
                "code": "diagnostic_partial",
                "service": "input",
                "message": message,
            }
        ],
    }


def _normalized_values(
    values: list[str] | None,
    *,
    name: str,
) -> list[str] | None:
    if values is None:
        return None
    if not values or any(not isinstance(value, str) for value in values):
        raise ValueError(f"{name} must contain at least one string")
    normalized = list(dict.fromkeys(value.strip().lower() for value in values))
    if any(not value or not re.fullmatch(r"[a-z0-9-]+", value) for value in normalized):
        raise ValueError(f"{name} contains an invalid value")
    return normalized


def diagnosticar_cobertura_aws(
    services: list[str] | None = None,
    regions: list[str] | None = None,
    include_permissions: bool = True,
    include_activity_sources: bool = True,
    include_cost_policy: bool = True,
) -> dict[str, Any]:
    """Explain which AWS coverage is reachable and why it may be partial.

    This read-only diagnostic checks STS, enabled Regions, existing Resource
    Explorer indexes, the shared adapter registry, free activity sources, and
    the central cost policy. It does not inventory resources, create indexes,
    change IAM, enable Regions, or run CloudWatch. Adapter permissions are
    reported conservatively because service inventory calls are not executed.
    Results may be partial and never prove that an unqueried service is empty.
    """
    if any(
        not isinstance(value, bool)
        for value in (
            include_permissions,
            include_activity_sources,
            include_cost_policy,
        )
    ):
        return _invalid("diagnostic include flags must be booleans")
    try:
        normalized_services = _normalized_values(services, name="services")
        normalized_regions = _normalized_values(regions, name="regions")
    except ValueError as error:
        return _invalid(str(error))
    unsupported = sorted(set(normalized_services or []) - set(ADAPTERS))
    if unsupported:
        return _invalid(
            f"services contains unsupported adapters: {', '.join(unsupported)}"
        )
    try:
        result = collect_coverage_diagnostics(
            services=normalized_services,
            regions=normalized_regions,
            include_permissions=include_permissions,
            include_activity_sources=include_activity_sources,
            include_cost_policy=include_cost_policy,
        )
    except Exception:
        return _invalid(
            "The coverage diagnostic could not initialize its safe local configuration."
        )
    return remove_sensitive_fields(result)
