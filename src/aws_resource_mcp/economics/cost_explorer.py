"""Explicit, single-use consent flow for potentially billable Cost Explorer."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from aws_resource_mcp.aws.consent import (
    CONSENT_STORE,
    ConsentRecord,
    ConsentValidationError,
    identity_fingerprint,
)
from aws_resource_mcp.aws.errors import describe_aws_error
from aws_resource_mcp.aws.identity import get_aws_identity
from aws_resource_mcp.aws.operations import (
    OperationGuard,
    ScopedOperationAuthorization,
)
from aws_resource_mcp.aws.session import create_aws_session
from aws_resource_mcp.config import AWSConfig

CE_ENDPOINT_REGION = "us-east-1"
PRIMARY_VIEW_PRICE_USD_PER_REQUEST = Decimal("0.01")
CE_PRICE_EVIDENCE = {
    "classification": "potentially_billable",
    "verified_at": "2026-07-23",
    "source": "https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/",
    "primary_billing_view_usd_per_request": "0.01",
}


def build_cost_scope(
    *,
    start_date: str,
    end_date: str,
    granularity: str,
    group_by_service: bool,
    services: list[str] | None,
    regions: list[str] | None,
    resource_ids: list[str] | None,
    include_resource_level: bool,
    include_forecast: bool,
    max_pages: int,
) -> dict[str, Any]:
    """Build an exact serializable scope without contacting AWS."""
    return {
        "start_date": start_date,
        "end_date": end_date,
        "granularity": granularity,
        "group_by_service": group_by_service,
        "services": list(services or []),
        "regions": list(regions or []),
        "resource_ids": list(resource_ids or []),
        "include_resource_level": include_resource_level,
        "include_forecast": include_forecast,
        "max_pages": max_pages,
    }


def _pending_operation(
    scope: dict[str, Any], *, continuation: bool = False
) -> dict[str, Any]:
    return {
        "service": "ce",
        "operation": "GetCostAndUsage",
        "adapter": "cost_explorer",
        "regions": ["global"],
        "estimated_max_requests": 1,
        "continuation": continuation,
        "purpose": (
            "Retrieve one additional page of actual AWS cost data"
            if continuation
            else "Retrieve actual AWS cost data for the exact requested period and filters"
        ),
        "executed": False,
    }


def create_cost_consent(scope: dict[str, Any]) -> ConsentRecord:
    """Create a draft that performs no AWS call and stores no AWS identity."""
    return CONSENT_STORE.create(
        identity_hash="unbound",
        consent_type="cost_explorer",
        scope=scope,
        pending_operations=[_pending_operation(scope)],
        provisional_inventory={
            "status": "pending_consent",
            "actual_cost_status": "pending_consent",
            "period": {
                "start": scope["start_date"],
                "end": scope["end_date"],
                "end_exclusive": True,
            },
            "results": [],
        },
    )


def cost_consent_payload(record: ConsentRecord) -> dict[str, Any]:
    """Explain the exact bounded charge before any AWS request is made."""
    return {
        "consent_request_id": record.request_id,
        "purpose": record.pending_operations[0]["purpose"],
        "operation": "ce:GetCostAndUsage",
        "scope": deepcopy(record.scope),
        "estimated_max_requests": 1,
        "estimated_max_api_cost_usd": "0.01",
        "pricing_basis": "Primary billing view; custom billing views are not used.",
        "single_use": True,
        "expires_at": record.expires_at.isoformat(),
        "executed": False,
        "requires_explicit_confirmation": True,
        "pricing_evidence": CE_PRICE_EVIDENCE,
    }


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except InvalidOperation:
        return Decimal("0")


def _normalize_cost_page(response: dict[str, Any]) -> dict[str, Any]:
    periods: list[dict[str, Any]] = []
    grand_total = Decimal("0")
    currency = "USD"
    for item in response.get("ResultsByTime", []):
        groups = []
        for group in item.get("Groups", []):
            metric = group.get("Metrics", {}).get("UnblendedCost", {})
            amount = _decimal(metric.get("Amount"))
            currency = str(metric.get("Unit") or currency)
            grand_total += amount
            groups.append(
                {
                    "service": (group.get("Keys") or [None])[0],
                    "amount": str(amount),
                    "currency": currency,
                }
            )
        total_metric = item.get("Total", {}).get("UnblendedCost", {})
        if not groups:
            amount = _decimal(total_metric.get("Amount"))
            currency = str(total_metric.get("Unit") or currency)
            grand_total += amount
        periods.append(
            {
                "start": item.get("TimePeriod", {}).get("Start"),
                "end": item.get("TimePeriod", {}).get("End"),
                "estimated": bool(item.get("Estimated")),
                "services": groups,
                "total": str(
                    sum((_decimal(group["amount"]) for group in groups), Decimal("0"))
                    if groups
                    else _decimal(total_metric.get("Amount"))
                ),
                "currency": currency,
            }
        )
    return {
        "periods": periods,
        "total": str(grand_total),
        "currency": currency,
        "actual_cost_status": "zero_reported" if grand_total == 0 else "confirmed",
    }


def _parameters(
    scope: dict[str, Any], continuation_token: str | None
) -> dict[str, Any]:
    parameters: dict[str, Any] = {
        "TimePeriod": {"Start": scope["start_date"], "End": scope["end_date"]},
        "Granularity": scope["granularity"],
        "Metrics": ["UnblendedCost"],
    }
    if scope["group_by_service"]:
        parameters["GroupBy"] = [{"Type": "DIMENSION", "Key": "SERVICE"}]
    filters = []
    if scope["services"]:
        filters.append({"Dimensions": {"Key": "SERVICE", "Values": scope["services"]}})
    if scope["regions"]:
        filters.append({"Dimensions": {"Key": "REGION", "Values": scope["regions"]}})
    if len(filters) == 1:
        parameters["Filter"] = filters[0]
    elif filters:
        parameters["Filter"] = {"And": filters}
    if continuation_token:
        parameters["NextPageToken"] = continuation_token
    return parameters


def execute_cost_consent(
    record: ConsentRecord,
    *,
    session: Any | None = None,
) -> dict[str, Any]:
    """Execute one approved CE request and consume its grant before the SDK call."""
    if record.consent_type != "cost_explorer":
        raise ConsentValidationError(
            "consent_type_mismatch", "The consent request is not for Cost Explorer."
        )
    config = AWSConfig.from_sources(region=CE_ENDPOINT_REGION)
    aws_session = session or create_aws_session(CE_ENDPOINT_REGION, config.profile_name)
    identity = get_aws_identity(aws_session, OperationGuard("free-only"))
    CONSENT_STORE.bind_identity(record.request_id, identity_fingerprint(identity))
    continuation_token = record.continuation_tokens.get("ce")
    authorization = ScopedOperationAuthorization(
        allowed_operations=frozenset({("ce", "GetCostAndUsage")}),
        allowed_regions=frozenset({"global"}),
        max_requests=1,
        max_additional_pages=1 if continuation_token else 0,
    )
    guard = OperationGuard("free-only", scoped_authorization=authorization)
    CONSENT_STORE.consume(record.request_id)
    try:
        response = guard.call(
            aws_session.client("ce", region_name=CE_ENDPOINT_REGION),
            service="ce",
            operation="GetCostAndUsage",
            region="global",
            pagination=bool(continuation_token),
            **_parameters(record.scope, continuation_token),
        )
        normalized = _normalize_cost_page(response)
        next_token = response.get("NextPageToken")
        next_record = None
        if next_token:
            next_record = CONSENT_STORE.create(
                identity_hash=record.identity_hash,
                consent_type="cost_explorer",
                scope=record.scope,
                pending_operations=[
                    _pending_operation(record.scope, continuation=True)
                ],
                provisional_inventory={
                    "status": "truncated",
                    **normalized,
                },
                continuation_tokens={"ce": next_token},
            )
        CONSENT_STORE.record_execution(record.request_id, authorization)
        result = {
            "status": "truncated" if next_token else "ok",
            **normalized,
            "period": {
                "start": record.scope["start_date"],
                "end": record.scope["end_date"],
                "end_exclusive": True,
            },
            "coverage": {
                "pages_checked": 1,
                "truncated": bool(next_token),
                "operation": "ce:GetCostAndUsage",
                "potentially_billable_unique_operations_executed": len(
                    authorization.operations_executed
                ),
                "potentially_billable_operations_executed": len(
                    authorization.operations_executed
                ),
                "potentially_billable_requests_executed": (
                    authorization.requests_executed
                ),
                "billable_operations_executed": len(authorization.operations_executed),
                "estimated_api_cost_usd": str(
                    PRIMARY_VIEW_PRICE_USD_PER_REQUEST * authorization.requests_executed
                ),
                "pricing_evidence": CE_PRICE_EVIDENCE,
            },
            "limitations": [
                "Costs are grouped only by service when requested.",
                "Linked-account identifiers, billing view ARNs, and resource-level data are not returned.",
                "The period end date is exclusive.",
            ],
            "errors": [],
        }
        if next_record:
            result["continuation_consent_request"] = cost_consent_payload(next_record)
        return result
    except Exception as error:
        CONSENT_STORE.record_execution(record.request_id, authorization)
        described = describe_aws_error("ce", error)
        state = (
            "permission_denied"
            if described["error_type"] == "access_denied"
            else "error"
        )
        return {
            "status": state,
            "actual_cost_status": state,
            "period": {
                "start": record.scope["start_date"],
                "end": record.scope["end_date"],
                "end_exclusive": True,
            },
            "periods": [],
            "coverage": {
                "pages_checked": 1,
                "truncated": False,
                "operation": "ce:GetCostAndUsage",
                "potentially_billable_unique_operations_executed": len(
                    authorization.operations_executed
                ),
                "potentially_billable_operations_executed": len(
                    authorization.operations_executed
                ),
                "potentially_billable_requests_executed": (
                    authorization.requests_executed
                ),
                "billable_operations_executed": len(authorization.operations_executed),
                "estimated_api_cost_usd": str(
                    PRIMARY_VIEW_PRICE_USD_PER_REQUEST * authorization.requests_executed
                ),
                "pricing_evidence": CE_PRICE_EVIDENCE,
            },
            "errors": [described],
        }
    finally:
        CONSENT_STORE.destroy_payload(record.request_id)


def validate_period(start_date: str, end_date: str) -> None:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if start.isoformat() != start_date or end.isoformat() != end_date:
        raise ValueError("dates must use the exact YYYY-MM-DD format")
    if start >= end:
        raise ValueError("start_date must be earlier than the exclusive end_date")
    if (end - start).days > 366:
        raise ValueError("the requested period cannot exceed 366 days")


def current_month_period(now: datetime | None = None) -> tuple[str, str]:
    current = (now or datetime.now(timezone.utc)).date()
    if current.day == 1:
        previous_day = current - timedelta(days=1)
        return previous_day.replace(day=1).isoformat(), current.isoformat()
    return current.replace(day=1).isoformat(), current.isoformat()
