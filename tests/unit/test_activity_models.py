"""Tests for the uniform resource activity model."""

import json
from datetime import UTC, datetime

import pytest

from aws_resource_mcp.activity.models import (
    ACTIVITY_STATUSES,
    ACTIVITY_TYPES,
    CONFIDENCE_LEVELS,
    build_activity_result,
    isoformat_utc,
    parse_timestamp,
)
from aws_resource_mcp.models import make_resource

NOW = datetime(2026, 7, 22, 12, tzinfo=UTC)


def resource(created_at: str = "2026-01-01T00:00:00Z") -> dict:
    return make_resource(
        service="ec2",
        resource_type="AWS::EC2::Instance",
        region="eu-west-1",
        source="test",
        identifier="i-test",
        created_at=created_at,
    )


def signal(
    activity_type: str,
    timestamp: str | None,
    *,
    confidence: str = "medium",
    name: str = "Example",
) -> dict:
    return {
        "timestamp": timestamp,
        "activity_type": activity_type,
        "activity_name": name,
        "source": "service_api",
        "confidence": confidence,
        "region": "eu-west-1",
        "resource_ids": ["i-test"],
    }


def result(signals: list[dict], **overrides: object) -> dict:
    arguments = {
        "now": NOW,
        "inactive_days": 30,
        "lookback_days": 90,
        "source_checked": True,
        "adapter_supported": True,
    }
    arguments.update(overrides)
    return build_activity_result(resource(), signals, **arguments)  # type: ignore[arg-type]


def test_allowed_model_values_are_complete() -> None:
    assert ACTIVITY_STATUSES == {
        "active",
        "inactive_candidate",
        "unknown",
        "not_supported",
        "blocked_by_cost_policy",
        "error",
    }
    assert ACTIVITY_TYPES == {
        "functional_usage",
        "administrative_activity",
        "configuration_change",
        "resource_state",
        "unknown",
    }
    assert CONFIDENCE_LEVELS == {"high", "medium", "low", "unknown"}


@pytest.mark.parametrize(
    "value",
    [
        "2026-07-20T10:00:00Z",
        "2026-07-20T10:00:00+00:00",
        datetime(2026, 7, 20, 10, tzinfo=UTC),
        "1784541600",
    ],
)
def test_dates_are_parsed_and_normalized(value: object) -> None:
    assert parse_timestamp(value) is not None
    assert isoformat_utc(value).endswith("Z")


@pytest.mark.parametrize(
    ("activity_type", "timestamp_field"),
    [
        ("functional_usage", "last_functional_usage_at"),
        ("administrative_activity", "last_administrative_activity_at"),
        ("configuration_change", "last_configuration_change_at"),
        ("resource_state", "last_state_change_at"),
    ],
)
def test_signal_types_keep_separate_timestamps(
    activity_type: str, timestamp_field: str
) -> None:
    activity = result([signal(activity_type, "2026-07-20T10:00:00Z")])
    assert activity["status"] == "active"
    assert activity[timestamp_field] == "2026-07-20T10:00:00Z"
    assert activity["best_known_activity_type"] == activity_type


def test_old_direct_evidence_is_only_an_inactive_candidate() -> None:
    activity = result([signal("administrative_activity", "2026-04-01T00:00:00Z")])
    assert activity["status"] == "inactive_candidate"
    assert "not proof" in " ".join(activity["limitations"])


def test_absence_of_data_is_unknown() -> None:
    activity = result([], source_checked=False)
    assert activity["status"] == "unknown"
    assert activity["confidence"] == "unknown"


def test_recent_resource_is_never_an_inactive_candidate() -> None:
    activity = build_activity_result(
        resource("2026-07-20T00:00:00Z"),
        [],
        now=NOW,
        inactive_days=30,
        lookback_days=90,
        source_checked=True,
        adapter_supported=True,
    )
    assert activity["status"] == "unknown"


def test_recent_contradictory_evidence_wins_over_old_evidence() -> None:
    activity = result(
        [
            signal("functional_usage", "2026-04-01T00:00:00Z", confidence="high"),
            signal("configuration_change", "2026-07-21T00:00:00Z"),
        ]
    )
    assert activity["status"] == "active"
    assert activity["best_known_activity_type"] == "configuration_change"
    json.dumps(activity)


def test_unsupported_and_failed_sources_are_explicit() -> None:
    assert result([], adapter_supported=False)["status"] == "not_supported"
    assert result([], source_error=True)["status"] == "error"
