"""Tests for the MCP-facing AWS resource inventory tool."""

import json
from unittest.mock import Mock, patch

import pytest

from aws_resource_mcp.aws.errors import AWSInventoryGlobalError
from aws_resource_mcp.tools.list_resources import listar_recursos_aws


def inventory(
    *,
    lambdas: list[dict] | None = None,
    buckets: list[dict] | None = None,
    errors: list[dict] | None = None,
) -> dict:
    return {
        "account": {
            "account_id": "111122223333",
            "arn": "arn:aws:iam::111122223333:user/example",
            "user_id": "example",
        },
        "region": "eu-west-1",
        "services": {
            "lambda": [] if lambdas is None else lambdas,
            "s3": [] if buckets is None else buckets,
        },
        "errors": [] if errors is None else errors,
    }


@patch("aws_resource_mcp.tools.list_resources.collect_aws_inventory")
def test_complete_response_has_counts_and_ok_status(collect: Mock) -> None:
    collect.return_value = inventory(
        lambdas=[{"name": "first"}, {"name": "second"}],
        buckets=[{"name": "bucket"}],
    )
    result = listar_recursos_aws()
    assert result["status"] == "ok"
    assert result["summary"] == {
        "region": "eu-west-1",
        "partial": False,
        "account_id": "111122223333",
        "lambda_count": 2,
        "s3_bucket_count": 1,
    }
    assert set(result["resources"]) == {"lambda", "s3"}


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        (["lambda"], ["lambda"]),
        (["s3"], ["s3"]),
        (["lambda", "s3"], ["lambda", "s3"]),
        (["lambda", "lambda"], ["lambda"]),
        (["LAMBDA", "S3"], ["lambda", "s3"]),
    ],
)
@patch("aws_resource_mcp.tools.list_resources.collect_aws_inventory")
def test_service_filtering_and_normalization(
    collect: Mock, requested: list[str], expected: list[str]
) -> None:
    collect.return_value = inventory()
    result = listar_recursos_aws(services=requested)
    collect.assert_called_once_with("eu-west-1", services=expected)
    assert list(result["resources"]) == expected


@pytest.mark.parametrize("services", [[], ["dynamodb"], [""], [1]])
@patch("aws_resource_mcp.tools.list_resources.collect_aws_inventory")
def test_invalid_services_return_controlled_error(
    collect: Mock, services: list[str]
) -> None:
    result = listar_recursos_aws(services=services)
    assert result["status"] == "error"
    assert result["errors"][0]["type"] == "invalid_services"
    collect.assert_not_called()


@patch("aws_resource_mcp.tools.list_resources.collect_aws_inventory")
def test_empty_region_returns_controlled_error(collect: Mock) -> None:
    result = listar_recursos_aws(region="  ")
    assert result["status"] == "error"
    assert result["errors"][0]["type"] == "invalid_region"
    collect.assert_not_called()


@pytest.mark.parametrize("failed_service", ["lambda", "s3"])
@patch("aws_resource_mcp.tools.list_resources.collect_aws_inventory")
def test_partial_service_error_is_preserved(
    collect: Mock, failed_service: str
) -> None:
    collect.return_value = inventory(
        lambdas=[{"name": "visible"}] if failed_service == "s3" else [],
        buckets=[{"name": "visible"}] if failed_service == "lambda" else [],
        errors=[
            {
                "service": failed_service,
                "error_type": "access_denied",
                "message": "Check read-only permissions.",
            }
        ],
    )
    result = listar_recursos_aws()
    assert result["status"] == "partial"
    assert result["summary"]["partial"] is True
    assert result["errors"][0]["service"] == failed_service
    assert result["errors"][0]["type"] == "access_denied"


@patch("aws_resource_mcp.tools.list_resources.collect_aws_inventory")
def test_global_credential_error_is_controlled(collect: Mock) -> None:
    collect.side_effect = AWSInventoryGlobalError(
        {
            "service": "sts",
            "error_type": "credentials_not_found",
            "message": "Configure credentials through the standard chain.",
        }
    )
    result = listar_recursos_aws()
    assert result["status"] == "error"
    assert result["resources"] == {}
    assert result["errors"][0]["service"] == "aws"
    assert result["errors"][0]["type"] == "credentials_not_found"


@patch("aws_resource_mcp.tools.list_resources.collect_aws_inventory")
def test_unexpected_error_does_not_expose_exception(collect: Mock) -> None:
    collect.side_effect = RuntimeError("internal detail")
    result = listar_recursos_aws()
    assert result["status"] == "error"
    assert "internal detail" not in json.dumps(result)


@patch("aws_resource_mcp.tools.list_resources.collect_aws_inventory")
def test_empty_inventory_is_valid_and_serializable(collect: Mock) -> None:
    collect.return_value = inventory()
    result = listar_recursos_aws()
    assert result["status"] == "ok"
    assert result["summary"]["lambda_count"] == 0
    assert result["summary"]["s3_bucket_count"] == 0
    json.dumps(result)


@patch("aws_resource_mcp.tools.list_resources.collect_aws_inventory")
def test_account_id_can_be_omitted(collect: Mock) -> None:
    collect.return_value = inventory()
    result = listar_recursos_aws(include_account_id=False)
    assert "account_id" not in result["summary"]


@patch("aws_resource_mcp.tools.list_resources.collect_aws_inventory")
def test_sensitive_fields_are_removed_recursively(collect: Mock) -> None:
    collect.return_value = inventory(
        lambdas=[
            {
                "name": "example",
                "credentials": {
                    "aws_access_key_id": "not-a-real-key",
                    "aws_secret_access_key": "not-a-real-secret",
                    "session_token": "not-a-real-token",
                },
            }
        ]
    )
    serialized = json.dumps(listar_recursos_aws()).lower()
    for forbidden in (
        "aws_access_key_id",
        "aws_secret_access_key",
        "session_token",
        "credentials",
    ):
        assert forbidden not in serialized
