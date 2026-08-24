"""Central allowlist and zero-cost guard for every Boto3 operation."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Literal

from aws_resource_mcp.config import DEFAULT_COST_MODE, VALID_COST_MODES

CostClassification = Literal["free", "potentially_billable", "unknown", "write"]
OperationAccess = Literal["read", "write"]
OperationScope = Literal["regional", "global"]
SensitiveDataRisk = Literal["low", "medium", "high"]
PolicyTarget = Literal["free-only", "consented-readonly", "excluded"]

IAM_VERIFIED_AT = "2026-07-23"
SERVICE_REFERENCE_ROOT = (
    "https://servicereference.us-east-1.amazonaws.com/v1"
)


@dataclass(frozen=True)
class OperationSpec:
    service: str
    operation: str
    method: str
    access: OperationAccess
    cost_classification: CostClassification
    enabled_in_free_only: bool
    iam_actions: tuple[str, ...] = ()
    capability: str = "unknown"
    component: str = "unknown"
    tools: tuple[str, ...] = ()
    scope: OperationScope = "global"
    stage: str = "unknown"
    sensitive_data_risk: SensitiveDataRisk = "high"
    resource_scope: str = "all"
    supports_resource_arn: bool = False
    condition_keys: tuple[str, ...] = ()
    dependent_actions: tuple[str, ...] = ()
    alternative_iam_actions: tuple[str, ...] = ()
    policy_target: PolicyTarget = "excluded"
    consent_required: bool = False
    justification: str = ""
    wildcard_justification: str = ""
    exclusion_reason: str | None = "Unverified operation metadata."
    verified_at: str = ""
    reference_url: str = ""


def _reference_url(service: str) -> str:
    reference_service = {
        "apigatewayv2": "apigateway",
        "accessanalyzer": "access-analyzer",
    }.get(service, service)
    return (
        f"{SERVICE_REFERENCE_ROOT}/{reference_service}/"
        f"{reference_service}.json"
    )


def _spec(
    service: str,
    operation: str,
    method: str,
    *,
    capability: str,
    component: str,
    tools: tuple[str, ...],
    scope: OperationScope,
    stage: str,
    cost: CostClassification = "free",
    iam_actions: tuple[str, ...] | None = None,
    sensitive_data_risk: SensitiveDataRisk = "low",
    supports_resource_arn: bool = False,
    condition_keys: tuple[str, ...] = (),
    dependent_actions: tuple[str, ...] = (),
    alternative_iam_actions: tuple[str, ...] = (),
    policy_target: PolicyTarget | None = None,
    justification: str = "Required by an implemented read-only MCP capability.",
    wildcard_justification: str = (
        "The operation discovers resources before their ARNs are known or "
        "does not support resource-level IAM permissions."
    ),
    exclusion_reason: str | None = None,
) -> OperationSpec:
    target = policy_target or (
        "free-only" if cost == "free" else "consented-readonly"
    )
    return OperationSpec(
        service=service,
        operation=operation,
        method=method,
        access="read",
        cost_classification=cost,
        enabled_in_free_only=cost == "free",
        iam_actions=iam_actions or (f"{service}:{operation}",),
        capability=capability,
        component=component,
        tools=tools,
        scope=scope,
        stage=stage,
        sensitive_data_risk=sensitive_data_risk,
        resource_scope="all",
        supports_resource_arn=supports_resource_arn,
        condition_keys=condition_keys,
        dependent_actions=dependent_actions,
        alternative_iam_actions=alternative_iam_actions,
        policy_target=target,
        consent_required=target == "consented-readonly",
        justification=justification,
        wildcard_justification=wildcard_justification,
        exclusion_reason=exclusion_reason,
        verified_at=IAM_VERIFIED_AT,
        reference_url=_reference_url(service),
    )


def _group(
    entries: tuple[tuple[str, str, str], ...],
    **metadata: Any,
) -> tuple[OperationSpec, ...]:
    action_overrides = metadata.pop("action_overrides", {})
    resource_arn_operations = set(metadata.pop("resource_arn_operations", ()))
    alternative_actions = metadata.pop("alternative_actions", {})
    return tuple(
        _spec(
            service,
            operation,
            method,
            iam_actions=action_overrides.get(operation),
            supports_resource_arn=operation in resource_arn_operations,
            alternative_iam_actions=alternative_actions.get(operation, ()),
            **metadata,
        )
        for service, operation, method in entries
    )


_OPERATION_SPECS = (
    _spec(
        "sts",
        "GetCallerIdentity",
        "get_caller_identity",
        capability="identity",
        component="aws.identity",
        tools=("health_check", "listar_recursos_aws"),
        scope="global",
        stage="identity",
        policy_target="excluded",
        justification="Binds results and consent to the current caller identity.",
        exclusion_reason=(
            "AWS documents that GetCallerIdentity returns caller information "
            "without an explicit Allow statement."
        ),
    ),
    _spec(
        "ec2",
        "DescribeRegions",
        "describe_regions",
        capability="regions",
        component="aws.regions",
        tools=("listar_recursos_aws", "diagnosticar_cobertura_aws"),
        scope="regional",
        stage="diagnostics",
        condition_keys=("aws:RequestedRegion",),
    ),
    *_group(
        (
            ("resource-explorer-2", "ListIndexes", "list_indexes"),
            ("resource-explorer-2", "ListViews", "list_views"),
            (
                "resource-explorer-2",
                "ListSupportedResourceTypes",
                "list_supported_resource_types",
            ),
            ("resource-explorer-2", "Search", "search"),
        ),
        capability="inventory.discovery.resource_explorer",
        component="aws.resource_explorer",
        tools=("listar_recursos_aws", "diagnosticar_cobertura_aws"),
        scope="regional",
        stage="discovery",
        condition_keys=("aws:RequestedRegion",),
        resource_arn_operations=("Search",),
    ),
    *_group(
        (("lambda", "ListFunctions", "list_functions"),),
        capability="inventory.discovery.lambda",
        component="adapter:lambda",
        tools=("listar_recursos_aws", "analizar_actividad_recursos"),
        scope="regional",
        stage="discovery",
        condition_keys=("aws:RequestedRegion",),
    ),
    *_group(
        (
            ("ec2", "DescribeInstances", "describe_instances"),
            ("ec2", "DescribeVolumes", "describe_volumes"),
            ("ec2", "DescribeVpcs", "describe_vpcs"),
            ("ec2", "DescribeSubnets", "describe_subnets"),
            ("ec2", "DescribeNatGateways", "describe_nat_gateways"),
            ("ec2", "DescribeInternetGateways", "describe_internet_gateways"),
            ("ec2", "DescribeAddresses", "describe_addresses"),
            ("ec2", "DescribeVpcEndpoints", "describe_vpc_endpoints"),
            ("ec2", "DescribeRouteTables", "describe_route_tables"),
        ),
        capability="inventory.discovery.ec2",
        component="adapter:ec2",
        tools=("listar_recursos_aws", "analizar_actividad_recursos"),
        scope="regional",
        stage="discovery",
        condition_keys=("aws:RequestedRegion",),
    ),
    *_group(
        (
            ("rds", "DescribeDBInstances", "describe_db_instances"),
            ("rds", "DescribeDBClusters", "describe_db_clusters"),
            ("rds", "DescribeDBSnapshots", "describe_db_snapshots"),
        ),
        capability="inventory.discovery.rds",
        component="adapter:rds",
        tools=("listar_recursos_aws", "analizar_actividad_recursos"),
        scope="regional",
        stage="discovery",
        condition_keys=("aws:RequestedRegion",),
    ),
    *_group(
        (
            ("dynamodb", "ListTables", "list_tables"),
            ("dynamodb", "DescribeTable", "describe_table"),
            (
                "dynamodb",
                "DescribeContinuousBackups",
                "describe_continuous_backups",
            ),
        ),
        capability="inventory.discovery.dynamodb",
        component="adapter:dynamodb",
        tools=("listar_recursos_aws", "analizar_actividad_recursos"),
        scope="regional",
        stage="discovery",
        condition_keys=("aws:RequestedRegion",),
        resource_arn_operations=("DescribeTable", "DescribeContinuousBackups"),
        alternative_actions={
            "DescribeTable": (
                "dynamodb:ReadDataForReplication",
                "dynamodb:ReplicateSettings",
            )
        },
    ),
    *_group(
        (
            ("ecs", "ListClusters", "list_clusters"),
            ("ecs", "DescribeClusters", "describe_clusters"),
            ("ecs", "ListServices", "list_services"),
            ("ecs", "DescribeServices", "describe_services"),
            ("ecs", "ListTasks", "list_tasks"),
            ("ecs", "DescribeTasks", "describe_tasks"),
        ),
        capability="inventory.discovery.ecs",
        component="adapter:ecs",
        tools=("listar_recursos_aws", "analizar_actividad_recursos"),
        scope="regional",
        stage="discovery",
        condition_keys=("aws:RequestedRegion",),
        resource_arn_operations=(
            "DescribeClusters",
            "ListServices",
            "DescribeServices",
            "ListTasks",
            "DescribeTasks",
        ),
    ),
    *_group(
        (
            ("apigateway", "GetRestApis", "get_rest_apis"),
            ("apigateway", "GetStages", "get_stages"),
            ("apigatewayv2", "GetApis", "get_apis"),
            ("apigatewayv2", "GetStages", "get_stages"),
        ),
        capability="inventory.discovery.apigateway",
        component="adapter:apigateway",
        tools=("listar_recursos_aws", "analizar_actividad_recursos"),
        scope="regional",
        stage="discovery",
        condition_keys=("aws:RequestedRegion",),
        action_overrides={
            "GetRestApis": ("apigateway:GET",),
            "GetStages": ("apigateway:GET",),
            "GetApis": ("apigateway:GET",),
        },
        resource_arn_operations=("GetRestApis", "GetStages", "GetApis"),
    ),
    *_group(
        (
            ("cloudformation", "ListStacks", "list_stacks"),
            (
                "cloudformation",
                "ListStackResources",
                "list_stack_resources",
            ),
        ),
        capability="inventory.discovery.cloudformation",
        component="adapter:cloudformation",
        tools=("listar_recursos_aws", "analizar_actividad_recursos"),
        scope="regional",
        stage="discovery",
        condition_keys=("aws:RequestedRegion",),
        resource_arn_operations=("ListStackResources",),
    ),
    *_group(
        (
            ("iam", "ListUsers", "list_users"),
            ("iam", "ListRoles", "list_roles"),
            ("iam", "ListPolicies", "list_policies"),
        ),
        capability="inventory.discovery.iam",
        component="adapter:iam",
        tools=("listar_recursos_aws", "analizar_actividad_recursos"),
        scope="global",
        stage="discovery",
        sensitive_data_risk="medium",
        wildcard_justification=(
            "IAM list operations do not support resource-level permissions; "
            "responses are minimized and anonymized by the MCP."
        ),
    ),
    *_group(
        (("cloudfront", "ListDistributions", "list_distributions"),),
        capability="inventory.discovery.cloudfront",
        component="adapter:cloudfront",
        tools=("listar_recursos_aws", "analizar_actividad_recursos"),
        scope="global",
        stage="discovery",
    ),
    *_group(
        (("route53", "ListHostedZones", "list_hosted_zones"),),
        capability="inventory.discovery.route53",
        component="adapter:route53",
        tools=("listar_recursos_aws", "analizar_actividad_recursos"),
        scope="global",
        stage="discovery",
    ),
    _spec(
        "cloudtrail",
        "LookupEvents",
        "lookup_events",
        capability="activity.free",
        component="activity.cloudtrail",
        tools=("analizar_actividad_recursos", "diagnosticar_cobertura_aws"),
        scope="regional",
        stage="activity",
        condition_keys=("aws:RequestedRegion",),
    ),
    *_group(
        (
            ("freetier", "GetFreeTierUsage", "get_free_tier_usage"),
            (
                "freetier",
                "GetAccountPlanState",
                "get_account_plan_state",
            ),
        ),
        capability="free_tier",
        component="economics.free_tier",
        tools=("revisar_free_tier", "analizar_riesgo_costes"),
        scope="global",
        stage="free_tier",
        sensitive_data_risk="medium",
        alternative_actions={
            "GetFreeTierUsage": ("aws-portal:ViewBilling",)
        },
        wildcard_justification=(
            "Free Tier is an account-level API and does not support resource ARNs."
        ),
    ),
    *_group(
        (("s3", "ListBuckets", "list_buckets"),),
        capability="inventory.discovery.s3",
        component="adapter:s3",
        tools=("listar_recursos_aws",),
        scope="global",
        stage="discovery",
        cost="potentially_billable",
        action_overrides={"ListBuckets": ("s3:ListAllMyBuckets",)},
        wildcard_justification=(
            "Listing account buckets occurs before bucket ARNs are known and "
            "ListAllMyBuckets requires Resource '*'."
        ),
    ),
    _spec(
        "s3",
        "GetBucketLocation",
        "get_bucket_location",
        capability="inventory.enrichment.s3",
        component="aws.resource_explorer",
        tools=("listar_recursos_aws",),
        scope="global",
        stage="enrichment",
        cost="potentially_billable",
        supports_resource_arn=True,
        wildcard_justification=(
            "The generic inventory can discover buckets dynamically and no "
            "bucket allowlist is configured in the generated portable policy."
        ),
    ),
    *_group(
        (
            ("s3", "GetBucketVersioning", "get_bucket_versioning"),
            (
                "s3",
                "GetBucketLifecycleConfiguration",
                "get_bucket_lifecycle_configuration",
            ),
            ("s3", "GetBucketReplication", "get_bucket_replication"),
            ("s3", "GetBucketLogging", "get_bucket_logging"),
            ("s3", "GetBucketEncryption", "get_bucket_encryption"),
            ("s3", "GetPublicAccessBlock", "get_public_access_block"),
        ),
        capability="inventory.enrichment.s3",
        component="adapter:s3",
        tools=("listar_recursos_aws",),
        scope="global",
        stage="enrichment",
        cost="potentially_billable",
        action_overrides={
            "GetBucketLifecycleConfiguration": (
                "s3:GetLifecycleConfiguration",
            ),
            "GetBucketReplication": ("s3:GetReplicationConfiguration",),
            "GetBucketEncryption": ("s3:GetEncryptionConfiguration",),
            "GetPublicAccessBlock": ("s3:GetBucketPublicAccessBlock",),
        },
        resource_arn_operations=(
            "GetBucketVersioning",
            "GetBucketLifecycleConfiguration",
            "GetBucketReplication",
            "GetBucketLogging",
            "GetBucketEncryption",
            "GetPublicAccessBlock",
        ),
        wildcard_justification=(
            "Buckets are discovered dynamically; a deployment-specific policy "
            "may replace '*' with reviewed bucket ARNs."
        ),
    ),
    *_group(
        (
            ("sqs", "ListQueues", "list_queues"),
            ("sqs", "GetQueueAttributes", "get_queue_attributes"),
        ),
        capability="inventory.discovery.sqs",
        component="adapter:sqs",
        tools=("listar_recursos_aws",),
        scope="regional",
        stage="discovery",
        cost="potentially_billable",
        condition_keys=("aws:RequestedRegion",),
        resource_arn_operations=("GetQueueAttributes",),
    ),
    *_group(
        (
            ("sns", "ListTopics", "list_topics"),
            (
                "sns",
                "ListSubscriptionsByTopic",
                "list_subscriptions_by_topic",
            ),
        ),
        capability="inventory.discovery.sns",
        component="adapter:sns",
        tools=("listar_recursos_aws",),
        scope="regional",
        stage="discovery",
        cost="potentially_billable",
        condition_keys=("aws:RequestedRegion",),
        resource_arn_operations=("ListSubscriptionsByTopic",),
    ),
    *_group(
        (
            ("cloudwatch", "GetMetricData", "get_metric_data"),
            (
                "cloudwatch",
                "GetMetricStatistics",
                "get_metric_statistics",
            ),
            ("cloudwatch", "ListMetrics", "list_metrics"),
        ),
        capability="activity.paid",
        component="activity.cloudwatch",
        tools=("analizar_actividad_recursos",),
        scope="regional",
        stage="activity",
        cost="potentially_billable",
        condition_keys=("aws:RequestedRegion",),
        policy_target="excluded",
        exclusion_reason=(
            "CloudWatch enrichment is not executable through the current "
            "consent flow."
        ),
    ),
    _spec(
        "ce",
        "GetCostAndUsage",
        "get_cost_and_usage",
        capability="cost_explorer.consented",
        component="economics.cost_explorer",
        tools=("consultar_costes_aws", "analizar_riesgo_costes"),
        scope="global",
        stage="cost_explorer",
        cost="potentially_billable",
        sensitive_data_risk="medium",
        alternative_iam_actions=("aws-portal:ViewBilling",),
        wildcard_justification=(
            "The primary billing view is account-level and the current tool "
            "does not accept a billing view ARN."
        ),
    ),
    *_group(
        (
            ("ce", "GetCostForecast", "get_cost_forecast"),
            (
                "ce",
                "GetCostAndUsageWithResources",
                "get_cost_and_usage_with_resources",
            ),
        ),
        capability="cost_explorer.future",
        component="economics.cost_explorer",
        tools=("consultar_costes_aws",),
        scope="global",
        stage="cost_explorer",
        cost="potentially_billable",
        sensitive_data_risk="medium",
        policy_target="excluded",
        alternative_actions={
            "GetCostForecast": ("aws-portal:ViewBilling",),
            "GetCostAndUsageWithResources": ("aws-portal:ViewBilling",),
        },
        exclusion_reason=(
            "Forecast and resource-level cost queries are registered but not "
            "implemented or authorizable in this phase."
        ),
    ),
    _spec(
        "accessanalyzer",
        "ValidatePolicy",
        "validate_policy",
        capability="development.policy_validation",
        component="security.validation",
        tools=(),
        scope="regional",
        stage="development",
        cost="unknown",
        iam_actions=("access-analyzer:ValidatePolicy",),
        policy_target="excluded",
        exclusion_reason=(
            "Remote validation is optional and its economic classification "
            "has not been confirmed; local validation is mandatory."
        ),
    ),
    _spec(
        "iam",
        "SimulateCustomPolicy",
        "simulate_custom_policy",
        capability="development.policy_simulation",
        component="security.validation",
        tools=(),
        scope="global",
        stage="development",
        cost="unknown",
        sensitive_data_risk="medium",
        policy_target="excluded",
        exclusion_reason=(
            "Remote simulation is optional and its economic classification "
            "has not been confirmed."
        ),
    ),
)

OPERATION_REGISTRY = {
    (spec.service, spec.operation): spec for spec in _OPERATION_SPECS
}


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
