"""Single registry for every AWS service adapter."""

from collections.abc import Collection

from aws_resource_mcp.aws.adapters.base import ResourceAdapter
from aws_resource_mcp.aws.adapters.databases import DynamoDBAdapter, RDSAdapter
from aws_resource_mcp.aws.adapters.ec2 import EC2Adapter
from aws_resource_mcp.aws.adapters.ecs import ECSAdapter
from aws_resource_mcp.aws.adapters.global_services import (
    CloudFrontAdapter,
    IAMAdapter,
    Route53Adapter,
)
from aws_resource_mcp.aws.adapters.integration import (
    ApiGatewayAdapter,
    CloudFormationAdapter,
    SNSAdapter,
    SQSAdapter,
)
from aws_resource_mcp.aws.adapters.lambda_s3 import LambdaAdapter, S3Adapter
from aws_resource_mcp.aws.operations import OPERATION_REGISTRY

_ADAPTER_INSTANCES: tuple[ResourceAdapter, ...] = (
    LambdaAdapter(),
    S3Adapter(),
    EC2Adapter(),
    RDSAdapter(),
    DynamoDBAdapter(),
    ECSAdapter(),
    ApiGatewayAdapter(),
    CloudFormationAdapter(),
    SQSAdapter(),
    SNSAdapter(),
    IAMAdapter(),
    CloudFrontAdapter(),
    Route53Adapter(),
)

ADAPTERS: dict[str, ResourceAdapter] = {
    adapter.metadata.service_name: adapter for adapter in _ADAPTER_INSTANCES
}


def get_adapters(services: Collection[str] | None = None) -> list[ResourceAdapter]:
    """Return registered adapters in stable order, optionally filtered."""
    requested = None if services is None else set(services)
    return [
        adapter
        for name, adapter in ADAPTERS.items()
        if requested is None or name in requested
    ]


def validate_registry() -> None:
    """Fail fast if adapter metadata bypasses the central operation registry."""
    for adapter in ADAPTERS.values():
        if not isinstance(adapter, ResourceAdapter):
            raise TypeError(f"{adapter!r} does not implement ResourceAdapter")
        for operation in adapter.metadata.operations:
            if operation not in OPERATION_REGISTRY:
                raise ValueError(
                    f"{adapter.metadata.service_name} declares unregistered operation {operation}"
                )


validate_registry()
