"""Tests for the MCP-facing general AWS inventory tool."""

import json
from unittest.mock import Mock, patch

import pytest

from aws_resource_mcp.aws.errors import AWSInventoryGlobalError
from aws_resource_mcp.tools.list_resources import listar_recursos_aws


def inventory(
    *,
    general: list[dict] | None = None,
    errors: list[dict] | None = None,
    coverage_status: str = "complete_for_supported_resources",
) -> dict:
    general_items = [] if general is None else general
    grouped: dict[str, list[dict]] = {}
    for item in general_items:
        grouped.setdefault(item["service"], []).append(item)
    return {
        "account": {"account_id": "111122223333", "arn": "example", "user_id": "id"},
        "region": "eu-west-1",
        "services": grouped,
        "resources": general_items,
        "resources_by_service": grouped,
        "coverage": {
            "status": coverage_status,
            "regions_scanned": ["eu-west-1"],
            "regions_enabled": ["eu-west-1"],
            "resource_explorer": {
                "available": coverage_status != "unavailable",
                "aggregator_index": coverage_status
                == "complete_for_supported_resources",
            },
        },
        "errors": [] if errors is None else errors,
    }


@patch("aws_resource_mcp.tools.list_resources.collect_general_aws_inventory")
def test_global_inventory_has_compatible_and_expanded_fields(collect: Mock) -> None:
    resources = [
        {"service": "lambda", "name": "function"},
        {"service": "ec2", "name": "instance"},
    ]
    collect.return_value = inventory(general=resources)
    result = listar_recursos_aws()
    assert result["status"] == "complete_for_requested_scope"
    assert result["summary"]["total_resources"] == 2
    assert result["summary"]["services_detected"] == 2
    assert result["summary"]["partial"] is False
    assert result["resources"]["lambda"] == [resources[0]]
    assert result["all_resources"] == resources
    assert result["coverage"]["status"] == "complete_for_supported_resources"


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        (["lambda"], ["lambda"]),
        (["s3"], ["s3"]),
        (["lambda", "s3"], ["lambda", "s3"]),
        (["lambda", "lambda"], ["lambda"]),
        (["EC2", "S3"], ["ec2", "s3"]),
    ],
)
@patch("aws_resource_mcp.tools.list_resources.collect_general_aws_inventory")
def test_service_filtering_and_normalization(
    collect: Mock, requested: list[str], expected: list[str]
) -> None:
    collect.return_value = inventory()
    listar_recursos_aws(region="eu-west-1", services=requested)
    collect.assert_called_once_with(
        "eu-west-1",
        services=expected,
        resource_types=None,
        query=None,
        all_regions=True,
        include_details=True,
        include_cost_indicators=True,
        confirm_potentially_billable_operations=False,
        timeout_seconds=30.0,
    )


@patch("aws_resource_mcp.tools.list_resources.collect_general_aws_inventory")
def test_region_type_query_and_all_regions_filters(collect: Mock) -> None:
    collect.return_value = inventory()
    listar_recursos_aws(
        region="eu-central-1",
        services=["ec2"],
        resource_types=["ec2:instance"],
        query="web",
        all_regions=False,
        include_details=True,
        include_cost_indicators=True,
        confirm_potentially_billable_operations=False,
        timeout_seconds=30.0,
    )
    collect.assert_called_once_with(
        "eu-central-1",
        services=["ec2"],
        resource_types=["ec2:instance"],
        query="web",
        all_regions=False,
        include_details=True,
        include_cost_indicators=True,
        confirm_potentially_billable_operations=False,
        timeout_seconds=30.0,
    )


@pytest.mark.parametrize("services", [[], [""], [1], ["ec2 instance"]])
@patch("aws_resource_mcp.tools.list_resources.collect_general_aws_inventory")
def test_invalid_services_return_controlled_error(
    collect: Mock, services: list
) -> None:
    result = listar_recursos_aws(services=services)
    assert result["status"] == "error"
    assert result["errors"][0]["type"] == "invalid_filters"
    collect.assert_not_called()


