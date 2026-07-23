"""Central allowlist and zero-cost guard for every Boto3 operation."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import monotonic
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


def _potentially_billable(service: str, operation: str, method: str) -> OperationSpec:
    return OperationSpec(
        service, operation, method, "read", "potentially_billable", False
    )


_FREE_OPERATIONS = (
    ("sts", "GetCallerIdentity", "get_caller_identity"),
    ("ec2", "DescribeRegions", "describe_regions"),
    ("resource-explorer-2", "ListIndexes", "list_indexes"),
    ("resource-explorer-2", "ListViews", "list_views"),
    (
        "resource-explorer-2",
        "ListSupportedResourceTypes",
        "list_supported_resource_types",
    ),
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
    ("cloudtrail", "LookupEvents", "lookup_events"),
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
    ("cloudwatch", "GetMetricData", "get_metric_data"),
    ("cloudwatch", "GetMetricStatistics", "get_metric_statistics"),
    ("cloudwatch", "ListMetrics", "list_metrics"),
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


class OperationLimitError(OperationBlockedError):
    """A scoped grant reached its request or pagination limit."""

    def __init__(self, service: str, operation: str, reason: str) -> None:
        super().__init__(service, operation, reason)
        self.error["error_type"] = "operation_truncated"


class OperationTimeoutError(OperationBlockedError):
    """The bounded inventory deadline was reached between AWS calls."""

    def __init__(self, service: str, operation: str) -> None:
        super().__init__(
            service,
            operation,
            "The inventory time budget was exhausted before this operation.",
        )
        self.error["error_type"] = "inventory_timeout"


@dataclass
class ScopedOperationAuthorization:
    """Single-execution authorization for exact read operations and Regions."""

    allowed_operations: frozenset[tuple[str, str]]
    allowed_regions: frozenset[str]
    max_requests: int
    max_additional_pages: int = 0
    requests_executed: int = 0
    pagination_requests_executed: int = 0
    operations_executed: set[tuple[str, str]] = field(default_factory=set)
    audit_events: list[dict[str, Any]] = field(default_factory=list)

    def permits(self, service: str, operation: str, region: str) -> bool:
        region_allowed = region == "global" or region in self.allowed_regions
        return (service, operation) in self.allowed_operations and region_allowed

    def consume(
        self,
        service: str,
        operation: str,
        region: str,
        *,
        pagination: bool,
    ) -> None:
        if not self.permits(service, operation, region):
            raise OperationBlockedError(
                service,
                operation,
                "The operation is outside the approved single-use scope.",
            )
        if self.requests_executed >= self.max_requests:
            raise OperationLimitError(
                service,
                operation,
                "The approved request limit has been reached.",
            )
        if pagination and (
            self.pagination_requests_executed >= self.max_additional_pages
        ):
            raise OperationLimitError(
                service,
                operation,
                "Additional pagination was not approved.",
            )
        self.requests_executed += 1
        if pagination:
            self.pagination_requests_executed += 1
        self.operations_executed.add((service, operation))
        self.audit_events.append(
            {
                "service": service,
                "operation": operation,
                "region": region,
                "pagination": pagination,
                "request_number": self.requests_executed,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )


class OperationGuard:
    """Enforce the central operation policy before each SDK call."""

    def __init__(
        self,
        cost_mode: str = DEFAULT_COST_MODE,
        *,
        paid_operations_confirmed: bool = False,
        scoped_authorization: ScopedOperationAuthorization | None = None,
        deadline: float | None = None,
    ) -> None:
        if cost_mode not in VALID_COST_MODES:
            raise ValueError(f"Unsupported cost mode: {cost_mode}")
        self.cost_mode = cost_mode
        self.paid_operations_confirmed = paid_operations_confirmed
        self.scoped_authorization = scoped_authorization
        self.deadline = deadline

    def require_allowed(
        self,
        *,
        service: str,
        operation: str,
        region: str = "global",
    ) -> OperationSpec:
        spec = OPERATION_REGISTRY.get((service, operation))
        if spec is None:
            raise OperationBlockedError(
                service, operation, "The operation is not registered and is blocked."
            )
        if spec.access == "write" or spec.cost_classification == "write":
            raise OperationBlockedError(
                service, operation, "Write operations are always blocked."
            )
        if spec.cost_classification == "unknown":
            raise OperationBlockedError(
                service, operation, "Unknown-cost operations are blocked."
            )
        scoped = bool(
            self.scoped_authorization
            and self.scoped_authorization.permits(service, operation, region)
        )
        if spec.cost_classification == "potentially_billable" and not scoped:
            raise OperationBlockedError(
                service,
                operation,
                "The operation may be billable and requires explicit confirmation.",
            )
        if (
            self.cost_mode == "free-only"
            and not spec.enabled_in_free_only
            and not scoped
        ):
            raise OperationBlockedError(
                service, operation, "The operation is disabled in free-only mode."
            )
        return spec

    def call(
        self,
        client: Any,
        *,
        service: str,
        operation: str,
        region: str = "global",
        pagination: bool = False,
        **parameters: Any,
    ) -> Any:
        if self.deadline is not None and monotonic() >= self.deadline:
            raise OperationTimeoutError(service, operation)
        spec = self.require_allowed(service=service, operation=operation, region=region)
        if (
            spec.cost_classification == "potentially_billable"
            and self.scoped_authorization is not None
            and self.scoped_authorization.permits(service, operation, region)
        ):
            self.scoped_authorization.consume(
                service, operation, region, pagination=pagination
            )
        return getattr(client, spec.method)(**parameters)
