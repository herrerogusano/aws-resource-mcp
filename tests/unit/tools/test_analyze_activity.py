"""Tests for the MCP-facing activity analysis tool."""

import json
from unittest.mock import Mock, patch

import pytest

from aws_resource_mcp.tools.analyze_activity import analizar_actividad_recursos


def response() -> dict:
    return {
        "status": "partial",
        "summary": {
            "resources_analyzed": 1,
            "lookback_days": 90,
            "paid_operations_executed": 0,
        },
        "resources": [{"id": "i-test", "activity": {"status": "unknown"}}],
        "coverage": {
            "cloudtrail_regions_checked": ["eu-west-1"],
            "blocked_sources": ["cloudwatch"],
        },
        "errors": [],
    }


@patch("aws_resource_mcp.tools.analyze_activity.analyze_resource_activity")
def test_filters_threshold_period_and_limits_are_forwarded(analyze: Mock) -> None:
    analyze.return_value = response()
    result = analizar_actividad_recursos(
        services=["EC2"],
        regions=["EU-WEST-1"],
        resource_ids=["i-test"],
        inactive_days=45,
        lookback_days=60,
        include_administrative_events=False,
        include_paid_sources=True,
        max_resources=10,
        max_regions=2,
        max_events_per_resource=5,
        timeout_seconds=10,
    )
    assert result["status"] == "partial"
    analyze.assert_called_once_with(
        services=["ec2"],
        regions=["eu-west-1"],
        resource_ids=["i-test"],
        inactive_days=45,
        lookback_days=60,
        include_administrative_events=False,
        include_paid_sources=True,
        max_resources=10,
        max_regions=2,
        max_events_per_resource=5,
        timeout_seconds=10.0,
    )


@pytest.mark.parametrize(
    "arguments",
    [
        {"services": []},
        {"regions": []},
        {"resource_ids": []},
        {"inactive_days": 0},
        {"lookback_days": 91},
        {"include_paid_sources": "yes"},
        {"max_resources": 0},
        {"max_regions": 11},
        {"max_events_per_resource": 51},
        {"timeout_seconds": 0},
    ],
)
@patch("aws_resource_mcp.tools.analyze_activity.analyze_resource_activity")
def test_invalid_inputs_are_rejected_before_aws(analyze: Mock, arguments: dict) -> None:
    result = analizar_actividad_recursos(**arguments)
    assert result["status"] == "error"
    assert result["errors"][0]["error_type"] == "invalid_activity_parameters"
    assert result["summary"]["paid_operations_executed"] == 0
    analyze.assert_not_called()


@patch("aws_resource_mcp.tools.analyze_activity.analyze_resource_activity")
def test_response_is_json_and_sensitive_fields_are_removed(analyze: Mock) -> None:
    unsafe = response()
    unsafe["resources"][0]["credentials"] = {
        "aws_access_key_id": "AKIA_NOT_REAL",
        "session_token": "not-real",
    }
    analyze.return_value = unsafe
    serialized = json.dumps(analizar_actividad_recursos()).lower()
    assert "credentials" not in serialized
    assert "aws_access_key_id" not in serialized
    assert "session_token" not in serialized
