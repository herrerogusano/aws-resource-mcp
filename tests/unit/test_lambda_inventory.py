"""Tests for paginated Lambda inventory normalization."""

from unittest.mock import Mock

from botocore.exceptions import ClientError
import pytest

from aws_resource_mcp.aws.lambda_inventory import list_lambda_functions


def lambda_session(pages: list[dict]) -> tuple[Mock, Mock]:
    paginator = Mock()
    paginator.paginate.return_value = pages
    client = Mock()
    client.get_paginator.return_value = paginator
    session = Mock()
    session.client.return_value = client
    return session, paginator


def test_lambda_inventory_can_be_empty() -> None:
    session, _ = lambda_session([{"Functions": []}])
    assert list_lambda_functions(session, "eu-west-1") == []
    session.client.assert_called_once_with("lambda", region_name="eu-west-1")


def test_lambda_inventory_normalizes_function() -> None:
    session, _ = lambda_session(
        [
            {
                "Functions": [
                    {
                        "FunctionName": "example",
                        "FunctionArn": "arn:aws:lambda:eu-west-1:111122223333:function:example",
                        "Runtime": "python3.12",
                        "Architectures": ["arm64"],
                        "MemorySize": 256,
                        "Timeout": 15,
                        "CodeSize": 1024,
                        "LastModified": "2026-07-21T10:00:00.000+0000",
                        "PackageType": "Zip",
                    }
                ]
            }
        ]
    )
    result = list_lambda_functions(session, "eu-west-1")
    assert result[0]["name"] == "example"
    assert result[0]["architectures"] == ["arm64"]
    assert result[0]["last_modified"] == "2026-07-21T10:00:00.000+0000"


def test_lambda_inventory_reads_multiple_pages_and_missing_fields() -> None:
    session, paginator = lambda_session(
        [
            {"Functions": [{"FunctionName": "first"}]},
            {"Functions": [{"FunctionName": "second"}]},
        ]
    )
    result = list_lambda_functions(session, "eu-west-1")
    assert [item["name"] for item in result] == ["first", "second"]
    assert result[0]["runtime"] is None
    assert result[0]["architectures"] == []
    assert result[0]["last_modified"] is None
    paginator.paginate.assert_called_once_with()


def test_lambda_inventory_propagates_permission_error() -> None:
    session, paginator = lambda_session([])
    paginator.paginate.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
        "ListFunctions",
    )
    with pytest.raises(ClientError):
        list_lambda_functions(session, "eu-west-1")
