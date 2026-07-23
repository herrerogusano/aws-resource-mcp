"""API Gateway, CloudFormation, SQS, and SNS adapters."""

import json

from aws_resource_mcp.aws.adapters.base import ActivityField, AdapterContext, AdapterMetadata, BaseAdapter, pages
from aws_resource_mcp.models import Resource, cost_indicator, make_resource


class ApiGatewayAdapter(BaseAdapter):
    metadata = AdapterMetadata(
        service_name="apigateway",
        scope="regional",
        operations=(("apigateway", "GetRestApis"), ("apigateway", "GetStages"), ("apigatewayv2", "GetApis"), ("apigatewayv2", "GetStages")),
        resource_types=("AWS::ApiGateway::RestApi", "AWS::ApiGatewayV2::Api", "AWS::ApiGateway::Stage", "AWS::ApiGatewayV2::Stage"),
        detail_fields=("protocol_type", "endpoint_types", "stages", "cache_cluster_enabled"),
        cost_indicator_types=("provisioned_api_cache",),
    )

    def discover(self, context: AdapterContext) -> list[Resource]:
        resources: list[Resource] = []
        for region in self.regions(context):
            rest_apis = pages(context, "apigateway", "GetRestApis", "items", region=region, request_token="position", response_token="position")
            for api in rest_apis:
                api_id = api.get("id")
                stages = pages(context, "apigateway", "GetStages", "item", region=region, parameters={"restApiId": api_id}) if api_id else []
                cache_enabled = any(stage.get("cacheClusterEnabled") for stage in stages)
                indicators = [cost_indicator("provisioned_api_cache", "medium", "An API Gateway cache cluster can generate hourly charges.")] if context.include_cost_indicators and cache_enabled else []
                resources.append(make_resource(
                    service="apigateway", resource_type="AWS::ApiGateway::RestApi", region=region,
                    source="apigateway_api", identifier=api_id,
                    arn=f"arn:aws:apigateway:{region}::/restapis/{api_id}" if api_id else None,
                    name=api.get("name"), account_id=context.account_id, state="available", created_at=api.get("createdDate"),
                    details={"protocol_type": "REST", "endpoint_types": api.get("endpointConfiguration", {}).get("types", []), "stages": [stage.get("stageName") for stage in stages], "cache_cluster_enabled": cache_enabled} if context.include_details else {},
                    cost_indicators=indicators,
                ))
            v2_apis = pages(context, "apigatewayv2", "GetApis", "Items", region=region, request_token="NextToken", response_token="NextToken")
            for api in v2_apis:
                api_id = api.get("ApiId")
                stages = pages(context, "apigatewayv2", "GetStages", "Items", region=region, parameters={"ApiId": api_id}) if api_id else []
                resources.append(make_resource(
                    service="apigateway", resource_type="AWS::ApiGatewayV2::Api", region=region,
                    source="apigateway_api", identifier=api_id,
                    arn=f"arn:aws:apigateway:{region}::/apis/{api_id}" if api_id else None,
                    name=api.get("Name"), account_id=context.account_id, state="available", created_at=api.get("CreatedDate"),
                    details={"protocol_type": api.get("ProtocolType"), "stages": [stage.get("StageName") for stage in stages], "disable_execute_api_endpoint": api.get("DisableExecuteApiEndpoint")} if context.include_details else {},
                ))
        return resources


