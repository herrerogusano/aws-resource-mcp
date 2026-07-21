"""Unit tests for the health-check tool."""

from aws_resource_mcp.tools.health import health_check


def test_health_check_returns_expected_status() -> None:
    result = health_check()

    assert isinstance(result, dict)
    assert result["status"] == "ok"
    assert result["server"] == "aws-resource-mcp"
    assert result["message"]
