"""MCP tool for local potential-cost prioritization."""

from datetime import datetime, timedelta, timezone
from typing import Any

from aws_resource_mcp.economics.risk import analyze_resources, merge_activity
from aws_resource_mcp.models import remove_sensitive_fields
from aws_resource_mcp.tools.analyze_activity import analizar_actividad_recursos
from aws_resource_mcp.tools.list_resources import listar_recursos_aws
from aws_resource_mcp.tools.query_costs import consultar_costes_aws
from aws_resource_mcp.tools.review_free_tier import revisar_free_tier


def analizar_riesgo_costes(
    services: list[str] | None = None,
    regions: list[str] | None = None,
    resource_ids: list[str] | None = None,
    include_activity: bool = True,
    include_free_tier: bool = False,
    include_actual_cost: bool = False,
    period_days: int = 30,
    max_resources: int = 100,
) -> dict[str, Any]:
    """Prioritize potential AWS cost risk without treating it as actual spend.

    The analysis uses the common inventory model and its cost indicators.
    Optional activity is merged through the existing uniform activity tool.
    Free Tier data uses the officially free API. ``include_actual_cost=True``
    only prepares a separate Cost Explorer consent request; it does not grant
    consent or execute a potentially billable operation. Recommendations are
    informational and no AWS resource is changed.
    """
    try:
        if any(
            not isinstance(flag, bool)
            for flag in (include_activity, include_free_tier, include_actual_cost)
        ):
            raise ValueError("include flags must be booleans")
        if type(period_days) is not int or not 1 <= period_days <= 366:
            raise ValueError("period_days must be an integer between 1 and 366")
        if type(max_resources) is not int or not 1 <= max_resources <= 500:
            raise ValueError("max_resources must be an integer between 1 and 500")
        if regions is not None and (
            not regions
            or any(not isinstance(item, str) or not item.strip() for item in regions)
        ):
            raise ValueError("regions must contain at least one string")
    except ValueError as error:
        return {
            "status": "error",
            "summary": {
                "resources_analyzed": 0,
                "billable_operations_executed": 0,
                "potentially_billable_operations_executed": 0,
                "potentially_billable_unique_operations_executed": 0,
                "potentially_billable_requests_executed": 0,
            },
            "resources": [],
            "errors": [
                {
                    "service": "input",
                    "error_type": "invalid_cost_risk_parameters",
                    "message": str(error),
                }
            ],
        }

    inventory = listar_recursos_aws(
        region=(regions or [None])[0],
        services=services,
        all_regions=regions is None or len(regions) > 1,
        include_details=True,
        include_cost_indicators=True,
        include_account_id=False,
    )
    resources = list(inventory.get("all_resources", []))[:max_resources]
    activity_result: dict[str, Any] | None = None
    if include_activity and resources:
        activity_result = analizar_actividad_recursos(
            services=services,
            regions=regions,
            resource_ids=resource_ids,
            max_resources=max_resources,
        )
        merge_activity(resources, list(activity_result.get("resources", [])))
    if resource_ids:
        wanted = set(resource_ids)
        resources = [
            resource
            for resource in resources
            if wanted
            & {
                str(resource.get("id") or ""),
                str(resource.get("arn") or ""),
                str(resource.get("name") or ""),
            }
        ]
    analyzed = analyze_resources(resources)
    free_tier = revisar_free_tier(services=services) if include_free_tier else None
    cost_consent = None
    if include_actual_cost:
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=period_days)
        cost_consent = consultar_costes_aws(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            services=services,
            regions=regions,
        )
    analyzed["summary"].update(
        {
            "inventory_status": inventory.get("status"),
            "activity_included": include_activity,
            "free_tier_included": include_free_tier,
            "actual_cost_status": (
                cost_consent.get("actual_cost_status")
                if cost_consent
                else "not_checked"
            ),
            "billable_operations_executed": 0,
            "potentially_billable_operations_executed": 0,
            "potentially_billable_unique_operations_executed": 0,
            "potentially_billable_requests_executed": 0,
        }
    )
    result = {
        "status": (
            "partial"
            if inventory.get("summary", {}).get("partial")
            or (activity_result and activity_result.get("status") != "ok")
            else "ok"
        ),
        **analyzed,
        "free_tier": free_tier,
        "actual_cost": cost_consent,
        "coverage": {
            "inventory": inventory.get("coverage", {}),
            "activity": activity_result.get("coverage", {})
            if activity_result
            else {"status": "not_requested"},
            "cost_explorer_executed": False,
        },
        "limitations": [
            "Potential-cost risk is not actual billed cost.",
            "Free Tier eligibility is account-level and does not prove that a resource is free.",
            "Recommendations require human validation and are never executed.",
        ],
        "errors": [
            *inventory.get("errors", []),
            *(activity_result.get("errors", []) if activity_result else []),
        ],
    }
    return remove_sensitive_fields(result)
