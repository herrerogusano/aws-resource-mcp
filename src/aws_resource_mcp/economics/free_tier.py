"""Free AWS Free Tier API queries and conservative normalization."""

from typing import Any

from aws_resource_mcp.aws.errors import describe_aws_error
from aws_resource_mcp.aws.operations import OperationGuard
from aws_resource_mcp.aws.session import create_aws_session
from aws_resource_mcp.config import AWSConfig
from aws_resource_mcp.models import to_iso8601

FREE_TIER_ENDPOINT_REGION = "us-east-1"
FREE_TIER_PRICE_EVIDENCE = {
    "classification": "free",
    "verified_at": "2026-07-23",
    "source": "https://aws.amazon.com/about-aws/whats-new/2023/11/aws-free-tier-usage-getfreetierusage-api/",
    "statement": "AWS documents programmatic Free Tier usage access at no cost.",
}


def _offer_status(actual: float, forecast: float, limit: float) -> str:
    if limit <= 0:
        return "unknown"
    if actual >= limit:
        return "limit_exceeded"
    if actual / limit >= 0.8 or forecast >= limit:
        return "approaching_limit"
    return "within_limit"


def _normalize_offer(item: dict[str, Any]) -> dict[str, Any]:
    actual = float(item.get("actualUsageAmount") or 0)
    forecast = float(item.get("forecastedUsageAmount") or 0)
    limit = float(item.get("limit") or 0)
    return {
        "service": item.get("service"),
        "operation": item.get("operation"),
        "usage_type": item.get("usageType"),
        "region": item.get("region") or "global",
        "actual_usage": actual,
        "forecasted_usage": forecast,
        "limit": limit,
        "unit": item.get("unit"),
        "offer_type": item.get("freeTierType"),
        "status": _offer_status(actual, forecast, limit),
    }


def _normalize_plan(response: dict[str, Any]) -> dict[str, Any]:
    remaining = response.get("accountPlanRemainingCredits")
    plan_status = str(response.get("accountPlanStatus") or "unknown").lower()
    if plan_status == "expired":
        credit_status = "credit_exhausted"
    elif isinstance(remaining, (int, float)) and remaining > 0:
        credit_status = "credit_available"
    elif isinstance(remaining, (int, float)) and remaining <= 0:
        credit_status = "credit_exhausted"
    else:
        credit_status = "unknown"
    return {
        "plan_type": str(response.get("accountPlanType") or "unknown").lower(),
        "plan_status": plan_status,
        "remaining_credits": remaining,
        "expiration_at": to_iso8601(response.get("accountPlanExpirationDate")),
        "free_tier_status": credit_status,
    }


def collect_free_tier(
    *,
    services: list[str] | None = None,
    max_pages: int = 1,
    session: Any | None = None,
) -> dict[str, Any]:
    """Query only officially documented no-cost Free Tier read APIs."""
    config = AWSConfig.from_sources(region=FREE_TIER_ENDPOINT_REGION)
    aws_session = session or create_aws_session(
        FREE_TIER_ENDPOINT_REGION, config.profile_name
    )
    client = aws_session.client("freetier", region_name=FREE_TIER_ENDPOINT_REGION)
    guard = OperationGuard("free-only")
    errors: list[dict[str, Any]] = []
    operations: list[str] = []
    plan: dict[str, Any] | None = None
    offers: list[dict[str, Any]] = []
    next_token: str | None = None
    truncated = False

    try:
        plan = _normalize_plan(
            guard.call(
                client,
                service="freetier",
                operation="GetAccountPlanState",
                region="global",
            )
        )
        operations.append("freetier:GetAccountPlanState")
    except Exception as error:
        errors.append(describe_aws_error("freetier", error))

    parameters: dict[str, Any] = {"maxResults": 100}
    if services:
        parameters["filter"] = {
            "Dimensions": {
                "Key": "SERVICE",
                "Values": services,
                "MatchOptions": ["CONTAINS"],
            }
        }
    for page in range(max_pages):
        if next_token:
            parameters["nextToken"] = next_token
        try:
            response = guard.call(
                client,
                service="freetier",
                operation="GetFreeTierUsage",
                region="global",
                pagination=page > 0,
                **parameters,
            )
            operations.append("freetier:GetFreeTierUsage")
            offers.extend(
                _normalize_offer(item) for item in response.get("freeTierUsages", [])
            )
            next_token = response.get("nextToken")
            if not next_token:
                break
        except Exception as error:
            errors.append(describe_aws_error("freetier", error))
            break
    if next_token:
        truncated = True
    statuses = {item["status"] for item in offers}
    overall = (
        "limit_exceeded"
        if "limit_exceeded" in statuses
        else "approaching_limit"
        if "approaching_limit" in statuses
        else "within_limit"
        if offers
        else "unknown"
    )
    if errors and not offers and plan is None:
        overall = (
            "permission_denied"
            if all(error.get("error_type") == "access_denied" for error in errors)
            else "unavailable"
        )
    return {
        "status": "partial" if errors or truncated else "ok",
        "free_tier_status": overall,
        "account_plan": plan,
        "offers": offers,
        "coverage": {
            "pages_checked": min(
                max_pages,
                len([op for op in operations if op.endswith("GetFreeTierUsage")]),
            ),
            "truncated": truncated,
            "operations_executed": operations,
            "billable_operations_executed": 0,
            "potentially_billable_operations_executed": 0,
            "potentially_billable_unique_operations_executed": 0,
            "potentially_billable_requests_executed": 0,
            "pricing_evidence": FREE_TIER_PRICE_EVIDENCE,
        },
        "limitations": [
            "Free Tier data is account-level and may be estimated or updated only a few times per day.",
            "An absent or exhausted offer does not prove that the related resource has zero cost.",
            "No actual billed cost is queried.",
        ],
        "errors": errors,
    }
