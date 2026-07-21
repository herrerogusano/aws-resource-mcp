"""Tests for S3 inventory and partial location failures."""

from datetime import datetime, timezone
from unittest.mock import Mock

from botocore.exceptions import ClientError
import pytest

from aws_resource_mcp.aws.s3_inventory import list_s3_buckets


def s3_session(client: Mock) -> Mock:
    session = Mock()
    session.client.return_value = client
    return session


def test_s3_inventory_can_be_empty() -> None:
    client = Mock()
    client.list_buckets.return_value = {"Buckets": []}
    buckets, errors = list_s3_buckets(s3_session(client))
    assert buckets == []
    assert errors == []


def test_s3_inventory_normalizes_buckets_and_us_east_1() -> None:
    client = Mock()
    client.list_buckets.return_value = {
        "Buckets": [
            {"Name": "first", "CreationDate": datetime(2026, 1, 1, tzinfo=timezone.utc)},
            {"Name": "second", "CreationDate": datetime(2026, 2, 1, tzinfo=timezone.utc)},
        ]
    }
    client.get_bucket_location.side_effect = [
        {"LocationConstraint": None},
        {"LocationConstraint": "eu-west-1"},
    ]
    buckets, errors = list_s3_buckets(s3_session(client))
    assert [bucket["region"] for bucket in buckets] == ["us-east-1", "eu-west-1"]
    assert buckets[0]["creation_date"] == "2026-01-01T00:00:00+00:00"
    assert errors == []


def test_bucket_location_failure_preserves_other_buckets() -> None:
    client = Mock()
    client.list_buckets.return_value = {
        "Buckets": [{"Name": "restricted"}, {"Name": "visible"}]
    }
    client.get_bucket_location.side_effect = [
        ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "denied"}},
            "GetBucketLocation",
        ),
        {"LocationConstraint": "eu-west-1"},
    ]
    buckets, errors = list_s3_buckets(s3_session(client))
    assert len(buckets) == 2
    assert buckets[0]["region"] is None
    assert buckets[1]["region"] == "eu-west-1"
    assert errors[0]["service"] == "s3"
    assert errors[0]["error_type"] == "access_denied"


def test_list_buckets_permission_error_is_not_hidden() -> None:
    client = Mock()
    client.list_buckets.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "ListBuckets"
    )
    with pytest.raises(ClientError):
        list_s3_buckets(s3_session(client))
