"""Generate deterministic IAM policies from the central operation registry."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from aws_resource_mcp.aws.operations import OPERATION_REGISTRY, OperationSpec

POLICY_VERSION = "2012-10-17"
POLICY_FILENAMES = {
    "free-only": "aws-resource-mcp-free-only.json",
    "consented-readonly": "aws-resource-mcp-consented-readonly.json",
    "combined-readonly": "aws-resource-mcp-combined-readonly.json",
    "permissions-boundary": "aws-resource-mcp-permissions-boundary.json",
}
MANIFEST_FILENAME = "permissions-manifest.json"

PROHIBITED_SENSITIVE_ACTIONS = frozenset(
    {
        "dynamodb:GetItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "ecr:BatchGetImage",
        "kms:Decrypt",
        "lambda:GetFunction",
        "lambda:InvokeFunction",
        "logs:FilterLogEvents",
        "logs:GetLogEvents",
        "s3:GetObject",
        "secretsmanager:GetSecretValue",
        "sqs:ReceiveMessage",
        "ssm:GetParameter",
        "ssm:GetParameters",
    }
)
PROHIBITED_WRITE_ACTIONS = frozenset(
    {
        "ec2:StartInstances",
        "ec2:StopInstances",
        "ec2:TerminateInstances",
        "iam:AttachRolePolicy",
        "iam:CreateRole",
        "iam:PassRole",
        "lambda:UpdateFunctionConfiguration",
        "s3:DeleteBucket",
        "s3:DeleteObject",
        "s3:PutBucketPolicy",
        "s3:PutObject",
        "sns:Publish",
        "sqs:SendMessage",
    }
)


def default_iam_dir() -> Path:
    """Return the versioned IAM artifact directory."""
    return Path(__file__).resolve().parents[3] / "iam"


def _all_actions(spec: OperationSpec) -> tuple[str, ...]:
    return tuple(sorted(set((*spec.iam_actions, *spec.dependent_actions))))


def validate_registry_metadata(
    registry: Mapping[tuple[str, str], OperationSpec] = OPERATION_REGISTRY,
) -> None:
    """Reject incomplete or unsafe metadata before policy generation."""
    errors: list[str] = []
    for key, spec in registry.items():
        label = f"{key[0]}:{key[1]}"
        if key != (spec.service, spec.operation):
            errors.append(f"{label}: registry key and specification differ")
        if not spec.iam_actions:
            errors.append(f"{label}: IAM actions are missing")
        if not spec.capability or spec.capability == "unknown":
            errors.append(f"{label}: capability is unverified")
        if not spec.component or spec.component == "unknown":
            errors.append(f"{label}: component is unverified")
        if not spec.stage or spec.stage == "unknown":
            errors.append(f"{label}: stage is unverified")
        if not spec.verified_at or not spec.reference_url:
            errors.append(f"{label}: official verification metadata is missing")
        if spec.policy_target != "excluded" and spec.exclusion_reason:
            errors.append(f"{label}: included operation has an exclusion reason")
        if spec.policy_target == "excluded" and not spec.exclusion_reason:
            errors.append(f"{label}: excluded operation needs a reason")
        if spec.policy_target != "excluded":
            if spec.access != "read":
                errors.append(f"{label}: write access cannot enter a policy")
            if spec.cost_classification in {"unknown", "write"}:
                errors.append(f"{label}: unknown/write cost cannot enter a policy")
            if spec.sensitive_data_risk == "high":
                errors.append(f"{label}: high-risk data cannot enter a policy")
            if not spec.wildcard_justification and spec.resource_scope == "all":
                errors.append(f"{label}: wildcard resource lacks justification")
        if spec.policy_target == "free-only" and (
            spec.cost_classification != "free" or not spec.enabled_in_free_only
        ):
            errors.append(f"{label}: free-only metadata is inconsistent")
        if spec.policy_target == "consented-readonly" and not spec.consent_required:
            errors.append(f"{label}: consented operation lacks consent requirement")
        actions = _all_actions(spec)
        if PROHIBITED_SENSITIVE_ACTIONS.intersection(actions):
            errors.append(f"{label}: sensitive-content action is prohibited")
        if PROHIBITED_WRITE_ACTIONS.intersection(actions):
            errors.append(f"{label}: known write action is prohibited")
        if any(action == "*" or action.endswith(":*") for action in actions):
            errors.append(f"{label}: wildcard IAM actions are prohibited")
    if errors:
        raise ValueError("Invalid IAM operation metadata:\n- " + "\n- ".join(errors))


def _selected_specs(
    target: str,
    registry: Mapping[tuple[str, str], OperationSpec],
) -> list[OperationSpec]:
    allowed_targets = (
        {"free-only"}
        if target == "free-only"
        else {"consented-readonly"}
        if target == "consented-readonly"
        else {"free-only", "consented-readonly"}
    )
    return sorted(
        (
            spec
            for spec in registry.values()
            if spec.policy_target in allowed_targets
        ),
        key=lambda spec: (
            spec.capability,
            spec.service,
            spec.operation,
        ),
    )


def _sid(value: str, index: int) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value)
    base = "".join(word[:1].upper() + word[1:] for word in words)
    return f"{base[:56]}{index:02d}"


def build_policy(
    target: str,
    *,
    registry: Mapping[tuple[str, str], OperationSpec] = OPERATION_REGISTRY,
    allowed_regions: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build one read-only policy without contacting AWS."""
    if target not in {"free-only", "consented-readonly", "combined-readonly"}:
        raise ValueError(f"Unsupported IAM policy target: {target}")
    validate_registry_metadata(registry)
    groups: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    specs_by_group: dict[tuple[str, str, str], list[OperationSpec]] = defaultdict(list)
    for spec in _selected_specs(target, registry):
        for action in _all_actions(spec):
            iam_namespace = action.split(":", 1)[0]
            key = (spec.capability, iam_namespace, spec.resource_scope)
            groups[key].add(action)
            if spec not in specs_by_group[key]:
                specs_by_group[key].append(spec)

    statements: list[dict[str, Any]] = []
    for index, key in enumerate(sorted(groups), start=1):
        capability, service, resource = key
        specs = specs_by_group[key]
        statement: dict[str, Any] = {
            "Sid": _sid(f"{capability}-{service}", index),
            "Effect": "Allow",
            "Action": sorted(groups[key]),
            "Resource": "*" if resource == "all" else resource,
        }
        if allowed_regions and all(
            spec.scope == "regional"
            and "aws:RequestedRegion" in spec.condition_keys
            for spec in specs
        ):
            statement["Condition"] = {
                "StringEquals": {
                    "aws:RequestedRegion": sorted(set(allowed_regions))
                }
            }
        statements.append(statement)
    return {"Version": POLICY_VERSION, "Statement": statements}


