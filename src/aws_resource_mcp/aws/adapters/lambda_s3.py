"""Lambda and S3 adapters using the same contract as every other service."""

from typing import Any

from botocore.exceptions import ClientError

from aws_resource_mcp.aws.adapters.base import (
    AdapterContext,
    AdapterMetadata,
    BaseAdapter,
    pages,
)
from aws_resource_mcp.models import Resource, cost_indicator, make_resource


class LambdaAdapter(BaseAdapter):
    metadata = AdapterMetadata(
        service_name="lambda",
        scope="regional",
        operations=(("lambda", "ListFunctions"),),
        resource_types=("AWS::Lambda::Function",),
        detail_fields=(
            "runtime",
            "memory_mb",
            "timeout_seconds",
            "architectures",
            "code_size_bytes",
            "package_type",
            "ephemeral_storage_mb",
            "last_modified",
            "layers_count",
            "vpc_id",
        ),
        cost_indicator_types=("high_memory", "additional_ephemeral_storage"),
    )

    def discover(self, context: AdapterContext) -> list[Resource]:
        resources: list[Resource] = []
        for region in self.regions(context):
            functions = pages(
                context,
                "lambda",
                "ListFunctions",
                "Functions",
                region=region,
                request_token="Marker",
                response_token="NextMarker",
            )
            for function in functions:
                memory = function.get("MemorySize")
                ephemeral = function.get("EphemeralStorage", {}).get("Size")
                indicators = []
                if context.include_cost_indicators and isinstance(memory, int) and memory >= 3008:
                    indicators.append(
                        cost_indicator(
                            "high_memory",
                            "medium",
                            "High configured memory can increase compute charges per invocation.",
                        )
                    )
                if context.include_cost_indicators and isinstance(ephemeral, int) and ephemeral > 512:
                    indicators.append(
                        cost_indicator(
                            "additional_ephemeral_storage",
                            "low",
                            "Ephemeral storage above the included baseline can generate charges.",
                        )
                    )
                details = {
                    "runtime": function.get("Runtime"),
                    "memory_mb": memory,
                    "timeout_seconds": function.get("Timeout"),
                    "architectures": list(function.get("Architectures", [])),
                    "code_size_bytes": function.get("CodeSize"),
                    "package_type": function.get("PackageType"),
                    "ephemeral_storage_mb": ephemeral,
                    "last_modified": function.get("LastModified"),
                    "layers_count": len(function.get("Layers", [])),
                    "vpc_id": function.get("VpcConfig", {}).get("VpcId"),
                } if context.include_details else {}
                resources.append(
                    make_resource(
                        service="lambda",
                        resource_type="AWS::Lambda::Function",
                        region=region,
                        source="lambda_api",
                        identifier=function.get("FunctionName"),
                        arn=function.get("FunctionArn"),
                        name=function.get("FunctionName"),
                        account_id=context.account_id,
                        state=function.get("State") or "active",
                        details=details,
                        cost_indicators=indicators,
                    )
                )
        return resources


_ABSENT_S3_CONFIGURATION = {
    "NoSuchLifecycleConfiguration",
    "ReplicationConfigurationNotFoundError",
    "ServerSideEncryptionConfigurationNotFoundError",
    "NoSuchPublicAccessBlockConfiguration",
}


def _optional_bucket_call(
    context: AdapterContext,
    operation: str,
    bucket: str,
) -> dict[str, Any] | None:
    try:
        return context.call("s3", operation, Bucket=bucket)
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code")
        if code in _ABSENT_S3_CONFIGURATION:
            return None
        raise


class S3Adapter(BaseAdapter):
    metadata = AdapterMetadata(
        service_name="s3",
        scope="global",
        operations=(
            ("s3", "ListBuckets"),
            ("s3", "GetBucketLocation"),
            ("s3", "GetBucketVersioning"),
            ("s3", "GetBucketLifecycleConfiguration"),
            ("s3", "GetBucketReplication"),
            ("s3", "GetBucketLogging"),
            ("s3", "GetBucketEncryption"),
            ("s3", "GetPublicAccessBlock"),
        ),
        resource_types=("AWS::S3::Bucket",),
        detail_fields=(
            "versioning",
            "lifecycle_configuration",
            "replication",
            "logging",
            "encryption",
            "public_access_block",
        ),
        cost_indicator_types=("versioned_storage", "replicated_storage", "access_logging"),
    )

    def discover(self, context: AdapterContext) -> list[Resource]:
        buckets = context.call("s3", "ListBuckets").get("Buckets", [])
        resources: list[Resource] = []
        for bucket in buckets:
            name = bucket.get("Name")
            if not name:
                continue
            location = context.call("s3", "GetBucketLocation", Bucket=name).get(
                "LocationConstraint"
            ) or "us-east-1"
            versioning = context.call("s3", "GetBucketVersioning", Bucket=name).get("Status")
            lifecycle = _optional_bucket_call(context, "GetBucketLifecycleConfiguration", name)
            replication = _optional_bucket_call(context, "GetBucketReplication", name)
            logging = _optional_bucket_call(context, "GetBucketLogging", name)
            encryption = _optional_bucket_call(context, "GetBucketEncryption", name)
            public_access = _optional_bucket_call(context, "GetPublicAccessBlock", name)
            indicators = []
            if context.include_cost_indicators and versioning == "Enabled":
                indicators.append(
                    cost_indicator(
                        "versioned_storage",
                        "low",
                        "Versioning can retain additional object versions and increase storage usage.",
                    )
                )
            if context.include_cost_indicators and replication:
                indicators.append(
                    cost_indicator(
                        "replicated_storage",
                        "medium",
                        "Replication can multiply storage and transfer usage.",
                    )
                )
            if context.include_cost_indicators and logging and logging.get("LoggingEnabled"):
                indicators.append(
                    cost_indicator(
                        "access_logging",
                        "low",
                        "Access logging writes additional objects that consume storage.",
                    )
                )
            details = {
                "versioning": (versioning or "disabled").lower(),
                "lifecycle_configuration": bool(lifecycle),
                "replication": bool(replication),
                "logging": bool(logging and logging.get("LoggingEnabled")),
                "encryption": bool(encryption),
                "public_access_block": (
                    public_access.get("PublicAccessBlockConfiguration", {})
                    if public_access
                    else {}
                ),
            } if context.include_details else {}
            resources.append(
                make_resource(
                    service="s3",
                    resource_type="AWS::S3::Bucket",
                    region=location,
                    source="s3_api",
                    identifier=name,
                    arn=f"arn:aws:s3:::{name}",
                    name=name,
                    account_id=context.account_id,
                    state="available",
                    created_at=bucket.get("CreationDate"),
                    details=details,
                    cost_indicators=indicators,
                )
            )
        return resources
