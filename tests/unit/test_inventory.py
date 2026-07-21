"""Tests for the aggregate inventory and diagnostic command."""

import json
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError, NoCredentialsError
import pytest

from aws_resource_mcp.aws.errors import AWSInventoryGlobalError
from aws_resource_mcp.aws.inventory import collect_aws_inventory, main


@patch("aws_resource_mcp.aws.inventory.list_s3_buckets")
@patch("aws_resource_mcp.aws.inventory.list_lambda_functions")
@patch("aws_resource_mcp.aws.inventory.get_aws_identity")
def test_complete_inventory_is_json_serializable(
    identity: Mock, lambdas: Mock, buckets: Mock
) -> None:
    identity.return_value = {"account_id": "111122223333", "arn": "example", "user_id": "id"}
    lambdas.return_value = [{"name": "function"}]
    buckets.return_value = ([{"name": "bucket"}], [])

    result = collect_aws_inventory(session=Mock())
    serialized = json.dumps(result)
    assert '"region": "eu-west-1"' in serialized
    assert result["services"]["lambda"] == [{"name": "function"}]
    assert result["services"]["s3"] == [{"name": "bucket"}]
    assert result["errors"] == []


@patch("aws_resource_mcp.aws.inventory.list_s3_buckets")
@patch("aws_resource_mcp.aws.inventory.list_lambda_functions")
@patch("aws_resource_mcp.aws.inventory.get_aws_identity")
def test_partial_service_failure_preserves_other_data(
    identity: Mock, lambdas: Mock, buckets: Mock
) -> None:
    identity.return_value = {"account_id": "account", "arn": "arn", "user_id": "user"}
    lambdas.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
        "ListFunctions",
    )
    buckets.return_value = ([{"name": "visible"}], [])

    result = collect_aws_inventory(session=Mock())
    assert result["services"]["lambda"] == []
    assert result["services"]["s3"] == [{"name": "visible"}]
    assert result["errors"][0]["service"] == "lambda"
    assert result["errors"][0]["error_type"] == "access_denied"


@patch("aws_resource_mcp.aws.inventory.get_aws_identity", side_effect=NoCredentialsError())
def test_missing_credentials_are_a_global_error(identity: Mock) -> None:
    with pytest.raises(AWSInventoryGlobalError) as raised:
        collect_aws_inventory(session=Mock())
    assert raised.value.error["service"] == "sts"
    assert raised.value.error["error_type"] == "credentials_not_found"


@patch("aws_resource_mcp.aws.inventory.collect_aws_inventory")
def test_diagnostic_command_prints_json_and_succeeds(
    collect: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    collect.return_value = {
        "account": {},
        "region": "eu-west-1",
        "services": {"lambda": [], "s3": []},
        "errors": [],
    }
    assert main([]) == 0
    assert json.loads(capsys.readouterr().out)["region"] == "eu-west-1"


@patch("aws_resource_mcp.aws.inventory.collect_aws_inventory")
def test_diagnostic_command_returns_nonzero_for_global_error(
    collect: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    collect.side_effect = AWSInventoryGlobalError(
        {"service": "sts", "error_type": "profile_not_found", "message": "Check profile."}
    )
    assert main(["--profile", "missing"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["service"] == "sts"


def test_inventory_source_does_not_expose_credential_fields() -> None:
    result = {
        "account": {"account_id": "account", "arn": "arn", "user_id": "user"},
        "region": "eu-west-1",
        "services": {"lambda": [], "s3": []},
        "errors": [],
    }
    serialized = json.dumps(result).lower()
    assert "access_key" not in serialized
    assert "secret_key" not in serialized
    assert "session_token" not in serialized