def _manifest_entry(spec: OperationSpec) -> dict[str, Any]:
    entry = asdict(spec)
    entry["iam_actions"] = list(spec.iam_actions)
    entry["tools"] = list(spec.tools)
    entry["condition_keys"] = list(spec.condition_keys)
    entry["dependent_actions"] = list(spec.dependent_actions)
    entry["alternative_iam_actions"] = list(spec.alternative_iam_actions)
    entry["included_in_policies"] = (
        []
        if spec.policy_target == "excluded"
        else [spec.policy_target, "combined-readonly", "permissions-boundary"]
    )
    return entry


def build_permissions_manifest(
    registry: Mapping[tuple[str, str], OperationSpec] = OPERATION_REGISTRY,
) -> dict[str, Any]:
    """Describe policy inclusion, exclusions, provenance, and guardrails."""
    validate_registry_metadata(registry)
    operations = [
        _manifest_entry(spec)
        for spec in sorted(
            registry.values(), key=lambda spec: (spec.service, spec.operation)
        )
    ]
    capabilities: list[dict[str, Any]] = []
    for capability in sorted({spec.capability for spec in registry.values()}):
        specs = sorted(
            (
                spec
                for spec in registry.values()
                if spec.capability == capability
            ),
            key=lambda spec: (spec.service, spec.operation),
        )
        capabilities.append(
            {
                "capability": capability,
                "tools": sorted({tool for spec in specs for tool in spec.tools}),
                "components": sorted({spec.component for spec in specs}),
                "operations": [
                    f"{spec.service}:{spec.operation}" for spec in specs
                ],
                "iam_actions": sorted(
                    {action for spec in specs for action in _all_actions(spec)}
                ),
                "policy_targets": sorted(
                    {spec.policy_target for spec in specs}
                ),
                "cost_classifications": sorted(
                    {spec.cost_classification for spec in specs}
                ),
                "consent_required": any(
                    spec.consent_required for spec in specs
                ),
                "sensitive_data_risks": sorted(
                    {spec.sensitive_data_risk for spec in specs}
                ),
            }
        )
    return {
        "schema_version": 1,
        "generated_from": "aws_resource_mcp.aws.operations.OPERATION_REGISTRY",
        "policy_version": POLICY_VERSION,
        "operation_count": len(operations),
        "operations": operations,
        "capabilities": capabilities,
        "prohibited_actions": {
            "sensitive_content": sorted(PROHIBITED_SENSITIVE_ACTIONS),
            "write": sorted(PROHIBITED_WRITE_ACTIONS),
        },
        "notes": [
            "Alternative IAM actions are informational and are not granted.",
            "STS GetCallerIdentity is intentionally absent from policies.",
            "Application consent remains mandatory for consented operations.",
            "Generated policies never change IAM automatically.",
        ],
    }


