"""Tests for the two-step MCP inventory consent flow."""

import json
from unittest.mock import Mock, patch

import pytest

from aws_resource_mcp.aws.consent import CONSENT_STORE
from aws_resource_mcp.aws.operations import ScopedOperationAuthorization
from aws_resource_mcp.tools.list_resources import listar_recursos_aws


@pytest.fixture(autouse=True)
def clear_consent_store():
    CONSENT_STORE.clear()
    yield
    CONSENT_STORE.clear()


def _pending_inventory() -> dict:
    pending = {
        "service": "s3",
        "operation": "ListBuckets",
        "adapter": "s3",
        "stage": "discovery",
        "scope": "global",
        "regions": [],
        "purpose": "Enumerate s3 resources",
        "cost_classification": "potentially_billable",
        "estimated_max_requests": 1,
        "pagination_possible": True,
        "executed": False,
    }
    return {
        "account": {"account_id": "123", "arn": "arn:aws:iam::123:user/test"},
        "region": "eu-west-1",
        "resources": [{"service": "lambda", "name": "function"}],
        "services": {"lambda": [{"service": "lambda", "name": "function"}]},
        "resources_by_service": {"lambda": [{"service": "lambda", "name": "function"}]},
        "coverage": {
            "status": "partial",
            "regions_scanned": ["eu-west-1"],
            "adapters": {
                "executed": ["lambda"],
                "failed": [],
                "pending_operations": [pending],
                "enrichment_pending_operations": [],
            },
        },
        "errors": [],
    }


@patch("aws_resource_mcp.tools.list_resources.collect_general_aws_inventory")
def test_first_call_returns_partial_resources_and_explicit_consent_request(
    collect: Mock,
) -> None:
    collect.return_value = _pending_inventory()

    result = listar_recursos_aws(services=["lambda", "s3"])

    assert result["status"] == "partial_pending_consent"
    assert result["all_resources"][0]["service"] == "lambda"
    assert result["consent_request"]["services"] == ["s3"]
    assert result["consent_request"]["operations"] == ["s3:ListBuckets"]
    assert result["consent_request"]["executed"] is False
    assert result["summary"]["potentially_billable_requests_executed"] == 0


@patch("aws_resource_mcp.tools.list_resources.complete_inventory_with_consent")
@patch("aws_resource_mcp.tools.list_resources.collect_general_aws_inventory")
def test_approval_is_single_use_and_reports_operations_and_requests(
    collect: Mock,
    complete: Mock,
) -> None:
    collect.return_value = _pending_inventory()
    first = listar_recursos_aws(services=["s3"])
    request_id = first["consent_request"]["consent_request_id"]
    authorization = ScopedOperationAuthorization(
        allowed_operations=frozenset({("s3", "ListBuckets")}),
        allowed_regions=frozenset(),
        max_requests=1,
    )
    authorization.requests_executed = 1
    authorization.operations_executed.add(("s3", "ListBuckets"))
    completed = _pending_inventory()
    completed["resources"] = [{"service": "s3", "name": "bucket"}]
    completed["errors"] = []
    completed["coverage"]["adapters"].update(
        {
            "executed": ["s3"],
            "pending_operations": [],
            "enrichment_pending_operations": [],
        }
    )
    complete.return_value = (completed, authorization)

    result = listar_recursos_aws(
        consent_request_id=request_id,
        consent_action="approve",
        approved_services=["s3"],
    )

    assert result["summary"]["potentially_billable_unique_operations_executed"] == 1
    assert result["summary"]["potentially_billable_requests_executed"] == 1
    complete.assert_called_once()
    reused = listar_recursos_aws(
        consent_request_id=request_id,
        consent_action="approve",
        approved_services=["s3"],
    )
    assert reused["errors"][0]["type"] == "consent_already_used"


@patch("aws_resource_mcp.tools.list_resources.complete_inventory_with_consent")
@patch("aws_resource_mcp.tools.list_resources.collect_general_aws_inventory")
def test_cancellation_makes_no_approved_aws_call(
    collect: Mock,
    complete: Mock,
) -> None:
    collect.return_value = _pending_inventory()
    first = listar_recursos_aws()

    result = listar_recursos_aws(
        consent_request_id=first["consent_request"]["consent_request_id"],
        consent_action="cancel",
    )

    assert result["status"] == "consent_cancelled"
    complete.assert_not_called()


@patch("aws_resource_mcp.tools.list_resources.collect_general_aws_inventory")
def test_legacy_confirmation_flag_does_not_execute_pending_operations(
    collect: Mock,
) -> None:
    collect.return_value = _pending_inventory()
    result = listar_recursos_aws(confirm_potentially_billable_operations=True)
    assert result["status"] == "partial_pending_consent"
    assert result["summary"]["potentially_billable_requests_executed"] == 0


