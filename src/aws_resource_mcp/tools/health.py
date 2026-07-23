"""Fast local health check with an optional, guarded STS probe."""

from importlib.metadata import PackageNotFoundError, version
from typing import Any

from aws_resource_mcp.aws.adapters.registry import get_adapters, validate_registry
from aws_resource_mcp.aws.consent import CONSENT_STORE
from aws_resource_mcp.aws.errors import describe_aws_error
from aws_resource_mcp.aws.identity import get_aws_identity
from aws_resource_mcp.aws.operations import OperationGuard
from aws_resource_mcp.aws.session import create_aws_session
from aws_resource_mcp.config import AWSConfig
from aws_resource_mcp.diagnostics.identity import anonymous_identity
from aws_resource_mcp.security.iam_policy_generator import iam_health_metadata
from aws_resource_mcp.tools.registry import registered_tool_names


def _package_version() -> str:
    try:
        return version("aws-resource-mcp")
    except PackageNotFoundError:
        return "unknown"


def health_check(check_aws: bool = True) -> dict[str, Any]:
    """Check local server health and optionally perform one guarded STS call.

    The AWS check never runs inventory, adapters, Resource Explorer, CloudTrail,
    CloudWatch, or any regional scan. Missing credentials degrade AWS access but
    do not mean the local MCP server is down.
    """
    if not isinstance(check_aws, bool):
        return {
            "status": "error",
            "server": {
                "status": "error",
                "name": "aws-resource-mcp",
                "version": _package_version(),
                "transport": "stdio",
            },
            "aws": {"check_requested": False, "error": {"type": "invalid_input"}},
            "capabilities": {},
            "iam": {
                "policy_manifest_loaded": False,
                "generated_policies_current": False,
                "free_only_policy_generated": False,
                "consented_policy_generated": False,
                "local_validation": "not_checked",
                "policy_validation": "not_checked",
                "runtime_identity_dedicated": "unknown",
                "managed_policy_audit": "not_checked",
                "remote_validation_executed": False,
            },
            "safety": {
                "billable_operations_executed": 0,
                "potentially_billable_operations_executed": 0,
                "potentially_billable_requests_executed": 0,
                "pending_consent_count": CONSENT_STORE.pending_count(),
            },
        }
    try:
        config = AWSConfig.from_sources()
        guard = OperationGuard(config.cost_mode)
        validate_registry()
        adapters = get_adapters()
        tool_names = registered_tool_names()
    except Exception:
        return {
            "status": "error",
            "server": {
                "status": "error",
                "name": "aws-resource-mcp",
                "version": _package_version(),
                "transport": "stdio",
            },
            "aws": {
                "check_requested": check_aws,
                "credentials_detected": False,
                "sts_accessible": False,
                "identity_available": False,
                "region": None,
                "error": {
                    "type": "internal_configuration_invalid",
                    "message": "The safe local configuration could not be initialized.",
                },
            },
            "capabilities": {},
            "iam": iam_health_metadata(),
            "safety": {
                "cost_mode": "invalid",
                "billable_operations_executed": 0,
                "potentially_billable_operations_executed": 0,
                "potentially_billable_requests_executed": 0,
                "pending_consent_count": CONSENT_STORE.pending_count(),
                "write_operations_enabled": False,
            },
        }

    result: dict[str, Any] = {
        "status": "ok",
        "server": {
            "status": "ok",
            "name": "aws-resource-mcp",
            "version": _package_version(),
            "transport": "stdio",
        },
        "aws": {
            "check_requested": check_aws,
            "credentials_detected": False,
            "sts_accessible": False,
            "identity_available": False,
            "account_id_masked": None,
            "principal_type": "unknown",
            "region": config.region,
            "error": None,
        },
        "capabilities": {
            "registered_adapter_count": len(adapters),
            "registered_services": [
                adapter.metadata.service_name for adapter in adapters
            ],
            "regional_adapters": [
                adapter.metadata.service_name
                for adapter in adapters
                if adapter.metadata.scope == "regional"
            ],
            "global_adapters": [
                adapter.metadata.service_name
                for adapter in adapters
                if adapter.metadata.scope == "global"
            ],
            "registered_tool_count": len(tool_names),
            "registered_tools": tool_names,
            "inventory_consent_flow": True,
            "economic_risk_analysis": True,
            "free_tier_api": {
                "available": True,
                "cost_classification": "free",
            },
            "cost_explorer": {
                "available_with_explicit_consent": True,
                "cost_classification": "potentially_billable",
                "automatic_execution": False,
            },
        },
        "iam": iam_health_metadata(),
        "safety": {
            "cost_mode": config.cost_mode,
            "billable_operations_executed": 0,
            "potentially_billable_operations_executed": 0,
            "potentially_billable_requests_executed": 0,
            "pending_consent_count": CONSENT_STORE.pending_count(),
            "write_operations_enabled": False,
        },
    }
    if not check_aws:
        result["aws"]["status"] = "not_checked"
        return result

    try:
        session = create_aws_session(config.region, config.profile_name)
        credentials = session.get_credentials()
        if credentials is None:
            result["status"] = "degraded"
            result["aws"]["status"] = "unavailable"
            result["aws"]["error"] = {
                "type": "credentials_not_found",
                "message": "AWS credentials were not found.",
            }
            return result
        result["aws"]["credentials_detected"] = True
        identity = get_aws_identity(session, guard)
        result["aws"].update(
            {
                "status": "available",
                "sts_accessible": True,
                **anonymous_identity(identity),
            }
        )
    except Exception as exception:
        described = describe_aws_error("sts", exception)
        result["status"] = "degraded"
        result["aws"]["status"] = (
            "permission_denied"
            if described["error_type"] == "access_denied"
            else "unavailable"
        )
        result["aws"]["error"] = {
            "type": described["error_type"],
            "message": described["message"],
        }
    return result
