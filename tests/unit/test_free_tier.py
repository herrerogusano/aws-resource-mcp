"""Tests for bounded, no-cost Free Tier normalization."""

from unittest.mock import Mock

from botocore.exceptions import ClientError

from aws_resource_mcp.economics.free_tier import collect_free_tier
from aws_resource_mcp.tools.review_free_tier import revisar_free_tier


def _session(client: Mock) -> Mock:
    session = Mock()
    session.client.return_value = client
    return session


def test_free_tier_normalizes_plan_offers_and_thresholds() -> None:
    client = Mock()
    client.get_account_plan_state.return_value = {
        "accountId": "111122223333",
        "accountPlanType": "FREE",
        "accountPlanStatus": "ACTIVE",
        "accountPlanRemainingCredits": 42.0,
    }
    client.get_free_tier_usage.return_value = {
        "freeTierUsages": [
            {
                "service": "Amazon EC2",
                "actualUsageAmount": 650,
                "forecastedUsageAmount": 760,
                "limit": 750,
                "unit": "Hrs",
                "freeTierType": "Always Free",
            }
        ]
    }

    result = collect_free_tier(session=_session(client))

    assert result["free_tier_status"] == "approaching_limit"
    assert result["account_plan"]["free_tier_status"] == "credit_available"
    assert "accountId" not in str(result)
    assert result["coverage"]["billable_operations_executed"] == 0
    assert result["coverage"]["operations_executed"] == [
        "freetier:GetAccountPlanState",
        "freetier:GetFreeTierUsage",
    ]


def test_free_tier_paginates_only_to_explicit_limit() -> None:
    client = Mock()
    client.get_account_plan_state.return_value = {}
    client.get_free_tier_usage.side_effect = [
        {"freeTierUsages": [], "nextToken": "opaque"},
        {"freeTierUsages": []},
    ]

    one = collect_free_tier(max_pages=1, session=_session(client))
    assert one["coverage"]["truncated"] is True
    assert client.get_free_tier_usage.call_count == 1

    client.reset_mock()
    client.get_account_plan_state.return_value = {}
    client.get_free_tier_usage.side_effect = [
        {"freeTierUsages": [], "nextToken": "opaque"},
        {"freeTierUsages": []},
    ]
    two = collect_free_tier(max_pages=2, session=_session(client))
    assert two["coverage"]["truncated"] is False
    assert client.get_free_tier_usage.call_count == 2


def test_free_tier_permission_error_is_structured_and_safe() -> None:
    client = Mock()
    denied = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "sensitive account data"}},
        "GetFreeTierUsage",
    )
    client.get_account_plan_state.side_effect = denied
    client.get_free_tier_usage.side_effect = denied

    result = collect_free_tier(session=_session(client))

    assert result["free_tier_status"] == "permission_denied"
    assert "sensitive account data" not in str(result)
    assert result["coverage"]["billable_operations_executed"] == 0


def test_free_tier_tool_rejects_invalid_input_before_aws() -> None:
    result = revisar_free_tier(max_pages=0)

    assert result["status"] == "error"
    assert result["coverage"]["operations_executed"] == []
