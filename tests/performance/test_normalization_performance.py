"""Lightweight local regression checks for normalized inventory handling."""

from time import perf_counter

from aws_resource_mcp.aws.discovery import deduplicate_resources
from aws_resource_mcp.models import make_resource


def test_deduplication_of_five_thousand_normalized_resources_is_bounded() -> None:
    resources = [
        make_resource(
            service="lambda",
            resource_type="AWS::Lambda::Function",
            region="eu-west-1",
            source="fake",
            identifier=f"function-{index}",
            arn=f"arn:aws:lambda:eu-west-1:example:function:function-{index}",
        )
        for index in range(5_000)
    ]
    started = perf_counter()
    result = deduplicate_resources(resources, list(resources))
    elapsed_seconds = perf_counter() - started

    assert len(result) == 5_000
    assert elapsed_seconds < 3.0
