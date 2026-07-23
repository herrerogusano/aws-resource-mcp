"""Tests for ephemeral, identity-bound inventory consent."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from aws_resource_mcp.aws.consent import (
    ConsentValidationError,
    InventoryConsentStore,
    identity_fingerprint,
)
from aws_resource_mcp.aws.operations import ScopedOperationAuthorization
from aws_resource_mcp.aws.inventory import complete_inventory_with_consent


def _record(store: InventoryConsentStore, now: datetime):
    return store.create(
        identity_hash=identity_fingerprint(
            {"account_id": "123", "arn": "arn:example", "user_id": "user"}
        ),
        scope={"region": "eu-west-1", "services": ["s3"]},
        pending_operations=[
            {
                "service": "s3",
                "operation": "ListBuckets",
                "adapter": "s3",
                "regions": [],
                "estimated_max_requests": 1,
            }
        ],
        provisional_inventory={
            "account": {"account_id": "123", "arn": "arn:example"},
            "resources": [
                {
                    "service": "lambda",
                    "account_id": "123",
                    "credentials": {"aws_access_key_id": "secret"},
                }
            ],
        },
        now=now,
    )


def test_consent_is_ephemeral_single_use_and_anonymized() -> None:
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)
    store = InventoryConsentStore(ttl_seconds=60)
    record = _record(store, now)

    assert "account" not in record.provisional_inventory
    assert "account_id" not in str(record.provisional_inventory)
    assert "credentials" not in str(record.provisional_inventory)
    assert store.get(record.request_id, now=now) is record

    store.consume(record.request_id, now=now)
    with pytest.raises(ConsentValidationError, match="already"):
        store.get(record.request_id, now=now)
    with pytest.raises(ConsentValidationError, match="already"):
        store.consume(record.request_id, now=now)


def test_expired_and_cancelled_consent_cannot_be_used() -> None:
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)
    store = InventoryConsentStore(ttl_seconds=10)
    expired = _record(store, now)
    with pytest.raises(ConsentValidationError) as error:
        store.get(expired.request_id, now=now + timedelta(seconds=10))
    assert error.value.code == "consent_expired"

    active_now = datetime.now(timezone.utc)
    active = _record(store, active_now)
    store.cancel(active.request_id)
    with pytest.raises(ConsentValidationError) as error:
        store.get(active.request_id, now=active_now)
    assert error.value.code == "consent_cancelled"


def test_audit_uses_anonymized_id_and_bounded_operation_metadata() -> None:
    now = datetime.now(timezone.utc)
    store = InventoryConsentStore()
    record = _record(store, now)
    authorization = ScopedOperationAuthorization(
        allowed_operations=frozenset({("s3", "ListBuckets")}),
        allowed_regions=frozenset({"global"}),
        max_requests=1,
    )
    authorization.consume("s3", "ListBuckets", "global", pagination=False)
    store.consume(record.request_id)
    store.record_execution(record.request_id, authorization)

    audit = store.audit_events()
    assert record.request_id not in str(audit)
    assert audit[-1]["operations"] == ["s3:ListBuckets"]
    assert audit[-1]["requests_executed"] == 1
    assert audit[-1]["regions"] == ["global"]


@patch("aws_resource_mcp.aws.inventory.execute_adapters")
@patch("aws_resource_mcp.aws.inventory.get_aws_identity")
def test_continuation_rejects_a_different_aws_identity_before_adapters(
    get_identity: Mock,
    execute_adapters: Mock,
) -> None:
    store = InventoryConsentStore()
    record = store.create(
        identity_hash=identity_fingerprint(
            {"account_id": "123", "arn": "arn:original", "user_id": "user"}
        ),
        scope={
            "primary_region": "eu-west-1",
            "regions_scanned": ["eu-west-1"],
            "include_details": True,
            "include_cost_indicators": True,
            "include_account_id": False,
        },
        pending_operations=[
            {
                "service": "s3",
                "operation": "ListBuckets",
                "adapter": "s3",
                "stage": "discovery",
                "regions": ["global"],
                "estimated_max_requests": 1,
            }
        ],
        provisional_inventory={"resources": [], "coverage": {}, "errors": []},
    )
    get_identity.return_value = {
        "account_id": "999",
        "arn": "arn:different",
        "user_id": "other",
    }

    with pytest.raises(ConsentValidationError) as error:
        complete_inventory_with_consent(record, ["s3"], session=Mock())

    assert error.value.code == "consent_identity_mismatch"
    execute_adapters.assert_not_called()


@patch("aws_resource_mcp.aws.inventory.execute_adapters")
@patch("aws_resource_mcp.aws.inventory.get_aws_identity")
def test_completion_deduplicates_resources_and_preserves_previous_coverage(
    get_identity: Mock,
    execute_adapters: Mock,
) -> None:
    identity = {"account_id": "123", "arn": "arn:original", "user_id": "user"}
    store = InventoryConsentStore()
    record = store.create(
        identity_hash=identity_fingerprint(identity),
        scope={
            "primary_region": "eu-west-1",
            "regions_scanned": ["eu-west-1"],
            "include_details": True,
            "include_cost_indicators": True,
            "include_account_id": False,
        },
        pending_operations=[
            {
                "service": "s3",
                "operation": "ListBuckets",
                "adapter": "s3",
                "stage": "discovery",
                "regions": ["global"],
                "estimated_max_requests": 1,
            }
        ],
        provisional_inventory={
            "resources": [
                {
                    "service": "lambda",
                    "resource_type": "AWS::Lambda::Function",
                    "region": "eu-west-1",
                    "id": "function",
                    "name": "function",
                }
            ],
            "coverage": {"adapters": {"executed": ["lambda"]}},
            "errors": [],
        },
    )
    get_identity.return_value = identity
    execute_adapters.return_value = {
        "resources": [
            {
                "service": "s3",
                "resource_type": "AWS::S3::Bucket",
                "region": "global",
                "id": "bucket",
                "name": "bucket",
            }
        ],
        "errors": [],
        "coverage": {
            "registered": ["lambda", "s3"],
            "selected": ["s3"],
            "executed": ["s3"],
            "failed": [],
            "pending_operations": [],
            "enrichment_pending_operations": [],
            "permission_denied": [],
            "timed_out": [],
            "unavailable": [],
            "truncated": False,
            "truncations": [],
            "continuation_tokens": {},
            "operations_executed": [],
        },
    }

    inventory, _ = complete_inventory_with_consent(record, ["s3"], session=Mock())

    assert {item["service"] for item in inventory["resources"]} == {"lambda", "s3"}
    assert inventory["coverage"]["adapters"]["executed"] == ["lambda", "s3"]
