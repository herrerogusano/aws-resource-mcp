"""Tests for bounded AWS coverage diagnostics."""

import json
from unittest.mock import Mock

from botocore.exceptions import ClientError

from aws_resource_mcp.diagnostics.engine import collect_coverage_diagnostics


def _client_map(
    *,
    credentials: object | None = object(),
    indexes: list[dict] | None = None,
    cloudtrail_error: Exception | None = None,
) -> tuple[Mock, dict[str, Mock]]:
    session = Mock()
    session.get_credentials.return_value = credentials
    clients = {
        "sts": Mock(),
        "ec2": Mock(),
        "resource-explorer-2": Mock(),
        "cloudtrail": Mock(),
    }
    clients["sts"].get_caller_identity.return_value = {
        "Account": "111122223333",
        "Arn": "arn:aws:iam::111122223333:user/private-name",
        "UserId": "private-id",
    }
    clients["ec2"].describe_regions.return_value = {
        "Regions": [
            {"RegionName": "eu-west-1", "OptInStatus": "opt-in-not-required"},
            {"RegionName": "eu-central-1", "OptInStatus": "opted-in"},
            {"RegionName": "ap-east-1", "OptInStatus": "not-opted-in"},
        ]
    }
    clients["resource-explorer-2"].list_indexes.return_value = {
        "Indexes": indexes
        if indexes is not None
        else [
            {
                "Arn": "redacted-index",
                "Region": "eu-west-1",
                "Type": "AGGREGATOR",
            }
        ]
    }
    clients["resource-explorer-2"].list_supported_resource_types.side_effect = [
        {
            "ResourceTypes": [{"Service": "ec2", "ResourceType": "ec2:instance"}],
            "NextToken": "next",
        },
        {"ResourceTypes": [{"Service": "s3", "ResourceType": "s3:bucket"}]},
    ]
    if cloudtrail_error:
        clients["cloudtrail"].lookup_events.side_effect = cloudtrail_error
    else:
        clients["cloudtrail"].lookup_events.return_value = {"Events": []}
    session.client.side_effect = lambda service, **_: clients[service]
    return session, clients


def test_coverage_reports_identity_regions_aggregator_and_activity() -> None:
    session, clients = _client_map()

    result = collect_coverage_diagnostics(session=session)

    assert result["identity"] == {
        "status": "available",
        "identity_available": True,
        "account_id_masked": "********3333",
        "principal_type": "user",
    }
    assert result["regions"]["enabled"] == ["eu-central-1", "eu-west-1"]
    assert result["regions"]["disabled_count"] == 1
    explorer = result["discovery"]["resource_explorer"]
    assert explorer["status"] == "available"
    assert explorer["aggregator_index"] is True
    assert explorer["supported_resource_type_count"] == 2
    assert result["activity"]["cloudtrail_event_history"]["status"] == "available"
    assert result["activity"]["cloudwatch"]["status"] == "blocked_by_cost_policy"
    assert result["summary"]["billable_operations_executed"] == 0
    clients["cloudtrail"].lookup_events.assert_called_once()
    assert clients["cloudtrail"].lookup_events.call_args.kwargs["MaxResults"] == 1


def test_local_resource_explorer_index_is_partial() -> None:
    session, _ = _client_map(
        indexes=[{"Arn": "local", "Region": "eu-west-1", "Type": "LOCAL"}]
    )

    result = collect_coverage_diagnostics(
        session=session, include_activity_sources=False
    )

    explorer = result["discovery"]["resource_explorer"]
    assert explorer["status"] == "partial"
    assert explorer["aggregator_index"] is False
    assert any(
        item["code"] == "resource_explorer_aggregator_missing"
        for item in result["limitations"]
    )


def test_resource_explorer_without_indexes_is_not_configured() -> None:
    session, clients = _client_map(indexes=[])

    result = collect_coverage_diagnostics(
        session=session, include_activity_sources=False
    )

    explorer = result["discovery"]["resource_explorer"]
    assert explorer["status"] == "not_configured"
    clients["resource-explorer-2"].list_supported_resource_types.assert_not_called()


def test_resource_explorer_permission_denial_is_preserved() -> None:
    session, clients = _client_map()
    clients["resource-explorer-2"].list_indexes.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "private"}},
        "ListIndexes",
    )

    result = collect_coverage_diagnostics(
        session=session,
        regions=["eu-west-1"],
        include_activity_sources=False,
    )

    assert result["discovery"]["resource_explorer"]["status"] == "permission_denied"
    assert result["errors"][0]["code"] == "diagnostic_permission_denied"
    assert "private" not in str(result)


def test_missing_credentials_keeps_local_adapter_diagnostics() -> None:
    session, _ = _client_map(credentials=None)

    result = collect_coverage_diagnostics(session=session)

    assert result["status"] == "unavailable"
    assert result["errors"][0]["code"] == "diagnostic_credentials_unavailable"
    assert len(result["adapters"]) == 13
    session.client.assert_not_called()


def test_sts_denial_skips_dependent_checks() -> None:
    session, clients = _client_map()
    clients["sts"].get_caller_identity.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "private"}},
        "GetCallerIdentity",
    )

    result = collect_coverage_diagnostics(session=session)

    assert result["errors"][0]["code"] == "diagnostic_sts_denied"
    clients["ec2"].describe_regions.assert_not_called()
    clients["resource-explorer-2"].list_indexes.assert_not_called()


def test_disabled_requested_region_is_omitted_not_reported_empty() -> None:
    session, _ = _client_map()

    result = collect_coverage_diagnostics(
        session=session,
        regions=["ap-east-1"],
        include_activity_sources=False,
    )

    assert result["regions"]["checked"] == []
    assert result["regions"]["omitted"] == ["ap-east-1"]
    assert any(
        item["code"] == "diagnostic_region_unavailable"
        for item in result["limitations"]
    )


def test_cloudtrail_denial_does_not_remove_other_coverage() -> None:
    denied = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "private"}},
        "LookupEvents",
    )
    session, _ = _client_map(cloudtrail_error=denied)

    result = collect_coverage_diagnostics(session=session)

    assert (
        result["activity"]["cloudtrail_event_history"]["status"] == "permission_denied"
    )
    assert result["identity"]["status"] == "available"
    assert result["discovery"]["resource_explorer"]["status"] == "available"


def test_all_adapters_use_one_diagnostic_shape_and_registry() -> None:
    session, _ = _client_map()

    result = collect_coverage_diagnostics(
        session=session, include_activity_sources=False
    )

    adapters = {item["service"]: item for item in result["adapters"]}
    assert {"lambda", "s3", "ec2", "rds"} <= set(adapters)
    common_keys = set(adapters["ec2"])
    assert set(adapters["lambda"]) == common_keys
    assert set(adapters["s3"]) == common_keys
    assert set(adapters["rds"]) == common_keys
    assert adapters["s3"]["status"] == "pending_consent"
    assert adapters["lambda"]["status"] == "available"


def test_diagnostic_is_json_serializable_and_contains_no_identity_secrets() -> None:
    session, _ = _client_map()

    serialized = json.dumps(collect_coverage_diagnostics(session=session), default=str)

    assert "111122223333" not in serialized
    assert "private-name" not in serialized
    assert "private-id" not in serialized
    assert "accessKeyId" not in serialized
