"""Architecture tests for the single uniform adapter registry."""

import inspect

from aws_resource_mcp.aws.adapters.base import ResourceAdapter
from aws_resource_mcp.aws.adapters.registry import ADAPTERS, get_adapters
from aws_resource_mcp.aws.operations import OPERATION_REGISTRY
from aws_resource_mcp.models import make_resource
from aws_resource_mcp.tools import list_resources

EXPECTED_ADAPTERS = {
    "lambda", "s3", "ec2", "rds", "dynamodb", "ecs", "apigateway",
    "cloudformation", "sqs", "sns", "iam", "cloudfront", "route53",
}


def test_every_service_is_in_one_registry_and_implements_contract() -> None:
    assert set(ADAPTERS) == EXPECTED_ADAPTERS
    assert [item.metadata.service_name for item in get_adapters()] == list(ADAPTERS)
    for name, adapter in ADAPTERS.items():
        assert isinstance(adapter, ResourceAdapter)
        assert adapter.metadata.service_name == name
        assert adapter.metadata.scope in {"regional", "global"}
        assert adapter.metadata.resource_types
        assert all(operation in OPERATION_REGISTRY for operation in adapter.metadata.operations)
        for operation in adapter.metadata.operations:
            spec = OPERATION_REGISTRY[operation]
            assert spec.component == f"adapter:{name}"
            assert spec.iam_actions
            assert spec.policy_target != "excluded"


def test_lambda_s3_and_other_services_use_identical_selection() -> None:
    assert [item.metadata.service_name for item in get_adapters(["lambda"])] == ["lambda"]
    assert [item.metadata.service_name for item in get_adapters(["ec2"])] == ["ec2"]
    assert [item.metadata.service_name for item in get_adapters(["s3"])] == ["s3"]
    assert [item.metadata.service_name for item in get_adapters(["rds"])] == ["rds"]


def test_tool_does_not_import_or_execute_service_adapters_directly() -> None:
    source = inspect.getsource(list_resources)
    assert "LambdaAdapter" not in source
    assert "S3Adapter" not in source
    assert "ADAPTERS" not in source


def test_common_model_has_no_service_specific_root_fields() -> None:
    roots = set(
        make_resource(
            service="example",
            resource_type="AWS::Example::Resource",
            region="eu-west-1",
            source="example_api",
        )
    )
    assert roots == {
        "id", "arn", "name", "service", "resource_type", "region",
        "account_id", "state", "created_at", "sources", "details",
        "cost_indicators", "activity",
    }
