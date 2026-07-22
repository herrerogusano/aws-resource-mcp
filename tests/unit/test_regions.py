"""Tests for account Region discovery."""

from unittest.mock import Mock

from botocore.exceptions import ClientError
import pytest

from aws_resource_mcp.aws.regions import enabled_region_names, list_aws_regions


def test_regions_normalize_status_and_sort_enabled_regions() -> None:
    client = Mock()
    client.describe_regions.return_value = {
        "Regions": [
            {"RegionName": "us-west-1", "OptInStatus": "not-opted-in"},
            {"RegionName": "eu-west-1", "OptInStatus": "opt-in-not-required"},
            {"RegionName": "ap-east-1", "OptInStatus": "opted-in"},
        ]
    }
    session = Mock()
    session.client.return_value = client

    regions = list_aws_regions(session)

    assert [item["name"] for item in regions] == [
        "ap-east-1",
        "eu-west-1",
        "us-west-1",
    ]
    assert enabled_region_names(regions) == ["ap-east-1", "eu-west-1"]
    assert regions[2]["enabled"] is False
    client.describe_regions.assert_called_once_with(AllRegions=True)


def test_region_permission_error_is_not_hidden() -> None:
    client = Mock()
    client.describe_regions.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "denied"}},
        "DescribeRegions",
    )
    session = Mock()
    session.client.return_value = client

    with pytest.raises(ClientError):
        list_aws_regions(session)
