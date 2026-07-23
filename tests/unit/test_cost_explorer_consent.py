"""Tests for exact, ephemeral Cost Explorer consent."""

import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from aws_resource_mcp.aws.consent import CONSENT_STORE
from aws_resource_mcp.economics.cost_explorer import current_month_period
from aws_resource_mcp.tools.query_costs import consultar_costes_aws


@pytest.fixture(autouse=True)
def clear_consent_store():
    CONSENT_STORE.clear()
    yield
    CONSENT_STORE.clear()


def _approved_session(*, next_token=None) -> tuple[Mock, Mock]:
    session = Mock()
    sts = Mock()
    sts.get_caller_identity.return_value = {
        "Account": "111122223333",
        "Arn": "arn:aws:iam::111122223333:role/example",
        "UserId": "secret-id",
    }
    ce = Mock()
    response = {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2026-07-01", "End": "2026-07-23"},
                "Total": {"UnblendedCost": {"Amount": "1.25", "Unit": "USD"}},
                "Groups": [],
                "Estimated": True,
            }
        ]
    }
    if next_token:
        response["NextPageToken"] = next_token
    ce.get_cost_and_usage.return_value = response
    session.client.side_effect = lambda service, **kwargs: (
        sts if service == "sts" else ce
    )
    session.get_credentials.return_value = object()
    return session, ce


@patch("aws_resource_mcp.economics.cost_explorer.create_aws_session")
def test_first_cost_call_makes_no_aws_request(create_session: Mock) -> None:
    result = consultar_costes_aws(start_date="2026-07-01", end_date="2026-07-23")

    assert result["status"] == "pending_consent"
    assert result["coverage"]["billable_operations_executed"] == 0
    assert result["consent_request"]["estimated_max_api_cost_usd"] == "0.01"
    assert result["consent_request"]["scope"]["end_date"] == "2026-07-23"
    create_session.assert_not_called()


@patch("aws_resource_mcp.economics.cost_explorer.create_aws_session")
def test_cancel_makes_no_aws_request_and_destroys_payload(create_session: Mock) -> None:
    pending = consultar_costes_aws(start_date="2026-07-01", end_date="2026-07-23")
    request_id = pending["consent_request"]["consent_request_id"]

    result = consultar_costes_aws(
        start_date="2026-07-01",
        end_date="2026-07-23",
        consent_request_id=request_id,
        consent_action="cancel",
    )

    assert result["status"] == "consent_cancelled"
    assert result["coverage"]["billable_operations_executed"] == 0
    create_session.assert_not_called()
    assert CONSENT_STORE._records[request_id].scope == {}


def test_cost_consent_rejects_changed_scope_before_aws() -> None:
    pending = consultar_costes_aws(start_date="2026-07-01", end_date="2026-07-23")

    result = consultar_costes_aws(
        start_date="2026-07-02",
        end_date="2026-07-23",
        consent_request_id=pending["consent_request"]["consent_request_id"],
        consent_action="approve",
    )

    assert result["errors"][0]["error_type"] == "consent_scope_mismatch"
    assert result["coverage"]["billable_operations_executed"] == 0


@patch("aws_resource_mcp.economics.cost_explorer.create_aws_session")
def test_approval_executes_exactly_one_cost_request(create_session: Mock) -> None:
    session, ce = _approved_session()
    create_session.return_value = session
    pending = consultar_costes_aws(
        start_date="2026-07-01",
        end_date="2026-07-23",
        services=["Amazon Simple Storage Service"],
    )

    result = consultar_costes_aws(
        start_date="2026-07-01",
        end_date="2026-07-23",
        services=["Amazon Simple Storage Service"],
        consent_request_id=pending["consent_request"]["consent_request_id"],
        consent_action="approve",
    )

    assert result["actual_cost_status"] == "confirmed"
    assert result["total"] == "1.25"
    assert result["coverage"]["billable_operations_executed"] == 1
    assert result["coverage"]["potentially_billable_requests_executed"] == 1
    assert result["coverage"]["estimated_api_cost_usd"] == "0.01"
    ce.get_cost_and_usage.assert_called_once()
    assert (
        ce.get_cost_and_usage.call_args.kwargs["Filter"]["Dimensions"]["Key"]
        == "SERVICE"
    )
    assert "111122223333" not in str(result)
    json.dumps(result)


@patch("aws_resource_mcp.economics.cost_explorer.create_aws_session")
def test_next_page_requires_a_new_consent(create_session: Mock) -> None:
    session, ce = _approved_session(next_token="do-not-expose")
    create_session.return_value = session
    pending = consultar_costes_aws(start_date="2026-07-01", end_date="2026-07-23")

    result = consultar_costes_aws(
        start_date="2026-07-01",
        end_date="2026-07-23",
        consent_request_id=pending["consent_request"]["consent_request_id"],
        consent_action="approve",
    )

    assert result["status"] == "truncated"
    assert result["coverage"]["billable_operations_executed"] == 1
    assert "continuation_consent_request" in result
    assert "do-not-expose" not in str(result)
    assert ce.get_cost_and_usage.call_count == 1


@patch("aws_resource_mcp.economics.cost_explorer.create_aws_session")
def test_continuation_rejects_a_different_identity_before_cost_call(
    create_session: Mock,
) -> None:
    first_session, _ = _approved_session(next_token="private-token")
    second_session, second_ce = _approved_session()
    second_session.client("sts").get_caller_identity.return_value = {
        "Account": "999900001111",
        "Arn": "arn:aws:iam::999900001111:role/other",
        "UserId": "other",
    }
    create_session.side_effect = [first_session, second_session]
    pending = consultar_costes_aws(start_date="2026-07-01", end_date="2026-07-23")
    first = consultar_costes_aws(
        start_date="2026-07-01",
        end_date="2026-07-23",
        consent_request_id=pending["consent_request"]["consent_request_id"],
        consent_action="approve",
    )

    result = consultar_costes_aws(
        start_date="2026-07-01",
        end_date="2026-07-23",
        consent_request_id=first["continuation_consent_request"]["consent_request_id"],
        consent_action="approve",
    )

    assert result["errors"][0]["error_type"] == "consent_identity_mismatch"
    second_ce.get_cost_and_usage.assert_not_called()


def test_forecast_and_resource_level_are_separate_and_not_silently_authorized() -> None:
    forecast = consultar_costes_aws(
        start_date="2026-07-01", end_date="2026-07-23", include_forecast=True
    )
    resources = consultar_costes_aws(
        start_date="2026-07-01",
        end_date="2026-07-23",
        include_resource_level=True,
    )

    assert forecast["status"] == resources["status"] == "error"
    assert forecast["coverage"]["billable_operations_executed"] == 0
    assert resources["coverage"]["billable_operations_executed"] == 0


def test_default_period_is_valid_on_first_day_of_month() -> None:
    start, end = current_month_period(datetime(2026, 8, 1, 12, tzinfo=timezone.utc))

    assert (start, end) == ("2026-07-01", "2026-08-01")
