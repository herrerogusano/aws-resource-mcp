"""MCP presentation layer for the read-only AWS inventory."""

import re
from copy import deepcopy
from typing import Any

from aws_resource_mcp.activity.engine import attach_free_activity_summaries
from aws_resource_mcp.aws.consent import (
    CONSENT_STORE,
    ConsentRecord,
    ConsentValidationError,
    consent_request_payload,
    identity_fingerprint,
)
from aws_resource_mcp.aws.errors import AWSInventoryGlobalError
from aws_resource_mcp.aws.inventory import (
    collect_general_aws_inventory,
    complete_inventory_with_consent,
)
from aws_resource_mcp.config import DEFAULT_AWS_REGION
from aws_resource_mcp.models import remove_sensitive_fields


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
        "all_resources": [],
        "resources_by_service": {},
        "coverage": {"status": "unavailable"},
        "errors": [{"service": service, "type": error_type, "message": message}],
    }


def _normalize_services(services: list[str] | None) -> list[str]:
    if services is None:
        return []
    if not services:
        raise ValueError("services must contain at least one supported service")
    if any(not isinstance(service, str) for service in services):
        raise ValueError("every service name must be a string")

    normalized = list(dict.fromkeys(service.strip().lower() for service in services))
    if any(not service for service in normalized):
        raise ValueError("service names must not be empty")
    if any(not re.fullmatch(r"[a-z0-9-]+", service) for service in normalized):
        raise ValueError("service names may contain only letters, numbers, and hyphens")
    return normalized


def _normalize_resource_types(resource_types: list[str] | None) -> list[str]:
    if resource_types is None:
        return []
    if not resource_types:
        raise ValueError("resource_types must contain at least one resource type")
    if any(not isinstance(resource_type, str) for resource_type in resource_types):
        raise ValueError("every resource type must be a string")
    normalized = list(
        dict.fromkeys(resource_type.strip() for resource_type in resource_types)
    )
    if any(
        not resource_type or not re.fullmatch(r"[A-Za-z0-9:_-]+", resource_type)
        for resource_type in normalized
    ):
        raise ValueError("resource types contain an invalid value")
    return normalized


def _remove_account_ids(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _remove_account_ids(item)
            for key, item in value.items()
            if key.lower() != "account_id"
        }
    if isinstance(value, list):
        return [_remove_account_ids(item) for item in value]
    return value


def _inventory_status(inventory: dict[str, Any], pending: list[dict[str, Any]]) -> str:
    adapter_coverage = inventory.get("coverage", {}).get("adapters", {})
    if adapter_coverage.get("timed_out"):
        return "partial_timeout"
    if adapter_coverage.get("permission_denied"):
        return "partial_permission_denied"
    if any(
        error.get("error_type") == "access_denied"
        for error in inventory.get("errors", [])
    ):
        return "partial_permission_denied"
    if pending:
        return "partial_pending_consent"
    if (
        adapter_coverage.get("failed")
        or inventory.get("errors")
        or inventory.get("coverage", {}).get("status") == "unavailable"
    ):
        return "partial_unavailable"
    return "complete_for_requested_scope"


def _scope_for_request(
    *,
    inventory: dict[str, Any],
    region: str | None,
    services: list[str],
    resource_types: list[str],
    query: str | None,
    all_regions: bool,
    include_details: bool,
    include_cost_indicators: bool,
    include_account_id: bool,
    include_activity_summary: bool,
) -> dict[str, Any]:
    return {
        "primary_region": inventory.get("region", region or DEFAULT_AWS_REGION),
        "regions_scanned": inventory.get("coverage", {}).get("regions_scanned", []),
        "region": region,
        "services": services,
        "resource_types": resource_types,
        "query": query,
        "all_regions": all_regions,
        "include_details": include_details,
        "include_cost_indicators": include_cost_indicators,
        "include_account_id": include_account_id,
        "include_activity_summary": include_activity_summary,
    }


