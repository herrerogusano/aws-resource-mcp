"""Tests for deterministic least-privilege IAM generation."""

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from aws_resource_mcp.aws.operations import OPERATION_REGISTRY
from aws_resource_mcp.security.iam_policy_generator import (
    MANIFEST_FILENAME,
    POLICY_FILENAMES,
    PROHIBITED_SENSITIVE_ACTIONS,
    PROHIBITED_WRITE_ACTIONS,
    build_artifacts,
    build_permissions_manifest,
    build_policy,
    check_artifacts_current,
    default_iam_dir,
    generate_iam_artifacts,
    validate_policy_document,
    validate_registry_metadata,
)


def _policy_actions(policy: dict[str, object]) -> list[str]:
    statements = policy["Statement"]
    assert isinstance(statements, list)
    return [
        action
        for statement in statements
        for action in statement["Action"]
    ]


def test_checked_in_artifacts_are_current_and_json_serializable() -> None:
    assert check_artifacts_current() == []
    for path in default_iam_dir().glob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))


def test_generator_is_deterministic(tmp_path: Path) -> None:
    first = generate_iam_artifacts(tmp_path)
    snapshots = {
        name: path.read_text(encoding="utf-8") for name, path in first.items()
    }
    second = generate_iam_artifacts(tmp_path)
    assert snapshots == {
        name: path.read_text(encoding="utf-8") for name, path in second.items()
    }


def test_policies_are_narrow_read_only_and_have_no_duplicate_actions() -> None:
    artifacts = build_artifacts()
    for filename in POLICY_FILENAMES.values():
        policy = artifacts[filename]
        validate_policy_document(policy)
        actions = _policy_actions(policy)
        assert len(actions) == len(set(actions))
        assert "*" not in actions
        assert not any(action.endswith(":*") for action in actions)
        assert PROHIBITED_SENSITIVE_ACTIONS.isdisjoint(actions)
        assert PROHIBITED_WRITE_ACTIONS.isdisjoint(actions)


def test_combined_policy_is_exact_union_of_runtime_policies() -> None:
    free = set(_policy_actions(build_policy("free-only")))
    consented = set(_policy_actions(build_policy("consented-readonly")))
    combined = set(_policy_actions(build_policy("combined-readonly")))
    assert combined == free | consented
    assert free.isdisjoint(consented)


def test_sts_and_unvalidated_remote_operations_are_excluded() -> None:
    combined = set(_policy_actions(build_policy("combined-readonly")))
    assert "sts:GetCallerIdentity" not in combined
    assert "access-analyzer:ValidatePolicy" not in combined
    assert "iam:SimulateCustomPolicy" not in combined


def test_consent_policy_does_not_bypass_application_consent() -> None:
    manifest = build_permissions_manifest()
    consented = [
        item
        for item in manifest["operations"]
        if item["policy_target"] == "consented-readonly"
    ]
    assert consented
    assert all(item["consent_required"] is True for item in consented)
    assert all(item["cost_classification"] == "potentially_billable" for item in consented)


def test_manifest_covers_every_registered_operation_and_provenance() -> None:
    manifest = build_permissions_manifest()
    assert manifest["operation_count"] == len(OPERATION_REGISTRY)
    assert len(manifest["operations"]) == len(OPERATION_REGISTRY)
    assert manifest["capabilities"]
    for item in manifest["operations"]:
        assert item["iam_actions"]
        assert item["capability"] != "unknown"
        assert item["component"] != "unknown"
        assert item["verified_at"] == "2026-07-23"
        assert item["reference_url"].startswith("https://")
        if item["resource_scope"] == "all" and item["policy_target"] != "excluded":
            assert item["wildcard_justification"]


def test_alternative_actions_are_documented_but_not_granted() -> None:
    manifest = build_permissions_manifest()
    alternatives = {
        action
        for item in manifest["operations"]
        for action in item["alternative_iam_actions"]
    }
    combined = set(_policy_actions(build_policy("combined-readonly")))
    assert alternatives
    assert alternatives.isdisjoint(combined)


def test_optional_region_constraint_only_affects_regional_statements() -> None:
    policy = build_policy("free-only", allowed_regions=["eu-west-1"])
    conditioned = [
        statement for statement in policy["Statement"] if "Condition" in statement
    ]
    assert conditioned
    assert all(
        statement["Condition"]["StringEquals"]["aws:RequestedRegion"]
        == ["eu-west-1"]
        for statement in conditioned
    )
    iam_statement = next(
        statement
        for statement in policy["Statement"]
        if "iam:ListRoles" in statement["Action"]
    )
    assert "Condition" not in iam_statement


def test_dependent_actions_are_included_but_alternatives_are_not() -> None:
    key = ("ec2", "DescribeRegions")
    registry = dict(OPERATION_REGISTRY)
    registry[key] = replace(
        registry[key],
        dependent_actions=("ec2:DescribeTags",),
        alternative_iam_actions=("ec2:DescribeAccountAttributes",),
    )
    actions = set(_policy_actions(build_policy("free-only", registry=registry)))
    assert "ec2:DescribeTags" in actions
    assert "ec2:DescribeAccountAttributes" not in actions


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"iam_actions": ()}, "IAM actions are missing"),
        ({"access": "write"}, "write access"),
        ({"cost_classification": "unknown"}, "unknown/write cost"),
        ({"sensitive_data_risk": "high"}, "high-risk data"),
    ],
)
def test_generator_rejects_unverified_or_unsafe_metadata(
    changes: dict[str, object], message: str
) -> None:
    key = ("ec2", "DescribeRegions")
    registry = dict(OPERATION_REGISTRY)
    registry[key] = replace(registry[key], **changes)
    with pytest.raises(ValueError, match=message):
        validate_registry_metadata(registry)


def test_every_literal_boto_method_is_routed_through_the_guard() -> None:
    source_root = Path(__file__).resolve().parents[3] / "src" / "aws_resource_mcp"
    registered_methods = {spec.method for spec in OPERATION_REGISTRY.values()}
    direct_calls: list[str] = []
    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in registered_methods
            ):
                direct_calls.append(f"{path.name}:{node.lineno}:{node.func.attr}")
    assert direct_calls == []


def test_artifact_set_has_expected_names() -> None:
    assert set(build_artifacts()) == {
        *POLICY_FILENAMES.values(),
        MANIFEST_FILENAME,
    }
