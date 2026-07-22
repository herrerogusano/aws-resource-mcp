"""Architecture tests for uniform adapter activity signals."""

import inspect

from aws_resource_mcp.activity import engine
from aws_resource_mcp.aws.adapters.base import ActivityContext
from aws_resource_mcp.aws.adapters.registry import ADAPTERS
from aws_resource_mcp.models import make_resource


def resource(service: str) -> dict:
    return make_resource(
        service=service,
        resource_type=f"AWS::{service.title()}::Resource",
        region="eu-west-1",
        source="test_api",
        identifier=f"{service}-id",
        state="available",
        created_at="2026-01-01T00:00:00Z",
    )


def test_every_adapter_implements_the_same_free_signal_contract() -> None:
    context = ActivityContext(30, 90, True, 20)
    for name, adapter in ADAPTERS.items():
        signals = adapter.get_free_activity_signals([resource(name)], context)
        assert signals
        assert {item["source"] for item in signals} == {f"{name}_api"}


def test_lambda_s3_ec2_and_rds_use_the_same_pipeline() -> None:
    context = ActivityContext(30, 90, True, 20)
    shapes = []
    for name in ("lambda", "s3", "ec2", "rds"):
        signals = ADAPTERS[name].get_free_activity_signals([resource(name)], context)
        shapes.append(set(signals[0]))
    assert all(shape == shapes[0] for shape in shapes)


def test_adapter_without_timestamped_signals_stays_representable() -> None:
    item = make_resource(
        service="sns",
        resource_type="AWS::SNS::Topic",
        region="eu-west-1",
        source="test",
        identifier="topic",
    )
    signals = ADAPTERS["sns"].get_free_activity_signals(
        [item], ActivityContext(30, 90, True, 20)
    )
    assert signals == []


def test_no_adapter_activity_path_calls_cloudwatch() -> None:
    for adapter in ADAPTERS.values():
        source = inspect.getsource(adapter.__class__.get_free_activity_signals)
        assert "cloudwatch" not in source.lower()


def test_activity_engine_has_no_lambda_or_s3_special_route() -> None:
    source = inspect.getsource(engine)
    assert "LambdaAdapter" not in source
    assert "S3Adapter" not in source
    assert "get_free_activity_signals" in source