def _json_text(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def build_artifacts(
    *,
    registry: Mapping[tuple[str, str], OperationSpec] = OPERATION_REGISTRY,
    allowed_regions: Sequence[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build every checked-in artifact in memory."""
    free = build_policy(
        "free-only", registry=registry, allowed_regions=allowed_regions
    )
    consented = build_policy(
        "consented-readonly", registry=registry, allowed_regions=allowed_regions
    )
    combined = build_policy(
        "combined-readonly", registry=registry, allowed_regions=allowed_regions
    )
    return {
        POLICY_FILENAMES["free-only"]: free,
        POLICY_FILENAMES["consented-readonly"]: consented,
        POLICY_FILENAMES["combined-readonly"]: combined,
        POLICY_FILENAMES["permissions-boundary"]: combined,
        MANIFEST_FILENAME: build_permissions_manifest(registry),
    }


def validate_policy_document(policy: Mapping[str, Any]) -> None:
    """Perform strict local validation of a generated policy."""
    if policy.get("Version") != POLICY_VERSION:
        raise ValueError("IAM policy version must be 2012-10-17")
    statements = policy.get("Statement")
    if not isinstance(statements, list) or not statements:
        raise ValueError("IAM policy must contain statements")
    seen: set[str] = set()
    for statement in statements:
        if statement.get("Effect") != "Allow":
            raise ValueError("Only explicit Allow statements are generated")
        actions = statement.get("Action")
        if not isinstance(actions, list) or actions != sorted(set(actions)):
            raise ValueError("IAM actions must be sorted and unique")
        if any(action == "*" or action.endswith(":*") for action in actions):
            raise ValueError("Wildcard IAM actions are prohibited")
        if PROHIBITED_SENSITIVE_ACTIONS.intersection(actions):
            raise ValueError("Sensitive-content permissions are prohibited")
        if PROHIBITED_WRITE_ACTIONS.intersection(actions):
            raise ValueError("Write permissions are prohibited")
        duplicate = seen.intersection(actions)
        if duplicate:
            raise ValueError(f"Duplicate policy actions: {sorted(duplicate)}")
        seen.update(actions)


def generate_iam_artifacts(
    output_dir: Path | None = None,
    *,
    allowed_regions: Sequence[str] | None = None,
) -> dict[str, Path]:
    """Write deterministic artifacts and return their paths."""
    destination = output_dir or default_iam_dir()
    destination.mkdir(parents=True, exist_ok=True)
    artifacts = build_artifacts(allowed_regions=allowed_regions)
    for name, artifact in artifacts.items():
        if name != MANIFEST_FILENAME:
            validate_policy_document(artifact)
        (destination / name).write_text(_json_text(artifact), encoding="utf-8")
    return {name: destination / name for name in artifacts}


def check_artifacts_current(output_dir: Path | None = None) -> list[str]:
    """Return stale or missing artifact names without modifying files."""
    destination = output_dir or default_iam_dir()
    expected = build_artifacts()
    stale: list[str] = []
    for name, artifact in expected.items():
        path = destination / name
        if not path.exists() or path.read_text(encoding="utf-8") != _json_text(artifact):
            stale.append(name)
    return stale


def iam_health_metadata() -> dict[str, Any]:
    """Expose local policy health without any AWS or IAM request."""
    try:
        validate_registry_metadata()
        stale = check_artifacts_current()
    except Exception:
        return {
            "policy_manifest_loaded": False,
            "generated_policies_current": False,
            "free_only_policy_generated": False,
            "consented_policy_generated": False,
            "local_validation": "failed",
            "policy_validation": "local_failed",
            "runtime_identity_dedicated": "unknown",
            "managed_policy_audit": "not_checked",
            "remote_validation_executed": False,
        }
    return {
        "policy_manifest_loaded": True,
        "generated_policies_current": not stale,
        "free_only_policy_generated": (
            POLICY_FILENAMES["free-only"] not in stale
        ),
        "consented_policy_generated": (
            POLICY_FILENAMES["consented-readonly"] not in stale
        ),
        "stale_artifacts": stale,
        "local_validation": "passed" if not stale else "stale",
        "policy_validation": "local_passed" if not stale else "local_stale",
        "runtime_identity_dedicated": "unknown",
        "managed_policy_audit": "not_checked",
        "remote_validation_executed": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate or check least-privilege IAM artifacts locally."
    )
    parser.add_argument("--output-dir", type=Path, default=default_iam_dir())
    parser.add_argument(
        "--allowed-region",
        action="append",
        default=[],
        help="Optionally constrain regional statements; repeat as needed.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when checked-in default artifacts are stale.",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    """CLI entry point; generation and validation are entirely local."""
    arguments = _parser().parse_args(list(argv) if argv is not None else None)
    if arguments.check:
        stale = check_artifacts_current(arguments.output_dir)
        if stale:
            print("Stale IAM artifacts: " + ", ".join(stale))
            return 1
        print("IAM artifacts are current and locally valid.")
        return 0
    paths = generate_iam_artifacts(
        arguments.output_dir,
        allowed_regions=arguments.allowed_region or None,
    )
    print(f"Generated {len(paths)} IAM artifacts in {arguments.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
