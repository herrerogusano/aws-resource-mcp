"""Tests for bounded, anonymized CloudTrail Event History lookup."""

import json
from datetime import UTC, datetime
from unittest.mock import Mock

from botocore.exceptions import ClientError

from aws_resource_mcp.activity.cloudtrail_activity import (
    lookup_events,
    normalize_cloudtrail_event,
)
from aws_resource_mcp.aws.operations import OperationGuard

NOW = datetime(2026, 7, 22, 12, tzinfo=UTC)


def event(name: str = "DescribeInstances", resource: str = "i-test") -> dict:
    return {
        "EventName": name,
        "EventSource": "ec2.amazonaws.com",
        "EventTime": NOW,
        "Resources": [{"ResourceName": resource, "ResourceType": "Instance"}],
        "Username": "must-not-escape",
        "CloudTrailEvent": json.dumps(
            {
                "readOnly": name.startswith("Describe"),
                "awsRegion": "eu-west-1",
                "sourceIPAddress": "192.0.2.20",
                "userIdentity": {"accessKeyId": "AKIA_NOT_REAL"},
                "userAgent": "secret-agent",
                "requestParameters": {"sensitive": "value"},
            }
        ),
    }


def session_with_client(client: Mock) -> Mock:
    session = Mock()
    session.client.return_value = client
    return session


def test_zero_and_one_event() -> None:
    client = Mock()
    client.lookup_events.side_effect = [{"Events": []}, {"Events": [event()]}]
    first = lookup_events(
        session_with_client(client),
        regions=["eu-west-1"],
        operation_guard=OperationGuard(),
        lookback_days=90,
        now=NOW,
    )
    second = lookup_events(
        session_with_client(client),
        regions=["eu-west-1"],
        operation_guard=OperationGuard(),
        lookback_days=90,
        now=NOW,
    )
    assert first["events"] == []
    assert second["events"][0]["event_name"] == "DescribeInstances"


def test_paginates_with_at_most_fifty_results_per_request() -> None:
    client = Mock()
    client.lookup_events.side_effect = [
        {"Events": [event("UpdateInstanceAttribute")], "NextToken": "next"},
        {"Events": [event("StartInstances")]},
    ]
    result = lookup_events(
        session_with_client(client),
        regions=["eu-west-1"],
        operation_guard=OperationGuard(),
        lookback_days=90,
        max_events=100,
        now=NOW,
    )
    assert len(result["events"]) == 2
    assert client.lookup_events.call_count == 2
    assert client.lookup_events.call_args_list[0].kwargs["MaxResults"] == 50
    assert client.lookup_events.call_args_list[1].kwargs["NextToken"] == "next"


def test_lookback_is_hard_limited_to_ninety_days() -> None:
    client = Mock()
    client.lookup_events.return_value = {"Events": []}
    result = lookup_events(
        session_with_client(client),
        regions=["eu-west-1"],
        operation_guard=OperationGuard(),
        lookback_days=500,
        now=NOW,
    )
    call = client.lookup_events.call_args.kwargs
    assert result["lookback_days"] == 90
    assert (call["EndTime"] - call["StartTime"]).days == 90


def test_checks_multiple_regions_and_reuses_the_same_lookup_shape() -> None:
    first = Mock()
    second = Mock()
    first.lookup_events.return_value = {"Events": [event()]}
    second.lookup_events.return_value = {"Events": []}
    session = Mock()
    session.client.side_effect = [first, second]
    result = lookup_events(
        session,
        regions=["eu-west-1", "eu-central-1"],
        operation_guard=OperationGuard(),
        lookback_days=30,
        now=NOW,
    )
    assert result["checked_regions"] == ["eu-west-1", "eu-central-1"]
    assert len(result["operations_executed"]) == 2


def test_event_budget_is_shared_across_regions() -> None:
    first = Mock()
    second = Mock()
    first.lookup_events.return_value = {
        "Events": [event(resource="i-one")],
        "NextToken": "more",
    }
    second.lookup_events.return_value = {"Events": [event(resource="i-two")]}
    session = Mock()
    session.client.side_effect = [first, second]

    result = lookup_events(
        session,
        regions=["eu-west-1", "us-east-1"],
        operation_guard=OperationGuard(),
        lookback_days=30,
        max_events=2,
        now=NOW,
    )

    assert result["checked_regions"] == ["eu-west-1", "us-east-1"]
    assert {item["resource_ids"][0] for item in result["events"]} == {
        "i-one",
        "i-two",
    }


def test_permission_denied_is_structured_and_other_regions_survive() -> None:
    denied = Mock()
    denied.lookup_events.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
        "LookupEvents",
    )
    successful = Mock()
    successful.lookup_events.return_value = {"Events": []}
    session = Mock()
    session.client.side_effect = [denied, successful]
    result = lookup_events(
        session,
        regions=["eu-west-1", "eu-central-1"],
        operation_guard=OperationGuard(),
        lookback_days=30,
        now=NOW,
    )
    assert result["errors"][0]["error_type"] == "activity_permission_denied"
    assert result["checked_regions"] == ["eu-central-1"]


def test_normalization_anonymizes_full_event_payload() -> None:
    normalized = normalize_cloudtrail_event(event(), "eu-west-1")
    serialized = json.dumps(normalized).lower()
    for forbidden in (
        "username",
        "sourceipaddress",
        "accesskey",
        "useragent",
        "requestparameters",
        "cloudtrailevent",
        "must-not-escape",
        "akia_not_real",
    ):
        assert forbidden not in serialized
    assert normalized["read_only"] is True
    assert normalized["activity_type"] == "administrative_activity"


def test_ambiguous_event_keeps_empty_resource_relation() -> None:
    ambiguous = event()
    ambiguous["Resources"] = []
    assert normalize_cloudtrail_event(ambiguous, "eu-west-1")["resource_ids"] == []


def test_single_resource_filter_uses_only_one_lookup_attribute() -> None:
    client = Mock()
    client.lookup_events.return_value = {"Events": []}
    lookup_events(
        session_with_client(client),
        regions=["eu-west-1"],
        operation_guard=OperationGuard(),
        lookback_days=30,
        resource_name="i-test",
        now=NOW,
    )
    assert client.lookup_events.call_args.kwargs["LookupAttributes"] == [
        {"AttributeKey": "ResourceName", "AttributeValue": "i-test"}
    ]
