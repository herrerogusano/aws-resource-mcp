"""Uniform behavior tests for every registered service adapter."""

import json
from unittest.mock import Mock

import pytest
from botocore.session import get_session
from botocore.validate import validate_parameters

from aws_resource_mcp.aws.adapters.base import AdapterContext
from aws_resource_mcp.aws.adapters.registry import ADAPTERS

ROOT_FIELDS = {
    "id", "arn", "name", "service", "resource_type", "region", "account_id",
    "state", "created_at", "sources", "details", "cost_indicators", "activity",
}


def _empty(service: str, operation: str) -> dict:
    if operation.startswith("GetBucket"):
        return {}
    keys = {
        "ListFunctions": "Functions", "ListBuckets": "Buckets",
        "DescribeInstances": "Reservations", "DescribeVolumes": "Volumes",
        "DescribeVpcs": "Vpcs", "DescribeSubnets": "Subnets",
        "DescribeNatGateways": "NatGateways", "DescribeInternetGateways": "InternetGateways",
        "DescribeAddresses": "Addresses", "DescribeVpcEndpoints": "VpcEndpoints",
        "DescribeRouteTables": "RouteTables", "DescribeDBInstances": "DBInstances",
        "DescribeDBClusters": "DBClusters", "DescribeDBSnapshots": "DBSnapshots",
        "ListTables": "TableNames", "ListClusters": "clusterArns",
        "ListServices": "serviceArns", "ListTasks": "taskArns",
        "GetRestApis": "items", "GetApis": "Items", "GetStages": "Items",
        "ListStacks": "StackSummaries", "ListStackResources": "StackResourceSummaries",
        "ListQueues": "QueueUrls", "ListTopics": "Topics",
        "ListSubscriptionsByTopic": "Subscriptions", "ListUsers": "Users",
        "ListRoles": "Roles", "ListPolicies": "Policies",
        "ListHostedZones": "HostedZones",
    }
    if operation == "ListDistributions":
        return {"DistributionList": {"Items": []}}
    return {keys.get(operation, "Items"): []}


def _context(responses: dict[tuple[str, str], list[dict] | dict] | None = None) -> Mock:
    configured = responses or {}
    context = Mock(spec=AdapterContext)
    context.account_id = "111122223333"
    context.regions = ["eu-west-1"]
    context.primary_region = "eu-west-1"
    context.include_details = True
    context.include_cost_indicators = True

    service_models: dict[str, object] = {}

    def call(service: str, operation: str, **parameters: object) -> dict:
        parameters.pop("region", None)
        model = service_models.setdefault(
            service, get_session().get_service_model(service)
        )
        operation_model = model.operation_model(operation)  # type: ignore[union-attr]
        validate_parameters(parameters, operation_model.input_shape)
        response = configured.get((service, operation))
        if isinstance(response, list):
            return response.pop(0)
        return response if response is not None else _empty(service, operation)

    context.call.side_effect = call
    return context


@pytest.mark.parametrize("name", list(ADAPTERS))
def test_every_adapter_supports_an_empty_account(name: str) -> None:
    assert ADAPTERS[name].discover(_context()) == []


