"""MCP tool for one-page Cost Explorer queries with exact consent."""

from copy import deepcopy
from typing import Any

from aws_resource_mcp.aws.consent import CONSENT_STORE, ConsentValidationError
from aws_resource_mcp.economics.cost_explorer import (
    build_cost_scope,
    cost_consent_payload,
    create_cost_consent,
    current_month_period,
    execute_cost_consent,
    validate_period,
)
from aws_resource_mcp.models import remove_sensitive_fields


def _error(code: str, message: str) -> dict[str, Any]:
    return {
        "status": "error",
        "actual_cost_status": "error",
        "periods": [],
        "coverage": {
            "pages_checked": 0,
            "billable_operations_executed": 0,
            "potentially_billable_operations_executed": 0,
            "potentially_billable_unique_operations_executed": 0,
            "potentially_billable_requests_executed": 0,
        },
        "errors": [{"service": "input", "error_type": code, "message": message}],
    }


def _values(values: list[str] | None, name: str) -> list[str]:
    if values is None:
        return []
    if not values or any(not isinstance(item, str) for item in values):
        raise ValueError(f"{name} must contain at least one string")
    normalized = list(dict.fromkeys(item.strip() for item in values))
    if any(not item or len(item) > 2048 for item in normalized):
        raise ValueError(f"{name} contains an invalid value")
    return normalized


def consultar_costes_aws(
    start_date: str | None = None,
    end_date: str | None = None,
    granularity: str = "MONTHLY",
    group_by_service: bool = True,
    services: list[str] | None = None,
    regions: list[str] | None = None,
    resource_ids: list[str] | None = None,
    include_resource_level: bool = False,
    include_forecast: bool = False,
    max_pages: int = 1,
    consent_request_id: str | None = None,
    consent_action: str | None = None,
) -> dict[str, Any]:
    """Prepare or execute one exact, potentially billable Cost Explorer query.

    The first call performs no AWS operation. It returns an expiring,
    single-use request that states the exact period, filters, operation,
    maximum request count, and estimated API charge. Calling again with the
    request id and ``consent_action="approve"`` executes at most one
    GetCostAndUsage page. A continuation page always needs a new consent.
    ``cancel`` performs no AWS call. Approval never authorizes another
    operation, period, filter, identity, forecast, or resource-level query.
    """
    default_start, default_end = current_month_period()
    start_date = start_date or default_start
    end_date = end_date or default_end
    try:
        if not isinstance(start_date, str) or not isinstance(end_date, str):
            raise ValueError("start_date and end_date must use YYYY-MM-DD")
        validate_period(start_date, end_date)
        if granularity not in {"MONTHLY", "DAILY"}:
            raise ValueError("granularity must be MONTHLY or DAILY")
        if not isinstance(group_by_service, bool):
            raise ValueError("group_by_service must be a boolean")
        normalized_services = _values(services, "services")
        normalized_regions = _values(regions, "regions")
        normalized_resources = _values(resource_ids, "resource_ids")
        if not isinstance(include_resource_level, bool) or not isinstance(
            include_forecast, bool
        ):
            raise ValueError("cost query include flags must be booleans")
        if include_resource_level or normalized_resources:
            raise ValueError(
                "resource-level Cost Explorer is intentionally not implemented in this phase"
            )
        if include_forecast:
            raise ValueError(
                "forecast is a separate potentially billable operation and is not implemented in this phase"
            )
        if max_pages != 1:
            raise ValueError(
                "max_pages must be 1 because every additional page requires new consent"
            )
        if consent_action not in {None, "approve", "cancel"}:
            raise ValueError("consent_action must be approve, cancel, or null")
        if bool(consent_request_id) != bool(consent_action):
            raise ValueError(
                "consent_request_id and consent_action must be provided together"
            )
    except (TypeError, ValueError) as error:
        return _error("invalid_cost_query_parameters", str(error))

    scope = build_cost_scope(
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
        group_by_service=group_by_service,
        services=normalized_services,
        regions=normalized_regions,
        resource_ids=normalized_resources,
        include_resource_level=include_resource_level,
        include_forecast=include_forecast,
        max_pages=max_pages,
    )
    if not consent_request_id:
        record = create_cost_consent(scope)
        return {
            "status": "pending_consent",
            "actual_cost_status": "pending_consent",
            "periods": [],
            "consent_request": cost_consent_payload(record),
            "coverage": {
                "pages_checked": 0,
                "billable_operations_executed": 0,
                "potentially_billable_operations_executed": 0,
                "potentially_billable_unique_operations_executed": 0,
                "potentially_billable_requests_executed": 0,
            },
            "errors": [],
        }

    try:
        record = CONSENT_STORE.get(consent_request_id)
        if record.consent_type != "cost_explorer" or record.scope != scope:
            raise ConsentValidationError(
                "consent_scope_mismatch",
                "The operation, period, granularity, or filters differ from the approved scope.",
            )
        if consent_action == "cancel":
            provisional = deepcopy(record.provisional_inventory)
            CONSENT_STORE.cancel(consent_request_id)
            CONSENT_STORE.destroy_payload(consent_request_id)
            return {
                **provisional,
                "status": "consent_cancelled",
                "actual_cost_status": "not_checked",
                "coverage": {
                    "pages_checked": 0,
                    "billable_operations_executed": 0,
                    "potentially_billable_operations_executed": 0,
                    "potentially_billable_unique_operations_executed": 0,
                    "potentially_billable_requests_executed": 0,
                },
                "errors": [],
            }
        return remove_sensitive_fields(execute_cost_consent(record))
    except ConsentValidationError as error:
        return _error(error.code, error.message)
    except Exception:
        return _error(
            "cost_query_failed",
            "The approved cost query could not be completed safely.",
        )