def _present_inventory(
    inventory: dict[str, Any],
    *,
    status: str,
    include_account_id: bool,
    include_activity_summary: bool,
    pending_operations: list[dict[str, Any]],
    consent_record: ConsentRecord | None = None,
    authorization: Any | None = None,
) -> dict[str, Any]:
    all_resources = inventory.get("resources", [])
    if include_activity_summary:
        all_resources = attach_free_activity_summaries(all_resources)
    resources_by_service: dict[str, list[dict[str, Any]]] = {}
    for resource in all_resources:
        resources_by_service.setdefault(resource.get("service", "unknown"), []).append(
            resource
        )
    errors = [
        {
            "service": error.get("service", "aws"),
            "type": error.get("error_type", "aws_error"),
            "message": error.get("message", "An AWS query failed."),
        }
        for error in inventory.get("errors", [])
    ]
    adapter_coverage = inventory.get("coverage", {}).get("adapters", {})
    summary: dict[str, Any] = {
        "region": inventory.get("region", DEFAULT_AWS_REGION),
        "total_resources": len(all_resources),
        "resources_detected": len(all_resources),
        "services_detected": len(resources_by_service),
        "regions_scanned": len(
            inventory.get("coverage", {}).get("regions_scanned", [])
        ),
        "regions_checked": inventory.get("coverage", {}).get("regions_scanned", []),
        "services_checked": adapter_coverage.get("executed", []),
        "services_pending_consent": sorted(
            {item["adapter"] for item in pending_operations}
        ),
        "services_failed": adapter_coverage.get("failed", []),
        "potentially_billable_unique_operations_executed": (
            len(authorization.operations_executed) if authorization else 0
        ),
        "potentially_billable_requests_executed": (
            authorization.requests_executed if authorization else 0
        ),
        "consent_used": authorization is not None,
        "partial": status != "complete_for_requested_scope",
    }
    summary["potentially_billable_operations_executed"] = summary[
        "potentially_billable_unique_operations_executed"
    ]
    summary["billable_operations_executed"] = summary[
        "potentially_billable_unique_operations_executed"
    ]
    summary["adapters_executed"] = summary["services_checked"]
    summary["adapters_failed"] = summary["services_failed"]
    account_id = inventory.get("account", {}).get("account_id")
    if include_account_id and account_id:
        summary["account_id"] = account_id
    public_coverage = deepcopy(inventory.get("coverage", {"status": "unavailable"}))
    public_coverage.get("adapters", {}).pop("continuation_tokens", None)
    response: dict[str, Any] = {
        "status": status,
        "summary": summary,
        "resources": resources_by_service,
        "all_resources": all_resources,
        "resources_by_service": resources_by_service,
        "pending_operations": pending_operations,
        "coverage": public_coverage,
        "coverage_summary": {
            "status": status,
            "diagnostic_tool_available": True,
            "full_diagnostic_executed": False,
        },
        "errors": errors,
    }
    if consent_record is not None:
        response["consent_request"] = consent_request_payload(consent_record)
    sanitized = remove_sensitive_fields(response)
    return sanitized if include_account_id else _remove_account_ids(sanitized)