ADAPTER_CASES = [
    ("lambda", {("lambda", "ListFunctions"): {"Functions": [{"FunctionName": "fn", "FunctionArn": "arn:aws:lambda:eu-west-1:111122223333:function:fn", "MemorySize": 4096}]}}, "AWS::Lambda::Function"),
    ("s3", {("s3", "ListBuckets"): {"Buckets": [{"Name": "bucket", "CreationDate": "2026-01-01T00:00:00+00:00"}]}, ("s3", "GetBucketLocation"): {"LocationConstraint": "eu-west-1"}, ("s3", "GetBucketVersioning"): {"Status": "Enabled"}}, "AWS::S3::Bucket"),
    ("ec2", {("ec2", "DescribeInstances"): {"Reservations": [{"Instances": [{"InstanceId": "i-1", "State": {"Name": "running"}, "PublicIpAddress": "192.0.2.1"}]}]}}, "AWS::EC2::Instance"),
    ("rds", {("rds", "DescribeDBInstances"): {"DBInstances": [{"DBInstanceIdentifier": "db", "DBInstanceArn": "arn:db", "DBInstanceStatus": "available"}]}}, "AWS::RDS::DBInstance"),
    ("dynamodb", {("dynamodb", "ListTables"): {"TableNames": ["table"]}, ("dynamodb", "DescribeTable"): {"Table": {"TableName": "table", "TableId": "id", "TableArn": "arn:table", "TableStatus": "ACTIVE"}}, ("dynamodb", "DescribeContinuousBackups"): {"ContinuousBackupsDescription": {}}}, "AWS::DynamoDB::Table"),
    ("ecs", {("ecs", "ListClusters"): {"clusterArns": ["arn:cluster"]}, ("ecs", "DescribeClusters"): {"clusters": [{"clusterArn": "arn:cluster", "clusterName": "cluster", "status": "ACTIVE"}]}}, "AWS::ECS::Cluster"),
    ("apigateway", {("apigateway", "GetRestApis"): {"items": [{"id": "api", "name": "api"}]}, ("apigateway", "GetStages"): {"item": []}}, "AWS::ApiGateway::RestApi"),
    ("cloudformation", {("cloudformation", "ListStacks"): {"StackSummaries": [{"StackName": "stack", "StackId": "arn:stack", "StackStatus": "CREATE_COMPLETE"}]}, ("cloudformation", "ListStackResources"): {"StackResourceSummaries": [{}]}}, "AWS::CloudFormation::Stack"),
    ("sqs", {("sqs", "ListQueues"): {"QueueUrls": ["https://sqs.eu-west-1.amazonaws.com/111122223333/queue"]}, ("sqs", "GetQueueAttributes"): {"Attributes": {"QueueArn": "arn:queue", "ApproximateNumberOfMessages": "1", "MessageRetentionPeriod": "345600"}}}, "AWS::SQS::Queue"),
    ("sns", {("sns", "ListTopics"): {"Topics": [{"TopicArn": "arn:aws:sns:eu-west-1:111122223333:topic"}]}, ("sns", "ListSubscriptionsByTopic"): {"Subscriptions": [{}, {}]}}, "AWS::SNS::Topic"),
    ("iam", {("iam", "ListUsers"): {"Users": [{"UserId": "user-id", "UserName": "user", "Arn": "arn:user"}]}}, "AWS::IAM::User"),
    ("cloudfront", {("cloudfront", "ListDistributions"): {"DistributionList": {"Items": [{"Id": "dist", "ARN": "arn:dist", "Enabled": True, "Status": "Deployed"}]}}}, "AWS::CloudFront::Distribution"),
    ("route53", {("route53", "ListHostedZones"): {"HostedZones": [{"Id": "/hostedzone/zone", "Name": "example.com.", "ResourceRecordSetCount": 3}]}}, "AWS::Route53::HostedZone"),
]


@pytest.mark.parametrize(("name", "responses", "expected_type"), ADAPTER_CASES)
def test_every_adapter_normalizes_resources_and_serializes(
    name: str,
    responses: dict[tuple[str, str], dict],
    expected_type: str,
) -> None:
    resources = ADAPTERS[name].discover(_context(responses))

    assert resources
    resource = next(item for item in resources if item["resource_type"] == expected_type)
    assert set(resource) == ROOT_FIELDS
    assert resource["service"] == name
    assert resource["activity"] == {"status": "not_analyzed"}
    assert isinstance(resource["details"], dict)
    assert all(indicator["actual_cost_confirmed"] is False for indicator in resource["cost_indicators"])
    json.dumps(resources)


def test_adapter_pagination_keeps_multiple_resources() -> None:
    responses = {
        ("lambda", "ListFunctions"): [
            {"Functions": [{"FunctionName": "one", "FunctionArn": "arn:one"}], "NextMarker": "next"},
            {"Functions": [{"FunctionName": "two", "FunctionArn": "arn:two"}]},
        ]
    }
    resources = ADAPTERS["lambda"].discover(_context(responses))
    assert [item["name"] for item in resources] == ["one", "two"]


def test_service_details_never_expose_sensitive_payloads() -> None:
    serialized = json.dumps(
        ADAPTERS["lambda"].discover(
            _context({("lambda", "ListFunctions"): {"Functions": [{"FunctionName": "fn", "Environment": {"Variables": {"SECRET": "value"}}}]}})
        )
    ).lower()
    assert "environment" not in serialized
    assert "secret" not in serialized