@patch("aws_resource_mcp.tools.list_resources.collect_general_aws_inventory")
def test_invalid_region_type_and_query_return_controlled_errors(collect: Mock) -> None:
    assert listar_recursos_aws(region="  ")["status"] == "error"
    assert listar_recursos_aws(resource_types=[])["status"] == "error"
    assert listar_recursos_aws(resource_types=["not valid"])["status"] == "error"
    assert listar_recursos_aws(query=123)["status"] == "error"
    assert listar_recursos_aws(include_details="yes")["status"] == "error"
    assert listar_recursos_aws(include_cost_indicators=1)["status"] == "error"
    assert (
        listar_recursos_aws(confirm_potentially_billable_operations="yes")["status"]
        == "error"
    )
    collect.assert_not_called()


@patch("aws_resource_mcp.tools.list_resources.collect_general_aws_inventory")
def test_detail_and_cost_flags_are_uniformly_forwarded(collect: Mock) -> None:
    collect.return_value = inventory()
    listar_recursos_aws(
        services=["rds"],
        include_details=False,
        include_cost_indicators=False,
        confirm_potentially_billable_operations=True,
    )
    assert collect.call_args.kwargs["include_details"] is False
    assert collect.call_args.kwargs["include_cost_indicators"] is False
    assert collect.call_args.kwargs["confirm_potentially_billable_operations"] is True


@patch("aws_resource_mcp.tools.list_resources.attach_free_activity_summaries")
@patch("aws_resource_mcp.tools.list_resources.collect_general_aws_inventory")
def test_activity_summary_uses_only_existing_inventory_fields(
    collect: Mock, attach: Mock
) -> None:
    item = {"service": "ec2", "name": "instance", "activity": {"status": "unknown"}}
    collect.return_value = inventory(general=[item])
    attach.return_value = [
        {
            **item,
            "activity": {
                "status": "active",
                "source": "ec2_api",
                "paid_data_executed": False,
            },
        }
    ]

    result = listar_recursos_aws(include_activity_summary=True)

    attach.assert_called_once_with([item])
    assert result["all_resources"][0]["activity"]["status"] == "active"
    assert result["resources"]["ec2"] == result["all_resources"]


@patch("aws_resource_mcp.tools.list_resources.collect_general_aws_inventory")
def test_partial_coverage_and_service_error_are_preserved(collect: Mock) -> None:
    collect.return_value = inventory(
        general=[{"service": "lambda", "name": "visible"}],
        errors=[
            {
                "service": "resource-explorer-2",
                "error_type": "access_denied",
                "message": "Check read-only permissions.",
            }
        ],
        coverage_status="partial",
    )
    result = listar_recursos_aws()
    assert result["status"] == "partial_permission_denied"
    assert result["summary"]["partial"] is True
    assert result["errors"][0]["type"] == "access_denied"


@patch("aws_resource_mcp.tools.list_resources.collect_general_aws_inventory")
def test_unavailable_resource_explorer_has_no_service_specific_fallback(
    collect: Mock,
) -> None:
    collect.return_value = inventory(
        coverage_status="unavailable",
    )
    result = listar_recursos_aws()
    assert result["status"] == "partial_unavailable"
    assert result["resources"] == {}
    assert result["all_resources"] == []
    assert result["coverage"]["status"] == "unavailable"


@patch("aws_resource_mcp.tools.list_resources.collect_general_aws_inventory")
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


@patch("aws_resource_mcp.tools.list_resources.collect_general_aws_inventory")
def test_account_id_can_be_omitted_and_response_is_json(collect: Mock) -> None:
    collect.return_value = inventory(
        general=[{"service": "ec2", "account_id": "111122223333"}]
    )
    result = listar_recursos_aws(include_account_id=False)
    serialized = json.dumps(result)
    assert "account_id" not in serialized
    assert "111122223333" not in serialized


@patch("aws_resource_mcp.tools.list_resources.collect_general_aws_inventory")
def test_sensitive_fields_are_removed_recursively(collect: Mock) -> None:
    collect.return_value = inventory(
        general=[
            {
                "service": "ec2",
                "credentials": {"aws_access_key_id": "not-real"},
                "properties": {
                    "aws_secret_access_key": "not-real",
                    "session_token": "not-real",
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
