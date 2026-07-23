"""Tests for activity correlation, limits, and zero-cost behavior."""

import json
from datetime import UTC, datetime
from unittest.mock import Mock, patch

from aws_resource_mcp.activity.engine import (
    _inventory_for_regions,
    analyze_resource_activity,
    attach_free_activity_summaries,
)
from aws_resource_mcp.models import make_resource

NOW = datetime(2026, 7, 22, 12, tzinfo=UTC)


def aws_resource(
    service: str = "ec2",
    identifier: str = "i-test",
    created_at: str = "2026-01-01T00:00:00Z",
) -> dict:
    return make_resource(
        service=service,
        resource_type=f"AWS::{service.title()}::Resource",
        region="eu-west-1",
        source="test",
        identifier=identifier,
        state="running",
        created_at=created_at,
    )


def trail_result(events: list[dict] | None = None) -> dict:
    return {
        "events": events or [],
        "checked_regions": ["eu-west-1"],
        "errors": [],
        "operations_executed": [
            {
                "service": "cloudtrail",
                "operation": "LookupEvents",
                "region": "eu-west-1",
            }
        ],
        "lookback_days": 90,
        "truncated": False,
        "max_concurrency": 1,
    }


def event(
    timestamp: str,
    *,
    resource_id: str = "i-test",
    activity_type: str = "administrative_activity",
) -> dict:
    return {
        "timestamp": timestamp,
        "event_name": "DescribeInstances",
        "event_source": "ec2.amazonaws.com",
        "read_only": True,
        "region": "eu-west-1",
        "resource_ids": [resource_id],
        "activity_type": activity_type,
        "source": "cloudtrail_event_history",
        "confidence": "medium",
        "category": "read",
    }


def run(resources: list[dict], events: list[dict], **kwargs: object) -> dict:
    with (
        patch(
            "aws_resource_mcp.activity.engine._inventory_for_regions",
            return_value=(
                resources,
                [],
                [{"status": "complete_for_supported_resources"}],
            ),
        ),
        patch(
            "aws_resource_mcp.activity.engine.lookup_events",
            return_value=trail_result(events),
        ),
    ):
        return analyze_resource_activity(
            session=Mock(), regions=["eu-west-1"], now=NOW, **kwargs
        )


def test_recent_related_event_marks_activity_without_claiming_functional_use() -> None:
    result = run([aws_resource()], [event("2026-07-21T00:00:00Z")])
    activity = result["resources"][0]["activity"]
    assert activity["status"] == "active"
    assert activity["activity_type"] == "administrative_activity"
    assert activity["last_functional_usage_at"] is None


def test_old_related_event_can_only_create_a_candidate() -> None:
    result = run([aws_resource()], [event("2026-04-01T00:00:00Z")])
    assert result["resources"][0]["activity"]["status"] == "inactive_candidate"
    assert result["summary"]["inactive_candidates"] == 1


def test_ambiguous_event_is_not_attached_to_a_resource() -> None:
    ambiguous = event("2026-07-21T00:00:00Z")
    ambiguous["resource_ids"] = []
    result = run([aws_resource(created_at="")], [ambiguous])
    assert result["resources"][0]["activity"]["status"] == "unknown"


def test_filters_by_service_region_and_resource() -> None:
    resources = [aws_resource(identifier="i-one"), aws_resource(identifier="i-two")]
    result = run(
        resources,
        [event("2026-07-21T00:00:00Z", resource_id="i-two")],
        services=["ec2"],
        resource_ids=["i-two"],
    )
    assert [item["id"] for item in result["resources"]] == ["i-two"]


def test_administrative_events_can_be_excluded() -> None:
    result = run(
        [aws_resource(created_at="")],
        [event("2026-07-21T00:00:00Z")],
        include_administrative_events=False,
    )
    assert result["resources"][0]["activity"]["status"] == "unknown"


def test_paid_sources_flag_never_executes_cloudwatch() -> None:
    session = Mock()
    result = run([aws_resource()], [], include_paid_sources=True)
    blocked = result["coverage"]["blocked_sources"][0]
    assert blocked["status"] == "blocked_by_cost_policy"
    assert blocked["requested"] is True
    assert blocked["executed"] is False
    assert result["summary"]["paid_operations_executed"] == 0
    session.client.assert_not_called()


def test_limits_return_partial_results() -> None:
    resources = [aws_resource(identifier=f"i-{index}") for index in range(3)]
    result = run(resources, [], max_resources=2)
    assert result["status"] == "partial"
    assert result["summary"]["resources_analyzed"] == 2
    assert "Resource limit" in " ".join(result["coverage"]["limitations"])


def test_compact_inventory_summary_performs_no_deep_lookup() -> None:
    resources = [aws_resource(created_at="2026-07-21T00:00:00Z")]
    result = attach_free_activity_summaries(resources, now=NOW)
    assert result[0]["activity"]["status"] == "active"
    assert "evidence" not in result[0]["activity"]
    assert result[0]["activity"]["paid_data_executed"] is False
    json.dumps(result)


@patch("aws_resource_mcp.activity.engine.collect_general_aws_inventory")
def test_inventory_includes_global_resources_without_service_special_cases(
    collect: Mock,
) -> None:
    global_resource = aws_resource(service="s3", identifier="bucket")
    global_resource["region"] = "global"
    other_region = aws_resource(identifier="i-other")
    other_region["region"] = "us-east-1"
    collect.return_value = {
        "resources": [global_resource, other_region],
        "errors": [],
        "coverage": {},
    }

    resources, _, _ = _inventory_for_regions(Mock(), ["eu-west-1"], ["s3"])

    assert resources == [global_resource]
    assert collect.call_args.kwargs["include_global_resource_explorer_results"] is True
