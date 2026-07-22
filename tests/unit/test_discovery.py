"""Tests for uniform resource deduplication."""

from aws_resource_mcp.aws.discovery import deduplicate_resources


def test_same_arn_is_deduplicated_without_service_specific_rules() -> None:
    arn = "arn:aws:example:eu-west-1:111122223333:resource/example"
    resources = [
        {
            "arn": arn,
            "service": "example",
            "resource_type": "example:resource",
            "region": "eu-west-1",
            "name": "example",
            "sources": ["resource_explorer:eu-west-1"],
            "details": {"first": True},
            "cost_indicators": [],
        },
        {
            "arn": arn,
            "service": "example",
            "resource_type": "example:resource",
            "region": "eu-west-1",
            "name": "example",
            "sources": ["resource_explorer:eu-central-1"],
            "details": {"second": True},
            "cost_indicators": [],
        },
    ]

    result = deduplicate_resources(resources)

    assert len(result) == 1
    assert result[0]["details"] == {"first": True, "second": True}
    assert result[0]["sources"] == [
        "resource_explorer:eu-west-1",
        "resource_explorer:eu-central-1",
    ]


def test_any_service_uses_the_same_arn_deduplication() -> None:
    resources = [
        {
            "arn": "arn:aws:s3:::bucket",
            "service": "s3",
            "region": "global",
            "name": "bucket",
            "sources": ["resource_explorer:first"],
            "details": {},
            "cost_indicators": [],
        },
        {
            "arn": "arn:aws:s3:::bucket",
            "service": "s3",
            "region": "global",
            "name": "bucket",
            "sources": ["resource_explorer:second"],
            "details": {},
            "cost_indicators": [],
        },
    ]

    assert len(deduplicate_resources(resources)) == 1


def test_resources_without_arn_use_typed_identifier() -> None:
    resources = [
        {
            "service": "ec2",
            "resource_type": "AWS::EC2::Instance",
            "region": "eu-west-1",
            "name": "one",
            "id": "i-example",
            "details": {},
            "sources": ["resource_explorer"],
        },
        {
            "service": "ec2",
            "resource_type": "AWS::EC2::Instance",
            "region": "eu-west-1",
            "name": "renamed",
            "id": "i-example",
            "details": {},
            "sources": ["resource_explorer"],
        },
    ]
    assert len(deduplicate_resources(resources)) == 1


def test_global_resources_and_same_name_in_different_regions_are_distinct() -> None:
    resources = [
        {"service": "iam", "region": "global", "name": "role", "details": {}},
        {"service": "ec2", "region": "eu-west-1", "name": "web", "details": {}},
        {"service": "ec2", "region": "eu-central-1", "name": "web", "details": {}},
    ]
    assert len(deduplicate_resources(resources)) == 3
