"""Tests for the economic-risk MCP tool."""

from unittest.mock import Mock, patch

from aws_resource_mcp.models import cost_indicator, make_resource
from aws_resource_mcp.tools.analyze_cost_risk import analizar_riesgo_costes


def _inventory_resource():
    return make_resource(
        service="ec2",
        resource_type="AWS::EC2::Instance",
        region="eu-west-1",
        source="test",
        identifier="i-test",
        cost_indicators=[cost_indicator("running_compute", "high", "Running compute")],
    )


@patch("aws_resource_mcp.tools.analyze_cost_risk.consultar_costes_aws")
@patch("aws_resource_mcp.tools.analyze_cost_risk.analizar_actividad_recursos")
@patch("aws_resource_mcp.tools.analyze_cost_risk.listar_recursos_aws")
def test_risk_reuses_inventory_activity_and_only_prepares_cost_consent(
    inventory: Mock, activity: Mock, costs: Mock
) -> None:
    item = _inventory_resource()
    inventory.return_value = {
        "status": "complete_for_requested_scope",
        "summary": {"partial": False},
        "all_resources": [item],
        "coverage": {},
        "errors": [],
    }
    activity_item = _inventory_resource()
    activity_item["activity"]["status"] = "inactive_candidate"
    activity.return_value = {
        "status": "ok",
        "resources": [activity_item],
        "coverage": {},
        "errors": [],
    }
    costs.return_value = {
        "status": "pending_consent",
        "actual_cost_status": "pending_consent",
        "coverage": {"billable_operations_executed": 0},
    }

    result = analizar_riesgo_costes(include_actual_cost=True)

    assert result["resources"][0]["economics"]["risk_level"] == "high"
    assert result["summary"]["actual_cost_status"] == "pending_consent"
    assert result["summary"]["billable_operations_executed"] == 0
    costs.assert_called_once()


@patch("aws_resource_mcp.tools.analyze_cost_risk.listar_recursos_aws")
def test_risk_filter_and_no_indicator_semantics(inventory: Mock) -> None:
    item = _inventory_resource()
    item["cost_indicators"] = []
    inventory.return_value = {
        "status": "complete_for_requested_scope",
        "summary": {"partial": False},
        "all_resources": [item],
        "coverage": {},
        "errors": [],
    }

    result = analizar_riesgo_costes(resource_ids=["i-test"], include_activity=False)

    economics = result["resources"][0]["economics"]
    assert economics["risk_level"] == "none_detected"
    assert economics["actual_cost_status"] == "not_checked"
    assert result["summary"]["potentially_billable_operations_executed"] == 0
