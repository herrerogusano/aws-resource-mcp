"""Central CloudTrail event classifier shared by every service adapter."""

from typing import Any, Literal

from aws_resource_mcp.models import ActivityConfidence, ActivityType

EventCategory = Literal[
    "read", "write", "create", "update", "delete", "invoke", "access", "unknown"
]

_STATE_EVENTS = {
    "startinstances",
    "stopinstances",
    "rebootinstances",
    "startdbinstance",
    "stopdbinstance",
    "runtask",
    "stoptask",
}
_FUNCTIONAL_EVENTS = {
    "invoke",
    "executeapi",
    "getobject",
    "putobject",
    "receivemessage",
    "sendmessage",
    "publish",
    "query",
    "scan",
}
_READ_PREFIXES = ("get", "list", "describe", "head", "lookup", "search")
_CREATE_PREFIXES = ("create", "run", "launch")
_UPDATE_PREFIXES = (
    "update",
    "modify",
    "put",
    "set",
    "attach",
    "detach",
    "associate",
    "disassociate",
    "enable",
    "disable",
)
_DELETE_PREFIXES = ("delete", "remove", "terminate")


def classify_event(
    event_name: str,
    read_only: bool | None,
) -> tuple[EventCategory, ActivityType, ActivityConfidence]:
    """Classify one event without confusing management calls with usage."""
    normalized = event_name.replace("_", "").lower()
    if normalized in _FUNCTIONAL_EVENTS:
        category: EventCategory = (
            "invoke" if normalized in {"invoke", "executeapi"} else "access"
        )
        return category, "functional_usage", "high"
    if normalized in _STATE_EVENTS:
        return "update", "resource_state", "medium"
    if normalized.startswith(_CREATE_PREFIXES):
        return "create", "configuration_change", "medium"
    if normalized.startswith(_DELETE_PREFIXES):
        return "delete", "configuration_change", "medium"
    if normalized.startswith(_UPDATE_PREFIXES):
        return "update", "configuration_change", "medium"
    if read_only is True or normalized.startswith(_READ_PREFIXES):
        return "read", "administrative_activity", "medium"
    if read_only is False:
        return "write", "administrative_activity", "medium"
    return "unknown", "unknown", "unknown"


def classify_cloudtrail_event(event: dict[str, Any]) -> dict[str, Any]:
    category, activity_type, confidence = classify_event(
        str(event.get("EventName") or "Unknown"),
        event.get("ReadOnly") if isinstance(event.get("ReadOnly"), bool) else None,
    )
    return {
        "category": category,
        "activity_type": activity_type,
        "confidence": confidence,
    }
