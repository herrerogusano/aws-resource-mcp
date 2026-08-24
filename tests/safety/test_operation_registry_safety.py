"""Negative safety checks for the central operation allowlist and IAM model."""

from aws_resource_mcp.aws.operations import OPERATION_REGISTRY
from aws_resource_mcp.security.iam_policy_generator import build_artifacts

FORBIDDEN_METHOD_PREFIXES = (
    "create_",
    "delete_",
    "update_",
    "put_",
    "terminate_",
    "stop_",
    "start_",
    "invoke_",
    "publish_",
    "send_",
    "attach_",
    "detach_",
    "enable_",
    "disable_",
)
SENSITIVE_READS = {
    ("s3", "GetObject"),
    ("secretsmanager", "GetSecretValue"),
    ("ssm", "GetParameter"),
    ("kms", "Decrypt"),
    ("sqs", "ReceiveMessage"),
    ("dynamodb", "GetItem"),
    ("dynamodb", "Scan"),
    ("logs", "GetLogEvents"),
}


def test_allowlist_contains_no_writes_or_sensitive_content_reads() -> None:
    for key, spec in OPERATION_REGISTRY.items():
        assert spec.access == "read", key
        assert spec.cost_classification != "write", key
        assert not spec.method.startswith(FORBIDDEN_METHOD_PREFIXES), key
        assert key not in SENSITIVE_READS


def test_generated_execution_policies_exclude_sensitive_and_write_actions() -> None:
    artifacts = build_artifacts()
    policy_text = str(
        {
            name: artifact
            for name, artifact in artifacts.items()
            if name != "permissions-manifest.json"
        }
    )
    for _, operation in SENSITIVE_READS:
        assert operation not in policy_text
    for prefix in ("Create", "Delete", "Update", "Put", "Terminate", "Invoke"):
        assert f":{prefix}" not in policy_text