class CloudFormationAdapter(BaseAdapter):
    metadata = AdapterMetadata(
        service_name="cloudformation",
        scope="regional",
        operations=(("cloudformation", "ListStacks"), ("cloudformation", "ListStackResources")),
        resource_types=("AWS::CloudFormation::Stack",),
        detail_fields=("resources_count", "drift_status", "termination_protection"),
        activity_fields=(ActivityField(
            "last_updated_at", "configuration_change", "LastUpdatedTime", "medium"
        ),),
    )
    _ACTIVE_STATUSES = (
        "CREATE_IN_PROGRESS", "CREATE_FAILED", "CREATE_COMPLETE", "ROLLBACK_IN_PROGRESS",
        "ROLLBACK_FAILED", "ROLLBACK_COMPLETE", "DELETE_IN_PROGRESS", "DELETE_FAILED",
        "UPDATE_IN_PROGRESS", "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS", "UPDATE_COMPLETE",
        "UPDATE_FAILED", "UPDATE_ROLLBACK_IN_PROGRESS", "UPDATE_ROLLBACK_FAILED",
        "UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS", "UPDATE_ROLLBACK_COMPLETE",
        "REVIEW_IN_PROGRESS", "IMPORT_IN_PROGRESS", "IMPORT_COMPLETE", "IMPORT_ROLLBACK_IN_PROGRESS",
        "IMPORT_ROLLBACK_FAILED", "IMPORT_ROLLBACK_COMPLETE",
    )

    def discover(self, context: AdapterContext) -> list[Resource]:
        resources: list[Resource] = []
        for region in self.regions(context):
            stacks = pages(context, "cloudformation", "ListStacks", "StackSummaries", region=region, parameters={"StackStatusFilter": list(self._ACTIVE_STATUSES)})
            for stack in stacks:
                name = stack.get("StackName")
                stack_resources = pages(context, "cloudformation", "ListStackResources", "StackResourceSummaries", region=region, parameters={"StackName": name}) if name else []
                resources.append(make_resource(
                    service="cloudformation", resource_type="AWS::CloudFormation::Stack", region=region,
                    source="cloudformation_api", identifier=stack.get("StackId") or name, arn=stack.get("StackId"),
                    name=name, account_id=context.account_id, state=stack.get("StackStatus"), created_at=stack.get("CreationTime"),
                    details={"last_updated_at": stack.get("LastUpdatedTime").isoformat() if hasattr(stack.get("LastUpdatedTime"), "isoformat") else stack.get("LastUpdatedTime"), "deletion_time": stack.get("DeletionTime").isoformat() if hasattr(stack.get("DeletionTime"), "isoformat") else stack.get("DeletionTime"), "resources_count": len(stack_resources), "drift_status": stack.get("DriftInformation", {}).get("StackDriftStatus")} if context.include_details else {},
                ))
        return resources


class SQSAdapter(BaseAdapter):
    metadata = AdapterMetadata(
        service_name="sqs", scope="regional",
        operations=(("sqs", "ListQueues"), ("sqs", "GetQueueAttributes")),
        resource_types=("AWS::SQS::Queue",),
        detail_fields=("fifo", "approximate_messages", "retention_seconds", "dead_letter_queue"),
        cost_indicator_types=("queued_messages",),
    )

    def discover(self, context: AdapterContext) -> list[Resource]:
        resources: list[Resource] = []
        for region in self.regions(context):
            urls = pages(context, "sqs", "ListQueues", "QueueUrls", region=region)
            for url in urls:
                attributes = context.call("sqs", "GetQueueAttributes", region=region, QueueUrl=url, AttributeNames=["QueueArn", "ApproximateNumberOfMessages", "MessageRetentionPeriod", "RedrivePolicy", "FifoQueue", "CreatedTimestamp"] ).get("Attributes", {})
                arn = attributes.get("QueueArn")
                name = url.rstrip("/").rsplit("/", 1)[-1]
                approximate = int(attributes.get("ApproximateNumberOfMessages", "0"))
                redrive = attributes.get("RedrivePolicy")
                has_dlq = bool(json.loads(redrive).get("deadLetterTargetArn")) if redrive else False
                indicators = [cost_indicator("queued_messages", "low", "A queue with retained messages can continue consuming request and storage capacity.")] if context.include_cost_indicators and approximate > 0 else []
                resources.append(make_resource(
                    service="sqs", resource_type="AWS::SQS::Queue", region=region, source="sqs_api",
                    identifier=name, arn=arn, name=name, account_id=context.account_id, state="available",
                    created_at=attributes.get("CreatedTimestamp"),
                    details={"fifo": attributes.get("FifoQueue") == "true", "approximate_messages": approximate, "retention_seconds": int(attributes.get("MessageRetentionPeriod", "0")), "dead_letter_queue": has_dlq} if context.include_details else {},
                    cost_indicators=indicators,
                ))
        return resources


class SNSAdapter(BaseAdapter):
    metadata = AdapterMetadata(
        service_name="sns", scope="regional",
        operations=(("sns", "ListTopics"), ("sns", "ListSubscriptionsByTopic")),
        resource_types=("AWS::SNS::Topic",), detail_fields=("fifo", "subscriptions_count"),
    )

    def discover(self, context: AdapterContext) -> list[Resource]:
        resources: list[Resource] = []
        for region in self.regions(context):
            topics = pages(context, "sns", "ListTopics", "Topics", region=region)
            for topic in topics:
                arn = topic.get("TopicArn")
                name = arn.rsplit(":", 1)[-1] if arn else None
                subscriptions = pages(context, "sns", "ListSubscriptionsByTopic", "Subscriptions", region=region, parameters={"TopicArn": arn}) if arn else []
                resources.append(make_resource(
                    service="sns", resource_type="AWS::SNS::Topic", region=region, source="sns_api",
                    identifier=name, arn=arn, name=name, account_id=context.account_id, state="available",
                    details={"fifo": bool(name and name.endswith(".fifo")), "subscriptions_count": len(subscriptions)} if context.include_details else {},
                ))
        return resources