@patch("aws_resource_mcp.tools.list_resources.collect_general_aws_inventory")
def test_resume_rejects_changed_original_scope(collect: Mock) -> None:
    collect.return_value = _pending_inventory()
    first = listar_recursos_aws(region="eu-west-1", services=["s3"])
    result = listar_recursos_aws(
        region="eu-central-1",
        consent_request_id=first["consent_request"]["consent_request_id"],
        consent_action="approve",
        approved_services=["s3"],
    )
    assert result["errors"][0]["type"] == "consent_scope_mismatch"


@patch("aws_resource_mcp.tools.list_resources.complete_inventory_with_consent")
@patch("aws_resource_mcp.tools.list_resources.collect_general_aws_inventory")
def test_failed_continuation_still_consumes_the_grant(
    collect: Mock,
    complete: Mock,
) -> None:
    collect.return_value = _pending_inventory()
    first = listar_recursos_aws(services=["s3"])
    request_id = first["consent_request"]["consent_request_id"]
    complete.side_effect = RuntimeError("unexpected")

    failed = listar_recursos_aws(
        consent_request_id=request_id,
        consent_action="approve",
        approved_services=["s3"],
    )
    assert failed["status"] == "error"

    reused = listar_recursos_aws(
        consent_request_id=request_id,
        consent_action="approve",
        approved_services=["s3"],
    )
    assert reused["errors"][0]["type"] == "consent_already_used"


@patch("aws_resource_mcp.tools.list_resources.complete_inventory_with_consent")
@patch("aws_resource_mcp.tools.list_resources.collect_general_aws_inventory")
def test_truncated_discovery_requires_new_page_before_enrichment(
    collect: Mock,
    complete: Mock,
) -> None:
    collect.return_value = _pending_inventory()
    first = listar_recursos_aws(services=["s3"])
    authorization = ScopedOperationAuthorization(
        allowed_operations=frozenset({("s3", "ListBuckets")}),
        allowed_regions=frozenset({"global"}),
        max_requests=1,
    )
    authorization.requests_executed = 1
    authorization.operations_executed.add(("s3", "ListBuckets"))
    completed = _pending_inventory()
    completed["coverage"]["adapters"].update(
        {
            "pending_operations": [],
            "truncations": [
                {
                    "service": "s3",
                    "operation": "ListBuckets",
                    "region": "global",
                }
            ],
            "continuation_tokens": {"s3:ListBuckets:global": "next"},
            "enrichment_pending_operations": [
                {
                    "service": "s3",
                    "operation": "GetBucketVersioning",
                    "adapter": "s3",
                    "stage": "enrichment",
                    "regions": ["global"],
                    "estimated_max_requests": 1,
                }
            ],
        }
    )
    complete.return_value = (completed, authorization)

    result = listar_recursos_aws(
        consent_request_id=first["consent_request"]["consent_request_id"],
        consent_action="approve",
        approved_services=["s3"],
    )

    assert [
        (item["operation"], item["stage"])
        for item in result["pending_operations"]
    ] == [("ListBuckets", "discovery")]
    assert result["pending_operations"][0]["continuation"] is True
    assert result["consent_request"]["pagination_request_limit"] == 1
    assert "next" not in json.dumps(result)


@patch("aws_resource_mcp.tools.list_resources.complete_inventory_with_consent")
@patch("aws_resource_mcp.tools.list_resources.collect_general_aws_inventory")
def test_partial_approval_keeps_unapproved_service_pending(
    collect: Mock,
    complete: Mock,
) -> None:
    initial = _pending_inventory()
    initial["coverage"]["adapters"]["pending_operations"].append(
        {
            "service": "sqs",
            "operation": "ListQueues",
            "adapter": "sqs",
            "stage": "discovery",
            "scope": "regional",
            "regions": ["eu-west-1"],
            "purpose": "Enumerate sqs resources",
            "cost_classification": "potentially_billable",
            "estimated_max_requests": 1,
            "pagination_possible": True,
            "executed": False,
        }
    )
    collect.return_value = initial
    first = listar_recursos_aws(services=["s3", "sqs"])
    authorization = ScopedOperationAuthorization(
        allowed_operations=frozenset({("s3", "ListBuckets")}),
        allowed_regions=frozenset({"global"}),
        max_requests=1,
    )
    completed = _pending_inventory()
    completed["coverage"]["adapters"].update(
        {"pending_operations": [], "enrichment_pending_operations": []}
    )
    complete.return_value = (completed, authorization)

    result = listar_recursos_aws(
        consent_request_id=first["consent_request"]["consent_request_id"],
        consent_action="approve",
        approved_services=["s3"],
    )

    assert result["summary"]["services_pending_consent"] == ["sqs"]
    assert result["consent_request"]["services"] == ["sqs"]
