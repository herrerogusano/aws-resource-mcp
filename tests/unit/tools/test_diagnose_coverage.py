"""Tests for the MCP coverage diagnostic presentation layer."""

import json
from unittest.mock import Mock, patch

from aws_resource_mcp.tools.diagnose_coverage import diagnosticar_cobertura_aws


@patch("aws_resource_mcp.tools.diagnose_coverage.collect_coverage_diagnostics")
def test_tool_passes_normalized_filters(collect: Mock) -> None:
    collect.return_value = {
        "status": "partial",
        "summary": {"billable_operations_executed": 0},
    }

    result = diagnosticar_cobertura_aws(
        services=["EC2", "ec2"],
        regions=["EU-WEST-1"],
        include_permissions=False,
        include_activity_sources=False,
        include_cost_policy=False,
    )

    assert result["status"] == "partial"
    collect.assert_called_once_with(
        services=["ec2"],
        regions=["eu-west-1"],
        include_permissions=False,
        include_activity_sources=False,
        include_cost_policy=False,
    )


def test_tool_rejects_invalid_filters_and_unknown_adapters() -> None:
    assert diagnosticar_cobertura_aws(services=[])["status"] == "error"
    result = diagnosticar_cobertura_aws(services=["unknown-service"])
    assert result["status"] == "error"
    assert result["summary"]["billable_operations_executed"] == 0


def test_tool_rejects_non_boolean_flags() -> None:
    result = diagnosticar_cobertura_aws(include_permissions="yes")  # type: ignore[arg-type]
    assert result["status"] == "error"


@patch("aws_resource_mcp.tools.diagnose_coverage.collect_coverage_diagnostics")
def test_tool_removes_sensitive_fields_and_serializes(collect: Mock) -> None:
    collect.return_value = {
        "status": "available",
        "summary": {"billable_operations_executed": 0},
        "aws_access_key_id": "AKIA_NOT_REAL",
        "nested": {"user_agent": "hidden"},
    }

    result = diagnosticar_cobertura_aws()
    serialized = json.dumps(result)

    assert "aws_access_key_id" not in serialized
    assert "user_agent" not in serialized
    assert "AKIA_NOT_REAL" not in serialized
