"""Tests for uniform adapter execution, fallback, and merging."""

from dataclasses import dataclass
from unittest.mock import Mock

import pytest

from aws_resource_mcp.aws import adapter_engine
from aws_resource_mcp.aws.adapters import registry
from aws_resource_mcp.aws.adapters.base import AdapterContext, AdapterMetadata
from aws_resource_mcp.aws.operations import OperationGuard
from aws_resource_mcp.models import Resource, make_resource


@dataclass
class FakeAdapter:
    metadata: AdapterMetadata
    resource: Resource | None = None
    fail: bool = False

    def discover(self, context: AdapterContext) -> list[Resource]:
        if self.fail:
            raise PermissionError("denied")
        return [] if self.resource is None else [self.resource]

    def enrich(
        self, resources: list[Resource], context: AdapterContext
    ) -> list[Resource]:
        return resources


def _adapter(name: str, resource: Resource | None = None, *, fail: bool = False) -> FakeAdapter:
    return FakeAdapter(
        AdapterMetadata(
            service_name=name,
            scope="regional",
            operations=(),
            resource_types=(f"AWS::{name}::Resource",),
        ),
        resource,
        fail,
    )


def _install(
    monkeypatch: pytest.MonkeyPatch,
    adapters: dict[str, FakeAdapter],
) -> None:
    monkeypatch.setattr(registry, "ADAPTERS", adapters)
    monkeypatch.setattr(adapter_engine, "ADAPTERS", adapters)


def test_uniform_fallback_executes_every_registered_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapters = {
        name: _adapter(name)
        for name in ("lambda", "s3", "ec2", "rds")
    }
    _install(monkeypatch, adapters)

    result = adapter_engine.execute_adapters(
        Mock(), account_id="account", regions=["eu-west-1"],
        primary_region="eu-west-1", discovered_resources=[], services=None,
        include_details=True, include_cost_indicators=True,
        operation_guard=OperationGuard(),
    )

    assert result["coverage"]["executed"] == ["lambda", "s3", "ec2", "rds"]
    assert result["coverage"]["failed"] == []


@pytest.mark.parametrize("service", ["lambda", "s3", "ec2", "rds"])
def test_service_filters_follow_the_same_registry_path(
    monkeypatch: pytest.MonkeyPatch,
    service: str,
) -> None:
    adapters = {name: _adapter(name) for name in ("lambda", "s3", "ec2", "rds")}
    _install(monkeypatch, adapters)
    result = adapter_engine.execute_adapters(
        Mock(), account_id="account", regions=["eu-west-1"],
        primary_region="eu-west-1", discovered_resources=[], services=[service],
        include_details=True, include_cost_indicators=True,
        operation_guard=OperationGuard(),
    )
    assert result["coverage"]["selected"] == [service]
    assert result["coverage"]["executed"] == [service]


def test_adapter_details_merge_with_general_discovery_without_empty_overwrite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arn = "arn:aws:example:eu-west-1:account:resource/id"
    general = make_resource(
        service="example", resource_type="AWS::Example::Resource",
        region="eu-west-1", source="resource_explorer", identifier="id",
        arn=arn, details={"general": True, "keep": "value"},
    )
    detailed = make_resource(
        service="example", resource_type="AWS::Example::Resource",
        region="eu-west-1", source="example_api", identifier="id", arn=arn,
        details={"specific": True, "keep": None},
    )
    _install(monkeypatch, {"example": _adapter("example", detailed)})

    result = adapter_engine.execute_adapters(
        Mock(), account_id="account", regions=["eu-west-1"],
        primary_region="eu-west-1", discovered_resources=[general], services=None,
        include_details=True, include_cost_indicators=True,
        operation_guard=OperationGuard(),
    )

    assert len(result["resources"]) == 1
    resource = result["resources"][0]
    assert resource["sources"] == ["resource_explorer", "example_api"]
    assert resource["details"] == {"general": True, "keep": "value", "specific": True}


def test_one_adapter_failure_preserves_other_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    visible = make_resource(
        service="visible", resource_type="AWS::visible::Resource",
        region="eu-west-1", source="visible_api", identifier="id",
    )
    _install(monkeypatch, {
        "failed": _adapter("failed", fail=True),
        "visible": _adapter("visible", visible),
    })

    result = adapter_engine.execute_adapters(
        Mock(), account_id="account", regions=["eu-west-1"],
        primary_region="eu-west-1", discovered_resources=[], services=None,
        include_details=True, include_cost_indicators=True,
        operation_guard=OperationGuard(),
    )

    assert result["coverage"]["failed"] == ["failed"]
    assert result["coverage"]["executed"] == ["visible"]
    assert result["resources"] == [visible]
    assert result["errors"][0]["service"] == "failed"


def test_real_lambda_adapter_executes_free_operation_through_guard() -> None:
    client = Mock()
    client.list_functions.return_value = {"Functions": []}
    session = Mock()
    session.client.return_value = client

    result = adapter_engine.execute_adapters(
        session, account_id="account", regions=["eu-west-1"],
        primary_region="eu-west-1", discovered_resources=[], services=["lambda"],
        include_details=True, include_cost_indicators=True,
        operation_guard=OperationGuard(),
    )

    assert result["coverage"]["executed"] == ["lambda"]
    assert result["coverage"]["operations_executed"][0]["operation"] == "ListFunctions"
    client.list_functions.assert_called_once_with()


@pytest.mark.parametrize(
    ("service", "method"),
    [("s3", "list_buckets"), ("sqs", "list_queues"), ("sns", "list_topics")],
)
def test_metered_adapter_operations_are_blocked_before_boto3(
    service: str,
    method: str,
) -> None:
    client = Mock()
    session = Mock()
    session.client.return_value = client

    result = adapter_engine.execute_adapters(
        session, account_id="account", regions=["eu-west-1"],
        primary_region="eu-west-1", discovered_resources=[], services=[service],
        include_details=True, include_cost_indicators=True,
        operation_guard=OperationGuard(),
    )

    assert result["coverage"]["failed"] == [service]
    assert result["errors"][0]["executed"] is False
    getattr(client, method).assert_not_called()


def test_regional_failure_keeps_successful_region_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter("regional")

    def discover(context: AdapterContext) -> list[Resource]:
        region = context.regions[0]
        if region == "eu-central-1":
            raise PermissionError("denied")
        return [make_resource(
            service="regional", resource_type="AWS::regional::Resource",
            region=region, source="regional_api", identifier=region,
        )]

    adapter.discover = discover  # type: ignore[method-assign]
    _install(monkeypatch, {"regional": adapter})

    result = adapter_engine.execute_adapters(
        Mock(), account_id="account", regions=["eu-west-1", "eu-central-1"],
        primary_region="eu-west-1", discovered_resources=[], services=None,
        include_details=True, include_cost_indicators=True,
        operation_guard=OperationGuard(),
    )

    assert len(result["resources"]) == 1
    assert result["coverage"]["executed"] == ["regional"]
    assert result["coverage"]["failed"] == ["regional"]
