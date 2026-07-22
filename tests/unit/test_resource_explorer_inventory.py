"""Tests for read-only Resource Explorer discovery."""

from datetime import datetime, timezone
from unittest.mock import Mock

from botocore.exceptions import ClientError, EndpointConnectionError

from aws_resource_mcp.aws.resource_explorer_inventory import (
    build_search_query,
    discover_with_resource_explorer,
    list_resource_explorer_indexes,
    list_supported_resource_types,
    normalize_resource_explorer_resource,
    search_resource_explorer,
)


def test_indexes_and_supported_types_are_paginated() -> None:
    client = Mock()
    client.list_indexes.side_effect = [
        {
            "Indexes": [{"Arn": "local", "Region": "eu-west-1", "Type": "LOCAL"}],
            "NextToken": "next",
        },
        {
            "Indexes": [
                {"Arn": "aggregator", "Region": "us-east-1", "Type": "AGGREGATOR"}
            ]
        },
    ]
    indexes = list_resource_explorer_indexes(client)
    assert [item["type"] for item in indexes] == ["LOCAL", "AGGREGATOR"]
    client.list_indexes.assert_any_call(NextToken="next")

    client.list_supported_resource_types.side_effect = [
        {
            "ResourceTypes": [
                {"Service": "ec2", "ResourceType": "ec2:instance"}
            ],
            "NextToken": "types-next",
        },
        {
            "ResourceTypes": [
                {"Service": "s3", "ResourceType": "s3:bucket"}
            ]
        },
    ]
    types = list_supported_resource_types(client)
    assert [item["resource_type"] for item in types] == [
        "ec2:instance",
        "s3:bucket",
    ]


def test_search_is_paginated_and_properties_are_variable() -> None:
    client = Mock()
    client.search.side_effect = [
        {
            "Resources": [
                {
                    "Arn": "arn:aws:ec2:eu-west-1:111122223333:instance/i-example",
                    "Service": "ec2",
                    "ResourceType": "ec2:instance",
                    "CfnResourceType": "AWS::EC2::Instance",
                    "Region": "eu-west-1",
                    "OwningAccountId": "111122223333",
                    "LastReportedAt": datetime(2026, 7, 1, tzinfo=timezone.utc),
                    "Properties": [
                        {"Name": "Name", "Data": "web"},
                        {"Name": "State", "Data": {"Value": "running"}},
                    ],
                }
            ],
            "NextToken": "search-next",
        },
        {"Resources": [{"Service": "iam", "Region": "global", "Properties": []}]},
    ]
    resources = search_resource_explorer(client, "view", "*")
    assert len(resources) == 2
    assert resources[0]["name"] == "web"
    assert resources[0]["resource_type"] == "AWS::EC2::Instance"
    assert resources[0]["properties"]["State"] == {"Value": "running"}
    assert resources[1]["region"] == "global"


def test_build_search_query_combines_filters() -> None:
    result = build_search_query(
        services=["ec2", "rds"],
        resource_types=["ec2:instance"],
        region="eu-west-1",
        query="web",
    )
    assert result == "web service:ec2,rds resourcetype:ec2:instance region:eu-west-1"


def configured_client(indexes: list[dict], resources: list[dict] | None = None) -> Mock:
    client = Mock()
    client.list_indexes.return_value = {"Indexes": indexes}
    client.list_supported_resource_types.return_value = {
        "ResourceTypes": [
            {"Service": "ec2", "ResourceType": "ec2:instance"},
            {"Service": "lambda", "ResourceType": "lambda:function"},
        ]
    }
    client.list_views.return_value = {"Views": ["view"]}
    client.search.return_value = {"Resources": resources or []}
    return client


def test_aggregator_index_is_preferred() -> None:
    indexes = [
        {"Arn": "local", "Region": "eu-west-1", "Type": "LOCAL"},
        {"Arn": "aggregate", "Region": "us-east-1", "Type": "AGGREGATOR"},
    ]
    probe = configured_client(indexes)
    aggregate = configured_client([])
    session = Mock()
    session.client.side_effect = lambda _, region_name: (
        aggregate if region_name == "us-east-1" else probe
    )

    result = discover_with_resource_explorer(
        session,
        ["eu-west-1", "us-east-1"],
        primary_region="eu-west-1",
    )

    assert result["coverage"]["aggregator_index"] is True
    assert result["coverage"]["supported_resource_type_count"] == 2
    aggregate.search.assert_called_once()
    probe.search.assert_not_called()


def test_local_indexes_are_all_queried_without_aggregator() -> None:
    indexes = [
        {"Arn": "one", "Region": "eu-west-1", "Type": "LOCAL"},
        {"Arn": "two", "Region": "eu-central-1", "Type": "LOCAL"},
    ]
    west = configured_client(indexes, [{"Service": "ec2", "Region": "eu-west-1"}])
    central = configured_client([], [{"Service": "rds", "Region": "eu-central-1"}])
    session = Mock()
    session.client.side_effect = lambda _, region_name: (
        central if region_name == "eu-central-1" else west
    )

    result = discover_with_resource_explorer(
        session,
        ["eu-central-1", "eu-west-1"],
        primary_region="eu-west-1",
    )

    assert len(result["resources"]) == 2
    assert result["coverage"]["aggregator_index"] is False
    assert "Only local" in result["coverage"]["limitations"][0]


def test_no_index_returns_unavailable_discovery_without_failure() -> None:
    client = configured_client([])
    session = Mock()
    session.client.return_value = client
    result = discover_with_resource_explorer(
        session, ["eu-west-1"], primary_region="eu-west-1"
    )
    assert result["resources"] == []
    assert result["coverage"]["available"] is True
    assert result["coverage"]["aggregator_index"] is False
    assert result["coverage"]["limitations"]


def test_permission_error_and_unavailable_service_are_diagnosed() -> None:
    denied = Mock()
    denied.list_indexes.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
        "ListIndexes",
    )
    session = Mock()
    session.client.return_value = denied
    result = discover_with_resource_explorer(
        session, ["eu-west-1"], primary_region="eu-west-1"
    )
    assert result["errors"][0]["error_type"] == "access_denied"
    assert result["coverage"]["permission_errors"]

    unavailable = Mock()
    unavailable.list_indexes.side_effect = EndpointConnectionError(
        endpoint_url="https://example.invalid"
    )
    session.client.return_value = unavailable
    result = discover_with_resource_explorer(
        session, ["eu-west-1"], primary_region="eu-west-1"
    )
    assert result["resources"] == []
    assert result["coverage"]["limitations"]


def test_normalizer_handles_resource_without_name_or_arn() -> None:
    result = normalize_resource_explorer_resource(
        {"Service": "service", "ResourceType": "service:type", "Properties": []}
    )
    assert result["name"] is None
    assert result["arn"] is None
