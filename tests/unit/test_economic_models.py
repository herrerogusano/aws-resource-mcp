"""Tests for the common resource-economic model."""

import inspect
from typing import get_args

from aws_resource_mcp.aws.adapters.registry import get_adapters
from aws_resource_mcp.economics.models import (
    ActualCostStatus,
    EconomicRiskLevel,
    FreeTierStatus,
)
from aws_resource_mcp.economics.risk import analyze_resources, assess_resource
from aws_resource_mcp.models import cost_indicator, make_resource


def resource(*, indicators=None, activity_status="unknown"):
    item = make_resource(
        service="ec2",
        resource_type="AWS::EC2::Instance",
        region="eu-west-1",
        source="test",
        identifier="i-test",
        cost_indicators=indicators or [],
    )
    item["activity"]["status"] = activity_status
    return item


def test_no_indicator_is_not_actual_zero_cost() -> None:
    result = assess_resource(resource())

    assert result["risk_level"] == "none_detected"
    assert result["actual_cost_status"] == "not_checked"
    assert result["actual_cost"] is None
    assert result["free_tier_status"] == "unknown"


def test_all_public_economic_states_are_explicit() -> None:
    assert set(get_args(EconomicRiskLevel)) == {
        "none_detected",
        "low",
        "medium",
        "high",
        "critical",
        "unknown",
    }
    assert set(get_args(ActualCostStatus)) == {
        "confirmed",
        "zero_reported",
        "not_checked",
        "pending_consent",
        "blocked_by_cost_policy",
        "unavailable",
        "permission_denied",
        "truncated",
        "error",
    }
    assert set(get_args(FreeTierStatus)) == {
        "within_limit",
        "approaching_limit",
        "limit_exceeded",
        "credit_available",
        "credit_exhausted",
        "not_eligible",
        "not_applicable",
        "unknown",
        "unavailable",
        "permission_denied",
        "error",
    }


def test_activity_and_multiple_indicators_raise_transparent_priority() -> None:
    item = resource(
        indicators=[
            cost_indicator("running_compute", "high", "Running compute"),
            cost_indicator("public_address", "medium", "Public address"),
            cost_indicator("premium_storage", "low", "Premium storage"),
        ],
        activity_status="inactive_candidate",
    )

    result = assess_resource(item)

    assert result["risk_level"] == "critical"
    assert result["priority_score"] == 95
    assert any(
        evidence["source"] == "activity_analysis" for evidence in result["evidence"]
    )
    assert all(
        indicator["actual_cost_confirmed"] is False
        for indicator in result["indicators"]
    )


def test_all_resources_use_the_same_economic_shape_and_priority_order() -> None:
    low = resource(indicators=[cost_indicator("retained", "low", "Retained")])
    high = resource(indicators=[cost_indicator("running", "high", "Running")])
    high["id"] = "i-high"

    result = analyze_resources([low, high])

    assert result["resources"][0]["resource"]["id"] == "i-high"
    assert set(result["resources"][0]["economics"]) == set(
        result["resources"][1]["economics"]
    )
    assert result["summary"]["risk_levels"]["high"] == 1
    assert result["summary"]["risk_levels"]["low"] == 1


def test_no_adapter_has_a_direct_free_tier_or_cost_explorer_path() -> None:
    for adapter in get_adapters():
        source = inspect.getsource(adapter.__class__).lower()
        assert "get_free_tier_usage" not in source
        assert "get_cost_and_usage" not in source
        assert "economics." not in source
