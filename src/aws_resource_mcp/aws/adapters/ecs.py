"""ECS and Fargate adapter."""

from aws_resource_mcp.aws.adapters.base import AdapterContext, AdapterMetadata, BaseAdapter, pages
from aws_resource_mcp.models import Resource, cost_indicator, make_resource


class ECSAdapter(BaseAdapter):
    metadata = AdapterMetadata(
        service_name="ecs",
        scope="regional",
        operations=(
            ("ecs", "ListClusters"), ("ecs", "DescribeClusters"),
            ("ecs", "ListServices"), ("ecs", "DescribeServices"),
            ("ecs", "ListTasks"), ("ecs", "DescribeTasks"),
        ),
        resource_types=("AWS::ECS::Cluster", "AWS::ECS::Service", "AWS::ECS::Task"),
        detail_fields=("desired_count", "running_count", "pending_count", "launch_type", "capacity_providers", "cpu", "memory"),
        cost_indicator_types=("running_fargate_task", "desired_service_capacity", "ec2_capacity_provider"),
    )

    @staticmethod
    def _batches(items: list[str], size: int = 100) -> list[list[str]]:
        return [items[index:index + size] for index in range(0, len(items), size)]

    def discover(self, context: AdapterContext) -> list[Resource]:
        resources: list[Resource] = []
        for region in self.regions(context):
            cluster_arns = pages(context, "ecs", "ListClusters", "clusterArns", region=region, request_token="nextToken", response_token="nextToken")
            for batch in self._batches(cluster_arns):
                response = context.call("ecs", "DescribeClusters", region=region, clusters=batch, include=["ATTACHMENTS", "CONFIGURATIONS"])
                for cluster in response.get("clusters", []):
                    arn = cluster.get("clusterArn")
                    name = cluster.get("clusterName")
                    capacity = cluster.get("capacityProviders", [])
                    indicators = []
                    if context.include_cost_indicators and any(provider != "FARGATE" and provider != "FARGATE_SPOT" for provider in capacity):
                        indicators.append(cost_indicator("ec2_capacity_provider", "medium", "An EC2 capacity provider can retain billable compute capacity."))
                    resources.append(make_resource(
                        service="ecs", resource_type="AWS::ECS::Cluster", region=region, source="ecs_api",
                        identifier=name, arn=arn, name=name, account_id=context.account_id, state=cluster.get("status"),
                        details={"registered_container_instances": cluster.get("registeredContainerInstancesCount"), "running_tasks": cluster.get("runningTasksCount"), "pending_tasks": cluster.get("pendingTasksCount"), "active_services": cluster.get("activeServicesCount"), "capacity_providers": capacity} if context.include_details else {},
                        cost_indicators=indicators,
                    ))
                for cluster_arn in batch:
                    resources.extend(self._services(context, region, cluster_arn))
                    resources.extend(self._tasks(context, region, cluster_arn))
        return resources

    def _services(self, context: AdapterContext, region: str, cluster_arn: str) -> list[Resource]:
        arns = pages(context, "ecs", "ListServices", "serviceArns", region=region, parameters={"cluster": cluster_arn}, request_token="nextToken", response_token="nextToken")
        resources: list[Resource] = []
        for batch in self._batches(arns, 10):
            for service in context.call("ecs", "DescribeServices", region=region, cluster=cluster_arn, services=batch).get("services", []):
                desired = service.get("desiredCount") or 0
                launch_type = service.get("launchType")
                indicators = []
                if context.include_cost_indicators and desired > 0:
                    indicators.append(cost_indicator("desired_service_capacity", "high", "A service with desired tasks can keep compute capacity active."))
                resources.append(make_resource(
                    service="ecs", resource_type="AWS::ECS::Service", region=region, source="ecs_api",
                    identifier=service.get("serviceName"), arn=service.get("serviceArn"), name=service.get("serviceName"),
                    account_id=context.account_id, state=service.get("status"), created_at=service.get("createdAt"),
                    details={"cluster_arn": cluster_arn, "desired_count": desired, "running_count": service.get("runningCount"), "pending_count": service.get("pendingCount"), "launch_type": launch_type, "capacity_provider_strategy": [item.get("capacityProvider") for item in service.get("capacityProviderStrategy", [])], "task_definition": service.get("taskDefinition")} if context.include_details else {},
                    cost_indicators=indicators,
                ))
        return resources

    def _tasks(self, context: AdapterContext, region: str, cluster_arn: str) -> list[Resource]:
        arns = pages(context, "ecs", "ListTasks", "taskArns", region=region, parameters={"cluster": cluster_arn}, request_token="nextToken", response_token="nextToken")
        resources: list[Resource] = []
        for batch in self._batches(arns):
            for task in context.call("ecs", "DescribeTasks", region=region, cluster=cluster_arn, tasks=batch).get("tasks", []):
                launch_type = task.get("launchType")
                indicators = []
                if context.include_cost_indicators and launch_type == "FARGATE" and task.get("lastStatus") == "RUNNING":
                    indicators.append(cost_indicator("running_fargate_task", "high", "A running Fargate task can generate compute charges."))
                arn = task.get("taskArn")
                identifier = arn.rsplit("/", 1)[-1] if arn else None
                resources.append(make_resource(
                    service="ecs", resource_type="AWS::ECS::Task", region=region, source="ecs_api",
                    identifier=identifier, arn=arn, name=identifier, account_id=context.account_id,
                    state=task.get("lastStatus"), created_at=task.get("createdAt"),
                    details={"cluster_arn": cluster_arn, "desired_status": task.get("desiredStatus"), "launch_type": launch_type, "capacity_provider": task.get("capacityProviderName"), "cpu": task.get("cpu"), "memory": task.get("memory"), "task_definition": task.get("taskDefinitionArn")} if context.include_details else {},
                    cost_indicators=indicators,
                ))
        return resources
