"""Read-only AWS coverage diagnostics without resource inventory."""

from collections.abc import Collection
from datetime import datetime, timedelta, timezone
from typing import Any

from aws_resource_mcp.aws.adapters.registry import get_adapters, validate_registry
from aws_resource_mcp.aws.errors import describe_aws_error
from aws_resource_mcp.aws.identity import get_aws_identity
from aws_resource_mcp.aws.operations import (
    OPERATION_REGISTRY,
    OperationBlockedError,
    OperationGuard,
)
from aws_resource_mcp.aws.regions import enabled_region_names, list_aws_regions
from aws_resource_mcp.aws.resource_explorer_inventory import (
    list_resource_explorer_indexes,
    list_supported_resource_types,
)
from aws_resource_mcp.aws.session import create_aws_session
from aws_resource_mcp.config import AWSConfig
from aws_resource_mcp.diagnostics.identity import anonymous_identity
from aws_resource_mcp.security.iam_policy_generator import iam_health_metadata

MAX_DIAGNOSTIC_REGIONS = 5


def _error(
    code: str,
    service: str,
    message: str,
) -> dict[str, Any]:
    return {"code": code, "service": service, "message": message}


def _limitation(
    code: str,
    impact: str,
    *,
    requires_permission: bool = False,
    requires_write_operation: bool = False,
    potential_cost: str = "none",
) -> dict[str, Any]:
    return {
        "code": code,
        "impact": impact,
        "can_continue": True,
        "requires_permission": requires_permission,
        "requires_write_operation": requires_write_operation,
        "potential_cost": potential_cost,
        "action_executed": False,
    }


def _operation_diagnostic(
    service: str,
    operation: str,
    guard: OperationGuard,
    *,
    include_permissions: bool,
) -> dict[str, Any]:
    spec = OPERATION_REGISTRY.get((service, operation))
    generic_name = f"{service}:{operation}"
    if spec is None:
        return {
            "operation": generic_name,
            "registered": False,
            "cost_classification": "unknown",
            "access": "unknown",
            "status": "operation_not_in_policy",
            "iam_actions": [],
            "capability": "unknown",
            "policy_target": "excluded",
            "consent_required": False,
            "sensitive_data_risk": "unknown",
        }
    if spec.access == "write":
        status = "operation_excluded_write"
    elif spec.sensitive_data_risk == "high":
        status = "operation_excluded_sensitive"
    elif spec.cost_classification == "unknown":
        status = "operation_unknown"
    elif spec.policy_target == "excluded":
        status = "operation_not_in_policy"
    else:
        try:
            guard.require_allowed(service=service, operation=operation)
            status = "not_checked" if not include_permissions else "operation_available"
        except OperationBlockedError:
            status = (
                "operation_pending_consent"
                if spec.policy_target == "consented-readonly"
                else "operation_not_in_policy"
            )
    return {
        "operation": generic_name,
        "registered": True,
        "cost_classification": spec.cost_classification,
        "access": spec.access,
        "status": status,
        "iam_actions": list(spec.iam_actions),
        "capability": spec.capability,
        "policy_target": spec.policy_target,
        "consent_required": spec.consent_required,
        "sensitive_data_risk": spec.sensitive_data_risk,
    }