def listar_recursos_aws(
    region: str | None = None,
    services: list[str] | None = None,
    include_account_id: bool = True,
    resource_types: list[str] | None = None,
    query: str | None = None,
    all_regions: bool = True,
    include_details: bool = True,
    include_cost_indicators: bool = True,
    confirm_potentially_billable_operations: bool = False,
    include_activity_summary: bool = False,
    consent_request_id: str | None = None,
    consent_action: str | None = None,
    approved_services: list[str] | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Discover AWS resources through locally available credentials, read-only.

    Runs free read-only discovery first. Operations that AWS can meter as
    requests are returned as pending and are not executed. To continue, call
    this same tool with the short-lived ``consent_request_id``,
    ``consent_action="approve"``, and an explicit subset in
    ``approved_services``. Approval is single-use, identity- and scope-bound,
    request-limited, and does not authorize enrichment or extra pagination.
    ``consent_action="cancel"`` performs no AWS inventory call. The legacy
    ``confirm_potentially_billable_operations`` flag is retained for signature
    compatibility but grants no permission.

    Every service uses the same adapter pipeline and normalized resource model.
    Coverage can be partial because of pending consent, timeout, permissions,
    unavailable APIs, or Resource Explorer configuration. An empty result is
    therefore distinct from a service that was not queried. This tool never
    writes resources, lists S3 objects, reads queue messages, publishes topics,
    calculates actual costs, or guarantees that a metered request is free.
    """
    if region is not None and not isinstance(region, str):
        return _error_response(
            "",
            "invalid_region",
            "region must be null or a non-empty AWS region name",
        )
    normalized_region = region.strip() if region is not None else None
    if region is not None and not normalized_region:
        return _error_response(
            "",
            "invalid_region",
            "region must be null or a non-empty AWS region name",
        )

    try:
        requested_services = _normalize_services(services)
        requested_types = _normalize_resource_types(resource_types)
    except (AttributeError, ValueError) as error:
        return _error_response(
            normalized_region or DEFAULT_AWS_REGION,
            "invalid_filters",
            str(error),
        )
    if query is not None and not isinstance(query, str):
        return _error_response(
            normalized_region or DEFAULT_AWS_REGION,
            "invalid_query",
            "query must be null or a string",
        )
    normalized_query = query.strip() if query and query.strip() else None
    if not isinstance(all_regions, bool):
        return _error_response(
            normalized_region or DEFAULT_AWS_REGION,
            "invalid_filters",
            "all_regions must be a boolean",
        )
    if (
        not isinstance(include_details, bool)
        or not isinstance(include_cost_indicators, bool)
        or not isinstance(confirm_potentially_billable_operations, bool)
        or not isinstance(include_activity_summary, bool)
    ):
        return _error_response(
            normalized_region or DEFAULT_AWS_REGION,
            "invalid_filters",
            "detail, cost, activity-summary, and confirmation flags must be booleans",
        )
    if not isinstance(timeout_seconds, (int, float)) or not 1 <= timeout_seconds <= 120:
        return _error_response(
            normalized_region or DEFAULT_AWS_REGION,
            "invalid_timeout",
            "timeout_seconds must be a number between 1 and 120",
        )
    if consent_action not in {None, "approve", "cancel"}:
        return _error_response(
            normalized_region or DEFAULT_AWS_REGION,
            "invalid_consent_action",
            "consent_action must be approve, cancel, or null",
        )
    if bool(consent_request_id) != bool(consent_action):
        return _error_response(
            normalized_region or DEFAULT_AWS_REGION,
            "invalid_consent_request",
            "consent_request_id and consent_action must be provided together",
        )
    try:
        normalized_approved = _normalize_services(approved_services)
    except (AttributeError, ValueError) as error:
        return _error_response(
            normalized_region or DEFAULT_AWS_REGION,
            "invalid_consent_services",
            str(error),
        )

    if consent_request_id:
        try:
            record = CONSENT_STORE.get(consent_request_id)
            scope = record.scope
            explicit_scope = {
                "region": normalized_region,
                "services": requested_services,
                "resource_types": requested_types,
                "query": normalized_query,
            }
            for key, value in explicit_scope.items():
                if value not in (None, []) and value != scope.get(key):
                    raise ConsentValidationError(
                        "consent_scope_mismatch",
                        f"{key} differs from the original inventory scope.",
                    )
            include_account_id = bool(scope["include_account_id"])
            include_activity_summary = bool(scope["include_activity_summary"])
            if consent_action == "cancel":
                CONSENT_STORE.cancel(consent_request_id)
                return _present_inventory(
                    record.provisional_inventory,
                    status="consent_cancelled",
                    include_account_id=include_account_id,
                    include_activity_summary=include_activity_summary,
                    pending_operations=[],
                )
            pending_services = {item["adapter"] for item in record.pending_operations}
            if not normalized_approved:
                raise ConsentValidationError(
                    "consent_services_required",
                    "approved_services must name at least one pending service.",
                )
            if not set(normalized_approved) <= pending_services:
                raise ConsentValidationError(
                    "consent_scope_mismatch",
                    "approved_services contains a service outside the pending request.",
                )
            # Consume before any AWS continuation call so an unexpected failure
            # can never make the same grant executable twice.
            CONSENT_STORE.consume(consent_request_id)
            inventory, authorization = complete_inventory_with_consent(
                record,
                normalized_approved,
                timeout_seconds=float(timeout_seconds),
            )
            CONSENT_STORE.record_execution(consent_request_id, authorization)
            completed = set(normalized_approved)
            remaining = [
                item
                for item in record.pending_operations
                if item["adapter"] not in completed
            ]
            adapter_coverage = inventory.get("coverage", {}).get("adapters", {})
            truncations = adapter_coverage.get("truncations", [])
            truncated_adapters: set[str] = set()
            for truncation in truncations:
                original = next(
                    (
                        item
                        for item in record.pending_operations
                        if item["service"] == truncation.get("service")
                        and item["operation"] == truncation.get("operation")
                    ),
                    None,
                )
                if original is None:
                    continue
                continuation = dict(original)
                continuation.update(
                    {
                        "purpose": f"Continue {original['purpose']}",
                        "regions": [truncation.get("region", "global")],
                        "estimated_max_requests": 1,
                        "continuation": True,
                        "executed": False,
                    }
                )
                truncated_adapters.add(original["adapter"])
                remaining.append(continuation)
            remaining.extend(adapter_coverage.get("pending_operations", []))
            remaining.extend(
                item
                for item in adapter_coverage.get(
                    "enrichment_pending_operations", []
                )
                if item["adapter"] not in truncated_adapters
            )
            new_record = None
            if remaining:
                new_record = CONSENT_STORE.create(
                    identity_hash=record.identity_hash,
                    scope=scope,
                    pending_operations=remaining,
                    provisional_inventory=inventory,
                    continuation_tokens=adapter_coverage.get("continuation_tokens", {}),
                )
            return _present_inventory(
                inventory,
                status=_inventory_status(inventory, remaining),
                include_account_id=include_account_id,
                include_activity_summary=include_activity_summary,
                pending_operations=remaining,
                consent_record=new_record,
                authorization=authorization,
            )
        except ConsentValidationError as error:
            return _error_response(
                normalized_region or DEFAULT_AWS_REGION,
                error.code,
                error.message,
                service="consent",
            )
        except AWSInventoryGlobalError as error:
            return _error_response(
                normalized_region or DEFAULT_AWS_REGION,
                error.error["error_type"],
                error.error["message"],
                service="aws",
            )
        except Exception:
            return _error_response(
                normalized_region or DEFAULT_AWS_REGION,
                "inventory_error",
                "The approved inventory continuation could not be completed.",
                service="aws",
            )

    try:
        inventory = collect_general_aws_inventory(
            normalized_region,
            services=requested_services or None,
            resource_types=requested_types or None,
            query=normalized_query,
            all_regions=all_regions,
            include_details=include_details,
            include_cost_indicators=include_cost_indicators,
            confirm_potentially_billable_operations=(
                confirm_potentially_billable_operations
            ),
            timeout_seconds=float(timeout_seconds),
        )
    except AWSInventoryGlobalError as error:
        return _error_response(
            normalized_region or DEFAULT_AWS_REGION,
            error.error["error_type"],
            error.error["message"],
            service="aws",
        )
    except Exception:
        return _error_response(
            normalized_region or DEFAULT_AWS_REGION,
            "inventory_error",
            "The AWS inventory could not be collected. Check the local AWS configuration.",
            service="aws",
        )

    adapter_coverage = inventory.get("coverage", {}).get("adapters", {})
    pending = [
        *adapter_coverage.get("pending_operations", []),
        *adapter_coverage.get("enrichment_pending_operations", []),
    ]
    consent_record = None
    if pending:
        scope = _scope_for_request(
            inventory=inventory,
            region=normalized_region,
            services=requested_services,
            resource_types=requested_types,
            query=normalized_query,
            all_regions=all_regions,
            include_details=include_details,
            include_cost_indicators=include_cost_indicators,
            include_account_id=include_account_id,
            include_activity_summary=include_activity_summary,
        )
        consent_record = CONSENT_STORE.create(
            identity_hash=identity_fingerprint(inventory.get("account", {})),
            scope=scope,
            pending_operations=pending,
            provisional_inventory=inventory,
            continuation_tokens=adapter_coverage.get("continuation_tokens", {}),
        )
    return _present_inventory(
        inventory,
        status=_inventory_status(inventory, pending),
        include_account_id=include_account_id,
        include_activity_summary=include_activity_summary,
        pending_operations=pending,
        consent_record=consent_record,
    )
