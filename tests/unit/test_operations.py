"""Tests for the central zero-cost operation guard."""

from unittest.mock import Mock

import pytest

from aws_resource_mcp.aws.operations import (
    OPERATION_REGISTRY,
    OperationBlockedError,
    OperationGuard,
    OperationSpec,
    ScopedOperationAuthorization,
)


def test_registered_free_operation_executes_through_guard() -> None:
    client = Mock()
    client.list_functions.return_value = {"Functions": []}

    result = OperationGuard().call(client, service="lambda", operation="ListFunctions")

    assert result == {"Functions": []}
    client.list_functions.assert_called_once_with()


def test_unregistered_operation_is_blocked_before_boto3() -> None:
    client = Mock()

    with pytest.raises(OperationBlockedError) as raised:
        OperationGuard().call(client, service="ec2", operation="TerminateInstances")

    assert raised.value.error["executed"] is False
    assert raised.value.error["error_type"] == "cost_permission_required"
    client.terminate_instances.assert_not_called()


@pytest.mark.parametrize("classification", ["unknown", "write"])
def test_unknown_and_write_operations_are_always_blocked(
    monkeypatch: pytest.MonkeyPatch,
    classification: str,
) -> None:
    spec = OperationSpec(
        "example",
        "Operation",
        "operation",
        "write" if classification == "write" else "read",
        classification,  # type: ignore[arg-type]
        False,
    )
    monkeypatch.setitem(OPERATION_REGISTRY, ("example", "Operation"), spec)
    client = Mock()

    with pytest.raises(OperationBlockedError):
        OperationGuard(
            "allow-paid-with-confirmation", paid_operations_confirmed=True
        ).call(client, service="example", operation="Operation")

    client.operation.assert_not_called()


def test_potentially_billable_requires_exact_scoped_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = OperationSpec(
        "example", "Read", "read", "read", "potentially_billable", False
    )
    monkeypatch.setitem(OPERATION_REGISTRY, ("example", "Read"), spec)
    client = Mock()
    client.read.return_value = {"ok": True}

    with pytest.raises(OperationBlockedError):
        OperationGuard().call(client, service="example", operation="Read")
    with pytest.raises(OperationBlockedError):
        OperationGuard("allow-paid-with-confirmation").call(
            client, service="example", operation="Read"
        )
    with pytest.raises(OperationBlockedError):
        OperationGuard(
            "allow-paid-with-confirmation", paid_operations_confirmed=True
        ).call(client, service="example", operation="Read")
    authorization = ScopedOperationAuthorization(
        allowed_operations=frozenset({("example", "Read")}),
        allowed_regions=frozenset(),
        max_requests=1,
    )
    assert OperationGuard(scoped_authorization=authorization).call(
        client, service="example", operation="Read"
    ) == {"ok": True}
    client.read.assert_called_once_with()


@pytest.mark.parametrize("service", ["s3", "sqs", "sns"])
def test_request_metered_services_are_not_free_by_default(service: str) -> None:
    classifications = {
        spec.cost_classification
        for (registered_service, _), spec in OPERATION_REGISTRY.items()
        if registered_service == service
    }
    assert classifications == {"potentially_billable"}


def test_cloudtrail_is_free_and_cloudwatch_is_blocked() -> None:
    cloudtrail = OPERATION_REGISTRY[("cloudtrail", "LookupEvents")]
    assert cloudtrail.access == "read"
    assert cloudtrail.cost_classification == "free"
    assert cloudtrail.enabled_in_free_only is True

    client = Mock()
    for operation in ("GetMetricData", "GetMetricStatistics", "ListMetrics"):
        spec = OPERATION_REGISTRY[("cloudwatch", operation)]
        assert spec.cost_classification == "potentially_billable"
        with pytest.raises(OperationBlockedError):
            OperationGuard().call(client, service="cloudwatch", operation=operation)
    client.get_metric_data.assert_not_called()
    client.get_metric_statistics.assert_not_called()
    client.list_metrics.assert_not_called()


def test_free_tier_is_free_and_cost_explorer_requires_scoped_consent() -> None:
    for operation in ("GetFreeTierUsage", "GetAccountPlanState"):
        spec = OPERATION_REGISTRY[("freetier", operation)]
        assert spec.access == "read"
        assert spec.cost_classification == "free"
        assert spec.enabled_in_free_only is True

    for operation in (
        "GetCostAndUsage",
        "GetCostForecast",
        "GetCostAndUsageWithResources",
    ):
        spec = OPERATION_REGISTRY[("ce", operation)]
        assert spec.access == "read"
        assert spec.cost_classification == "potentially_billable"
        assert spec.enabled_in_free_only is False
