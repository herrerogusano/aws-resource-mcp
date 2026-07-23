"""Tests for exact, bounded operation authorization."""

from unittest.mock import Mock

import pytest

from aws_resource_mcp.aws.operations import (
    OperationBlockedError,
    OperationGuard,
    OperationLimitError,
    ScopedOperationAuthorization,
)


def _guard(*, max_requests: int = 1, max_pages: int = 0) -> OperationGuard:
    authorization = ScopedOperationAuthorization(
        allowed_operations=frozenset({("s3", "ListBuckets")}),
        allowed_regions=frozenset(),
        max_requests=max_requests,
        max_additional_pages=max_pages,
    )
    return OperationGuard(scoped_authorization=authorization)


def test_scoped_grant_allows_only_the_exact_operation() -> None:
    client = Mock()
    client.list_buckets.return_value = {"Buckets": []}
    guard = _guard()

    guard.call(client, service="s3", operation="ListBuckets")
    client.list_buckets.assert_called_once_with()

    with pytest.raises(OperationBlockedError):
        guard.call(client, service="s3", operation="GetBucketVersioning", Bucket="x")


def test_request_and_pagination_budgets_stop_before_boto3() -> None:
    client = Mock()
    client.list_buckets.return_value = {"Buckets": []}
    guard = _guard(max_requests=2, max_pages=0)

    guard.call(client, service="s3", operation="ListBuckets")
    with pytest.raises(OperationLimitError):
        guard.call(
            client,
            service="s3",
            operation="ListBuckets",
            pagination=True,
            ContinuationToken="token",
        )
    assert client.list_buckets.call_count == 1


def test_free_only_mode_is_not_persistently_changed() -> None:
    guard = _guard()
    assert guard.cost_mode == "free-only"
    assert guard.paid_operations_confirmed is False
