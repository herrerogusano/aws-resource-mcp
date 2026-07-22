"""Central allowlist and zero-cost guard for every Boto3 operation."""

from dataclasses import dataclass
from typing import Any, Literal

from aws_resource_mcp.config import DEFAULT_COST_MODE, VALID_COST_MODES

CostClassification = Literal["free", "potentially_billable", "unknown", "write"]


@dataclass(frozen=True)
class OperationSpec:
    service: str
    operation: str
    method: str
    access: Literal["read", "write"]
    cost_classification: CostClassification
    enabled_in_free_only: bool


def _free(service: str, operation: str, method: str) -> OperationSpec:
    return OperationSpec(service, operation, method, "read", "free", True)


def _potentially_billable(
    service: str, operation: str, method: str
) -> OperationSpec:
    return OperationSpec(
        service, operation, method, "read", "potentially_billable", False
    )


_FREE_OPERATIONS = (
    ("sts", "GetCallerIdentity", "get_caller_identity"),
    ("ec2", "DescribeRegions", "describe_regions"),
    ("resource-explorer-2", "ListIndexes", "list_indexes"),
    ("resource-explorer-2", "ListViews", "list_views"),
    ("resource-explorer-2", "ListSupportedResourceTypes", "list_supported_resource_types"),
    ("resource-explorer-2", "Search", "search"),
    ("lambda", "ListFunctions", "list_functions"),
    ("ec2", "DescribeInstances", "describe_instances"),
    ("ec2", "DescribeVolumes", "describe_volumes"),
    ("ec2", "DescribeVpcs", "describe_vpcs"),
    ("ec2", "DescribeSubnets", "describe_subnets"),
    ("ec2", "DescribeNatGateways", "describe_nat_gateways"),
    ("ec2", "DescribeInternetGateways", "describe_internet_gateways"),
    ("ec2", "DescribeAddresses", "describe_addresses"),
    ("ec2", "DescribeVpcEndpoints", "describe_vpc_endpoints"),
    ("ec2", "DescribeRouteTables", "describe_route_tables"),
    ("rds", "DescribeDBInstances", "describe_db_instances"),
    ("rds", "DescribeDBClusters", "describe_db_clusters"),
    ("rds", "DescribeDBSnapshots", "describe_db_snapshots"),
    ("dynamodb", "ListTables", "list_tables"),
    ("dynamodb", "DescribeTable", "describe_table"),
    ("dynamodb", "DescribeContinuousBackups", "describe_continuous_backups"),
    ("ecs", "ListClusters", "list_clusters"),
    ("ecs", "DescribeClusters", "describe_clusters"),
    ("ecs", "ListServices", "list_services"),
    ("ecs", "DescribeServices", "describe_services"),
    ("ecs", "ListTasks", "list_tasks"),
    ("ecs", "DescribeTasks", "describe_tasks"),
    ("apigateway", "GetRestApis", "get_rest_apis"),
    ("apigateway", "GetStages", "get_stages"),
    ("apigatewayv2", "GetApis", "get_apis"),
    ("apigatewayv2", "GetStages", "get_stages"),
    ("cloudformation", "ListStacks", "list_stacks"),
    ("cloudformation", "ListStackResources", "list_stack_resources"),
    ("iam", "ListUsers", "list_users"),
    ("iam", "ListRoles", "list_roles"),
    ("iam", "ListPolicies", "list_policies"),
    ("cloudfront", "ListDistributions", "list_distributions"),
    ("route53", "ListHostedZones", "list_hosted_zones"),
)

_POTENTIALLY_BILLABLE_OPERATIONS = (
    ("s3", "ListBuckets", "list_buckets"),
    ("s3", "GetBucketLocation", "get_bucket_location"),
    ("s3", "GetBucketVersioning", "get_bucket_versioning"),
    ("s3", "GetBucketLifecycleConfiguration", "get_bucket_lifecycle_configuration"),
    ("s3", "GetBucketReplication", "get_bucket_replication"),
    ("s3", "GetBucketLogging", "get_bucket_logging"),
    ("s3", "GetBucketEncryption", "get_bucket_encryption"),
    ("s3", "GetPublicAccessBlock", "get_public_access_block"),
    ("sqs", "ListQueues", "list_queues"),
    ("sqs", "GetQueueAttributes", "get_queue_attributes"),
    ("sns", "ListTopics", "list_topics"),
    ("sns", "ListSubscriptionsByTopic", "list_subscriptions_by_topic"),
)

OPERATION_REGISTRY = {
    (service, operation): _free(service, operation, method)
    for service, operation, method in _FREE_OPERATIONS
}
OPERATION_REGISTRY.update(
    {
        (service, operation): _potentially_billable(service, operation, method)
        for service, operation, method in _POTENTIALLY_BILLABLE_OPERATIONS
    }
)


class OperationBlockedError(RuntimeError):
    """Raised before Boto3 when an operation is not allowed."""

    def __init__(self, service: str, operation: str, reason: str) -> None:
        super().__init__(reason)
        self.error = {
            "service": service,
            "operation": operation,
            "error_type": "cost_permission_required",
            "message": reason,
            "executed": False,
        }


class OperationGuard:
    """Enforce the central operation policy before each SDK call."""

    def __init__(
        self,
        cost_mode: str = DEFAULT_COST_MODE,
        *,
        paid_operations_confirmed: bool = False,
    ) -> None:
        if cost_mode not in VALID_COST_MODES:
            raise ValueError(f"Unsupported cost mode: {cost_mode}")
        self.cost_mode = cost_mode
        self.paid_operations_confirmed = paid_operations_confirmed

    def require_allowed(self, *, service: str, operation: str) -> OperationSpec:
        spec = OPERATION_REGISTRY.get((service, operation))
        if spec is None:
            raise OperationBlockedError(
                service, operation, "The operation is not registered and is blocked."
            )
        if spec.access == "write" or spec.cost_classification == "write":
            raise OperationBlockedError(service, operation, "Write operations are always blocked.")
        if spec.cost_classification == "unknown":
            raise OperationBlockedError(service, operation, "Unknown-cost operations are blocked.")
        if spec.cost_classification == "potentially_billable" and not (
            self.cost_mode == "allow-paid-with-confirmation"
            and self.paid_operations_confirmed
        ):
            raise OperationBlockedError(
                service,
                operation,
                "The operation may be billable and requires explicit confirmation.",
            )
        if self.cost_mode == "free-only" and not spec.enabled_in_free_only:
            raise OperationBlockedError(service, operation, "The operation is disabled in free-only mode.")
        return spec

    def call(self, client: Any, *, service: str, operation: str, **parameters: Any) -> Any:
        spec = self.require_allowed(service=service, operation=operation)
        return getattr(client, spec.method)(**parameters)