def _adapter_diagnostics(
    services: Collection[str] | None,
    regions: list[str],
    guard: OperationGuard,
    *,
    include_permissions: bool,
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for adapter in get_adapters(services):
        metadata = adapter.metadata
        operations = [
            _operation_diagnostic(
                service,
                operation,
                guard,
                include_permissions=include_permissions,
            )
            for service, operation in metadata.operations
        ]
        blocked = [
            item["operation"]
            for item in operations
            if item["status"] == "operation_pending_consent"
        ]
        unregistered = [
            item["operation"]
            for item in operations
            if item["status"] == "operation_not_in_policy"
        ]
        permitted = [
            item["operation"]
            for item in operations
            if item["status"] in {"operation_available", "not_checked"}
        ]
        discovery_names = {
            f"{service}:{operation}"
            for service, operation in metadata.discovery_operations
        }
        pending_discovery = [
            item["operation"]
            for item in operations
            if item["status"] == "operation_pending_consent"
            and item["operation"] in discovery_names
        ]
        if unregistered:
            status = "error"
        elif blocked and len(blocked) == len(operations):
            status = "pending_consent"
        elif blocked:
            status = "partial"
        else:
            status = "available"
        limitations: list[dict[str, Any]] = []
        if not include_permissions:
            limitations.append(
                _limitation(
                    "adapter_permissions_not_checked",
                    "IAM access for this adapter was not tested.",
                )
            )
        elif permitted:
            limitations.append(
                _limitation(
                    "adapter_permissions_declared_only",
                    "Operations are allowed by the local policy, but no inventory call was made to prove IAM access.",
                    requires_permission=True,
                )
            )
        diagnostics.append(
            {
                "service": metadata.service_name,
                "scope": metadata.scope,
                "status": status,
                "inventory_status": (
                    "operation_pending_consent"
                    if pending_discovery
                    else "operation_available"
                    if not unregistered
                    else "operation_blocked"
                ),
                "required_operation": (
                    pending_discovery[0].split(":", 1)[1]
                    if len(pending_discovery) == 1
                    else None
                ),
                "executed": False,
                "capabilities": {
                    "discovery": metadata.supports_discovery,
                    "enrichment": metadata.supports_enrichment,
                    "cost_indicators": bool(metadata.cost_indicator_types),
                    "free_activity_signals": callable(
                        getattr(adapter, "get_free_activity_signals", None)
                    ),
                },
                "required_operations": operations,
                "required_iam_actions": sorted(
                    {
                        action
                        for operation in operations
                        for action in operation["iam_actions"]
                    }
                ),
                "iam_policy_targets": sorted(
                    {operation["policy_target"] for operation in operations}
                ),
                "permitted_operations": permitted,
                "blocked_operations": blocked,
                "permission_errors": [],
                "regions_available": ["global"]
                if metadata.scope == "global"
                else regions,
                "limitations": limitations,
            }
        )
    return diagnostics


def _resource_explorer_diagnostic(
    session: Any,
    regions: list[str],
    guard: OperationGuard,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    indexes: dict[str, dict[str, Any]] = {}
    successful_regions: list[str] = []
    permission_errors: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    client_for_types: Any | None = None

    for region in regions:
        try:
            client = session.client("resource-explorer-2", region_name=region)
            found = list_resource_explorer_indexes(client, guard)
            successful_regions.append(region)
            if found and client_for_types is None:
                client_for_types = client
            for index in found:
                key = str(
                    index.get("arn") or f"{index.get('region')}:{index.get('type')}"
                )
                indexes[key] = index
        except Exception as exception:
            described = describe_aws_error("resource-explorer-2", exception)
            code = (
                "diagnostic_permission_denied"
                if described["error_type"] == "access_denied"
                else "diagnostic_source_not_configured"
            )
            diagnostic_error = _error(code, "resource_explorer", described["message"])
            errors.append(diagnostic_error)
            if described["error_type"] == "access_denied":
                permission_errors.append(diagnostic_error)

    index_values = list(indexes.values())
    aggregators = [item for item in index_values if item.get("type") == "AGGREGATOR"]
    supported_count = 0
    supported_status = "not_checked"
    if client_for_types is not None:
        try:
            supported_count = len(
                list_supported_resource_types(client_for_types, guard)
            )
            supported_status = "available"
        except Exception as exception:
            described = describe_aws_error("resource-explorer-2", exception)
            errors.append(
                _error(
                    "diagnostic_permission_denied"
                    if described["error_type"] == "access_denied"
                    else "diagnostic_partial",
                    "resource_explorer",
                    described["message"],
                )
            )
            supported_status = (
                "permission_denied"
                if described["error_type"] == "access_denied"
                else "error"
            )

    limitations: list[dict[str, Any]] = []
    if not index_values and successful_regions:
        status = "not_configured"
        limitations.append(
            _limitation(
                "resource_explorer_index_missing",
                "General discovery cannot use Resource Explorer in the checked Regions.",
                requires_write_operation=True,
                potential_cost="unknown",
            )
        )
    elif aggregators:
        status = "available"
    elif index_values:
        status = "partial"
        limitations.append(
            _limitation(
                "resource_explorer_aggregator_missing",
                "Cross-Region discovery may be incomplete because only local indexes were detected.",
                requires_write_operation=True,
                potential_cost="unknown",
            )
        )
    elif permission_errors and not successful_regions:
        status = "permission_denied"
    else:
        status = "unavailable"

    return (
        {
            "source": "resource_explorer",
            "status": status,
            "available": bool(successful_regions),
            "aggregator_index": bool(aggregators),
            "indexed_regions": sorted(
                {str(item["region"]) for item in index_values if item.get("region")}
            ),
            "checked_regions": successful_regions,
            "index_count": len(index_values),
            "supported_resource_type_count": supported_count,
            "supported_resource_types_status": supported_status,
            "multiregion_search": "available" if aggregators else "partial",
            "permission_errors": permission_errors,
            "limitations": limitations,
        },
        errors,
        limitations,
    )


def _activity_diagnostic(
    session: Any,
    regions: list[str],
    adapters: list[dict[str, Any]],
    guard: OperationGuard,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    cloudtrail_region = regions[0] if regions else None
    cloudtrail: dict[str, Any] = {
        "status": "not_checked",
        "lookback_days": 90,
        "checked_regions": [],
        "operation": "cloudtrail:LookupEvents",
    }
    if cloudtrail_region:
        try:
            client = session.client("cloudtrail", region_name=cloudtrail_region)
            now = datetime.now(timezone.utc)
            guard.call(
                client,
                service="cloudtrail",
                operation="LookupEvents",
                StartTime=now - timedelta(days=1),
                EndTime=now,
                MaxResults=1,
            )
            cloudtrail.update(
                {"status": "available", "checked_regions": [cloudtrail_region]}
            )
        except Exception as exception:
            described = describe_aws_error("cloudtrail", exception)
            status = (
                "permission_denied"
                if described["error_type"] == "access_denied"
                else "error"
            )
            cloudtrail["status"] = status
            errors.append(
                _error(
                    "diagnostic_permission_denied"
                    if status == "permission_denied"
                    else "diagnostic_partial",
                    "cloudtrail",
                    described["message"],
                )
            )

    cloudwatch_operations = [
        _operation_diagnostic(
            "cloudwatch",
            operation,
            guard,
            include_permissions=True,
        )
        for operation in ("GetMetricData", "GetMetricStatistics", "ListMetrics")
    ]
    return (
        {
            "service_api_signals": {
                "status": "available",
                "supported_adapters": [
                    item["service"]
                    for item in adapters
                    if item["capabilities"]["free_activity_signals"]
                ],
                "unsupported_adapters": [
                    item["service"]
                    for item in adapters
                    if not item["capabilities"]["free_activity_signals"]
                ],
            },
            "cloudtrail_event_history": cloudtrail,
            "cloudwatch": {
                "status": "blocked_by_cost_policy",
                "operations": cloudwatch_operations,
                "executed": False,
                "consent_required": True,
            },
        },
        errors,
    )


def _cost_policy_diagnostic(config: AWSConfig) -> dict[str, Any]:
    counts = {
        classification: sum(
            1
            for spec in OPERATION_REGISTRY.values()
            if spec.cost_classification == classification
        )
        for classification in ("free", "potentially_billable", "unknown", "write")
    }
    blocked = counts["potentially_billable"] + counts["unknown"] + counts["write"]
    return {
        "mode": config.cost_mode,
        "free_operations": counts["free"],
        "potentially_billable_operations": counts["potentially_billable"],
        "unknown_operations": counts["unknown"],
        "write_operations": counts["write"],
        "blocked_operation_count": blocked,
        "billable_operations_executed": 0,
        "potentially_billable_requests_executed": 0,
        "write_operations_enabled": False,
    }


def collect_coverage_diagnostics(
    *,
    services: Collection[str] | None = None,
    regions: Collection[str] | None = None,
    include_permissions: bool = True,
    include_activity_sources: bool = True,
    include_cost_policy: bool = True,
    session: Any | None = None,
) -> dict[str, Any]:
    """Diagnose reachable AWS coverage without running a resource inventory."""
    config = AWSConfig.from_sources()
    guard = OperationGuard(config.cost_mode)
    validate_registry()
    requested_services = None if services is None else list(dict.fromkeys(services))
    requested_regions = None if regions is None else list(dict.fromkeys(regions))
    local_adapters = _adapter_diagnostics(
        requested_services,
        [],
        guard,
        include_permissions=include_permissions,
    )
    cost_policy = _cost_policy_diagnostic(config)
    base: dict[str, Any] = {
        "status": "unavailable",
        "summary": {
            "identity_accessible": False,
            "enabled_region_count": 0,
            "registered_adapter_count": len(local_adapters),
            "fully_available_adapter_count": 0,
            "partially_available_adapter_count": 0,
            "unavailable_adapter_count": 0,
            "billable_operations_executed": 0,
        },
        "identity": {
            "status": "not_checked",
            "identity_available": False,
            "account_id_masked": None,
            "principal_type": "unknown",
        },
        "regions": {
            "status": "not_checked",
            "default_region": config.region,
            "enabled": [],
            "disabled_count": 0,
            "requested": requested_regions or [],
            "checked": [],
            "omitted": [],
            "errors": [],
        },
        "adapters": local_adapters,
        "discovery": {"status": "not_checked"},
        "enrichment": {"status": "not_checked"},
        "activity": {"status": "not_checked"},
        "economics": {
            "status": "available",
            "risk_analysis": {"status": "available", "aws_call_executed": False},
            "free_tier": {
                "status": "available",
                "operations": [
                    "freetier:GetFreeTierUsage",
                    "freetier:GetAccountPlanState",
                ],
                "cost_classification": "free",
                "executed": False,
            },
            "cost_explorer": {
                "status": "requires_explicit_consent",
                "operation": "ce:GetCostAndUsage",
                "cost_classification": "potentially_billable",
                "executed": False,
            },
        },
        "permissions": {
            "status": "not_checked" if not include_permissions else "partial",
            "checks": [],
            "errors": [],
        },
        "iam": iam_health_metadata(),
        "cost_policy": cost_policy
        if include_cost_policy
        else {"status": "not_checked"},
        "limitations": [],
        "errors": [],
    }

    try:
        aws_session = session or create_aws_session(config.region, config.profile_name)
        credentials = aws_session.get_credentials()
        if credentials is None:
            raise RuntimeError("credentials_not_found")
        identity = get_aws_identity(aws_session, guard)
    except Exception as exception:
        if str(exception) == "credentials_not_found":
            described = {
                "error_type": "credentials_not_found",
                "message": "AWS credentials were not found in the standard credential chain.",
            }
        else:
            described = describe_aws_error("sts", exception)
        code = (
            "diagnostic_credentials_unavailable"
            if described["error_type"]
            in {"credentials_not_found", "invalid_credentials", "profile_not_found"}
            else "diagnostic_sts_denied"
            if described["error_type"] == "access_denied"
            else "diagnostic_partial"
        )
        base["identity"]["status"] = (
            "permission_denied"
            if described["error_type"] == "access_denied"
            else "unavailable"
        )
        diagnostic_error = _error(code, "sts", described["message"])
        base["errors"].append(diagnostic_error)
        base["permissions"]["errors"].append(diagnostic_error)
        base["limitations"].append(
            _limitation(
                "aws_identity_unavailable",
                "AWS-dependent coverage checks were skipped; local diagnostics remain available.",
                requires_permission=True,
            )
        )
        return base

    base["identity"] = {"status": "available", **anonymous_identity(identity)}
    base["summary"]["identity_accessible"] = True
    base["permissions"]["checks"].append(
        {"operation": "sts:GetCallerIdentity", "status": "operation_available"}
    )

    region_records: list[dict[str, Any]] = []
    try:
        region_records = list_aws_regions(aws_session, config.region, guard)
        enabled = enabled_region_names(region_records)
        base["permissions"]["checks"].append(
            {"operation": "ec2:DescribeRegions", "status": "operation_available"}
        )
    except Exception as exception:
        described = describe_aws_error("ec2", exception)
        enabled = [config.region]
        diagnostic_error = _error(
            "diagnostic_permission_denied"
            if described["error_type"] == "access_denied"
            else "diagnostic_region_unavailable",
            "ec2",
            described["message"],
        )
        base["errors"].append(diagnostic_error)
        base["regions"]["errors"].append(diagnostic_error)
        base["limitations"].append(
            _limitation(
                "enabled_regions_unknown",
                "Only the default Region can be checked because enabled Regions could not be listed.",
                requires_permission=True,
            )
        )

    if requested_regions is None:
        candidates = [config.region, *enabled]
    else:
        candidates = requested_regions
    candidates = list(dict.fromkeys(candidates))
    eligible = [region for region in candidates if region in enabled]
    not_enabled = [region for region in candidates if region not in enabled]
    checked = eligible[:MAX_DIAGNOSTIC_REGIONS]
    limit_omitted = eligible[MAX_DIAGNOSTIC_REGIONS:]
    omitted = [*not_enabled, *limit_omitted]
    if not checked and requested_regions is None and config.region in enabled:
        checked = [config.region]
    if not_enabled:
        base["limitations"].append(
            _limitation(
                "diagnostic_region_unavailable",
                f"{len(not_enabled)} requested Regions are not enabled for this account.",
            )
        )
    if limit_omitted:
        base["limitations"].append(
            _limitation(
                "diagnostic_region_limit",
                f"{len(limit_omitted)} enabled Regions were not probed during this bounded diagnostic.",
            )
        )
    base["regions"] = {
        "status": (
            "available" if not base["regions"]["errors"] and not omitted else "partial"
        ),
        "default_region": config.region,
        "enabled": enabled,
        "disabled_count": sum(1 for item in region_records if not item.get("enabled")),
        "requested": requested_regions or [],
        "checked": checked,
        "omitted": omitted,
        "errors": base["regions"]["errors"],
    }
    base["summary"]["enabled_region_count"] = len(enabled)

    adapters = _adapter_diagnostics(
        requested_services,
        checked,
        guard,
        include_permissions=include_permissions,
    )
    base["adapters"] = adapters
    available_count = sum(item["status"] == "available" for item in adapters)
    partial_count = sum(item["status"] == "partial" for item in adapters)
    unavailable_count = len(adapters) - available_count - partial_count
    base["summary"].update(
        {
            "registered_adapter_count": len(adapters),
            "fully_available_adapter_count": available_count,
            "partially_available_adapter_count": partial_count,
            "unavailable_adapter_count": unavailable_count,
        }
    )

    explorer, explorer_errors, explorer_limitations = _resource_explorer_diagnostic(
        aws_session, checked, guard
    )
    base["discovery"] = {
        "status": explorer["status"],
        "resource_explorer": explorer,
        "adapter_fallback": {
            "status": "available" if adapters else "not_supported",
            "does_not_run_during_diagnostic": True,
        },
    }
    base["errors"].extend(explorer_errors)
    base["limitations"].extend(explorer_limitations)
    base["enrichment"] = {
        "status": "available" if adapters else "not_supported",
        "supported_adapters": [
            item["service"] for item in adapters if item["capabilities"]["enrichment"]
        ],
        "inventory_executed": False,
    }

    if include_activity_sources:
        activity, activity_errors = _activity_diagnostic(
            aws_session, checked, adapters, guard
        )
        base["activity"] = activity
        base["errors"].extend(activity_errors)
    else:
        base["activity"] = {"status": "not_checked"}

    if not include_permissions:
        base["permissions"]["status"] = "not_checked"
    elif base["permissions"]["errors"]:
        base["permissions"]["status"] = "partial"
    else:
        base["permissions"]["status"] = "partial"
        base["permissions"]["limitations"] = [
            "Adapter IAM permissions are declared but not exhaustively tested."
        ]

    has_partial = bool(base["errors"] or base["limitations"]) or any(
        item["status"] != "available" for item in adapters
    )
    base["status"] = "partial" if has_partial else "available"
    return base
