"""Tests for the aggregate inventory and diagnostic command."""

import json
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
import pytest

from aws_resource_mcp.aws.errors import AWSInventoryGlobalError
from aws_resource_mcp.aws.inventory import (
    _matches_resource_type,
    collect_aws_inventory,
    collect_general_aws_inventory,
    main,
)


def test_cfn_and_resource_explorer_type_filters_are_equivalent() -> None:
    resource = {"resource_type": "AWS::EC2::Instance"}
    assert _matches_resource_type(resource, {"aws::ec2::instance"})
    assert _matches_resource_type(resource, {"ec2:instance"})


@patch("aws_resource_mcp.aws.inventory.collect_general_aws_inventory")
def test_diagnostic_inventory_uses_the_uniform_collector(collect: Mock) -> None:
    collect.return_value = {"resources": [], "services": {}, "errors": []}

    result = collect_aws_inventory(
        region="eu-west-1",
        profile_name="example",
        session=Mock(),
        services=["ec2"],
    )

    assert json.dumps(result)
    collect.assert_called_once()
    assert collect.call_args.kwargs["services"] == ["ec2"]
    assert collect.call_args.kwargs["all_regions"] is False


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


@patch("aws_resource_mcp.aws.inventory.execute_adapters")
@patch("aws_resource_mcp.aws.inventory.discover_with_resource_explorer")
@patch("aws_resource_mcp.aws.inventory.list_aws_regions")
@patch("aws_resource_mcp.aws.inventory.get_aws_identity")
def test_general_inventory_scans_enabled_regions_and_deduplicates(
    identity: Mock,
    regions: Mock,
    explorer: Mock,
    adapters: Mock,
) -> None:
    identity.return_value = {"account_id": "account", "arn": "arn", "user_id": "user"}
    regions.return_value = [
        {"name": "eu-central-1", "enabled": True},
        {"name": "eu-west-1", "enabled": True},
        {"name": "us-west-1", "enabled": False},
    ]
    lambda_arn = "arn:aws:lambda:eu-west-1:account:function:function"
    resource = {
        "arn": lambda_arn,
        "service": "lambda",
        "resource_type": "lambda:function",
        "region": "eu-west-1",
        "name": "function",
        "sources": ["resource_explorer"],
        "details": {},
        "cost_indicators": [],
    }
    adapters.return_value = {
        "resources": [resource],
        "errors": [],
        "coverage": {
            "registered": ["lambda"],
            "selected": ["lambda"],
            "executed": ["lambda"],
            "failed": [],
            "operations_executed": [],
        },
    }
    explorer.return_value = {
        "resources": [
            resource,
            resource.copy(),
        ],
        "coverage": {
            "available": True,
            "aggregator_index": True,
            "regions_indexed": ["eu-west-1"],
            "supported_resource_type_count": 1,
            "services_recognized": ["lambda"],
            "permission_errors": [],
            "limitations": [],
        },
        "errors": [],
    }
    result = collect_general_aws_inventory(session=Mock())

    assert len(result["resources"]) == 1
    assert result["services"] == {"lambda": result["resources"]}
    assert result["resources"][0]["sources"] == ["resource_explorer"]
    assert result["coverage"]["status"] == "complete_for_supported_resources"


@patch("aws_resource_mcp.aws.inventory.execute_adapters")
@patch("aws_resource_mcp.aws.inventory.discover_with_resource_explorer")
@patch("aws_resource_mcp.aws.inventory.list_aws_regions")
@patch("aws_resource_mcp.aws.inventory.get_aws_identity")
def test_general_inventory_filters_service_and_region(
    identity: Mock,
    regions: Mock,
    explorer: Mock,
    adapters: Mock,
) -> None:
    identity.return_value = {"account_id": "account", "arn": "arn", "user_id": "user"}
    regions.return_value = [{"name": "eu-west-1", "enabled": True}]
    explorer.return_value = {
        "resources": [],
        "coverage": {
            "available": True,
            "aggregator_index": False,
            "regions_indexed": ["eu-west-1"],
            "permission_errors": [],
            "limitations": ["local only"],
        },
        "errors": [],
    }
    adapters.return_value = {
        "resources": [],
        "errors": [],
        "coverage": {
            "registered": [], "selected": [], "executed": [], "failed": [],
            "operations_executed": [],
        },
    }
    result = collect_general_aws_inventory(
        region="eu-west-1",
        services=["lambda"],
        all_regions=True,
        session=Mock(),
    )

    assert explorer.call_args.kwargs["services"] == ["lambda"]
    assert explorer.call_args.kwargs["region_filter"] == "eu-west-1"
    assert result["coverage"]["regions_scanned"] == ["eu-west-1"]
    assert result["coverage"]["status"] == "partial"


@patch("aws_resource_mcp.aws.inventory.execute_adapters")
@patch("aws_resource_mcp.aws.inventory.discover_with_resource_explorer")
@patch("aws_resource_mcp.aws.inventory.list_aws_regions")
@patch("aws_resource_mcp.aws.inventory.get_aws_identity")
def test_general_inventory_region_failure_reports_unavailable_coverage(
    identity: Mock,
    regions: Mock,
    explorer: Mock,
    adapters: Mock,
) -> None:
    identity.return_value = {"account_id": "account", "arn": "arn", "user_id": "user"}
    regions.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "denied"}},
        "DescribeRegions",
    )
    explorer.return_value = {
        "resources": [],
        "coverage": {
            "available": False,
            "aggregator_index": False,
            "regions_indexed": [],
            "permission_errors": [],
            "limitations": ["not configured"],
        },
        "errors": [],
    }
    adapters.return_value = {
        "resources": [],
        "errors": [],
        "coverage": {
            "registered": [], "selected": [], "executed": [], "failed": [],
            "operations_executed": [],
        },
    }
    result = collect_general_aws_inventory(session=Mock())

    assert result["services"] == {}
    assert result["resources"] == []
    assert result["coverage"]["status"] == "unavailable"
    assert any(error["service"] == "ec2" for error in result["errors"])


@patch("aws_resource_mcp.aws.inventory.execute_adapters")
@patch("aws_resource_mcp.aws.inventory.discover_with_resource_explorer")
@patch("aws_resource_mcp.aws.inventory.list_aws_regions")
@patch("aws_resource_mcp.aws.inventory.get_aws_identity")
def test_uniform_adapter_fallback_makes_unavailable_general_discovery_partial(
    identity: Mock,
    regions: Mock,
    explorer: Mock,
    adapters: Mock,
) -> None:
    identity.return_value = {"account_id": "account", "arn": "arn", "user_id": "user"}
    regions.return_value = [{"name": "eu-west-1", "enabled": True}]
    explorer.return_value = {
        "resources": [],
        "coverage": {
            "available": False, "aggregator_index": False, "regions_indexed": [],
            "permission_errors": [], "limitations": ["not configured"],
        },
        "errors": [],
    }
    adapters.return_value = {
        "resources": [], "errors": [],
        "coverage": {
            "registered": ["lambda", "ec2"], "selected": ["lambda", "ec2"],
            "executed": ["lambda", "ec2"], "failed": [], "operations_executed": [],
        },
    }

    result = collect_general_aws_inventory(session=Mock())

    assert result["coverage"]["status"] == "partial"
    assert result["coverage"]["adapters"]["executed"] == ["lambda", "ec2"]
    assert "uniform fallback" in result["coverage"]["resource_explorer"]["limitations"][-1]
