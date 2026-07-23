"""MCP presentation layer for officially free AWS Free Tier reads."""

from typing import Any

from aws_resource_mcp.economics.free_tier import collect_free_tier
from aws_resource_mcp.models import remove_sensitive_fields


def revisar_free_tier(
    services: list[str] | None = None,
    include_forecast: bool = True,
    max_pages: int = 1,
) -> dict[str, Any]:
    """Review account-plan and Free Tier usage without querying billed costs.

    AWS officially documents programmatic Free Tier usage and account-plan
    monitoring at no cost. This read-only tool uses only GetFreeTierUsage and
    GetAccountPlanState. It does not call Cost Explorer, prove that a resource
    is free, or guarantee future eligibility. Usage can be estimated, delayed,
    absent after a limit is exhausted, or unavailable because of IAM.
    """
    if services is not None:
        if not services or any(not isinstance(item, str) for item in services):
            return _invalid("services must contain at least one string")
        services = list(dict.fromkeys(item.strip() for item in services))
        if any(not item or len(item) > 256 for item in services):
            return _invalid("services contains an invalid value")
    if not isinstance(include_forecast, bool):
        return _invalid("include_forecast must be a boolean")
    if type(max_pages) is not int or not 1 <= max_pages <= 5:
        return _invalid("max_pages must be an integer between 1 and 5")
    try:
        result = collect_free_tier(services=services, max_pages=max_pages)
    except Exception:
        return _invalid(
            "Free Tier data could not be queried with the local AWS configuration.",
            code="free_tier_unavailable",
        )
    if not include_forecast:
        for offer in result["offers"]:
            offer.pop("forecasted_usage", None)
    return remove_sensitive_fields(result)


def _invalid(
    message: str, *, code: str = "invalid_free_tier_parameters"
) -> dict[str, Any]:
    return {
        "status": "error",
        "free_tier_status": "error",
        "account_plan": None,
        "offers": [],
        "coverage": {
            "pages_checked": 0,
            "truncated": False,
            "operations_executed": [],
            "billable_operations_executed": 0,
            "potentially_billable_operations_executed": 0,
            "potentially_billable_unique_operations_executed": 0,
            "potentially_billable_requests_executed": 0,
        },
        "limitations": [],
        "errors": [{"service": "input", "error_type": code, "message": message}],
    }
