"""Tests for the central event classifier."""

import pytest

from aws_resource_mcp.activity.classifier import classify_event


@pytest.mark.parametrize(
    ("name", "read_only", "category", "activity_type"),
    [
        ("Invoke", False, "invoke", "functional_usage"),
        ("GetObject", False, "access", "functional_usage"),
        ("DescribeInstances", True, "read", "administrative_activity"),
        ("UpdateFunctionConfiguration", False, "update", "configuration_change"),
        ("CreateTable", False, "create", "configuration_change"),
        ("DeleteBucket", False, "delete", "configuration_change"),
        ("StartInstances", False, "update", "resource_state"),
        ("SomethingNew", None, "unknown", "unknown"),
    ],
)
def test_event_classification_is_central_and_semantic(
    name: str, read_only: bool | None, category: str, activity_type: str
) -> None:
    assert classify_event(name, read_only)[:2] == (category, activity_type)
