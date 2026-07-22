"""Uniform resource deduplication for general AWS discovery."""

from typing import Any


def resource_identity(resource: dict[str, Any]) -> tuple[str, ...]:
    """Build a deterministic identity key using progressively weaker fields."""
    arn = resource.get("arn")
    if arn:
        return ("arn", str(arn).strip())

    details = resource.get("details", {})
    identifier = resource.get("id") or resource.get("identifier")
    if not identifier and isinstance(details, dict):
        identifier = (
            details.get("Identifier")
            or details.get("ResourceId")
            or details.get("Id")
        )
    resource_type = resource.get("resource_type")
    region = resource.get("region") or "global"
    if resource_type and identifier:
        return ("typed", str(resource_type), str(region), str(identifier))

    return (
        "named",
        str(resource.get("service") or "unknown"),
        str(region),
        str(resource.get("name") or "unknown"),
    )


def merge_resources(
    current: dict[str, Any],
    duplicate: dict[str, Any],
) -> dict[str, Any]:
    """Merge duplicate general-discovery records without service preference."""
    merged = dict(current)
    for key, value in duplicate.items():
        if key not in {"details", "properties", "sources", "cost_indicators"} and value not in (None, "", [], {}):
            merged[key] = value
    merged["sources"] = list(
        dict.fromkeys(
            [*current.get("sources", []), *duplicate.get("sources", [])]
        )
    )
    merged["details"] = {
        **current.get("details", current.get("properties", {})),
        **{
            key: value
            for key, value in duplicate.get(
                "details", duplicate.get("properties", {})
            ).items()
            if value not in (None, "", [], {})
        },
    }
    indicators = [
        *current.get("cost_indicators", []),
        *duplicate.get("cost_indicators", []),
    ]
    merged["cost_indicators"] = list(
        {indicator.get("type", str(index)): indicator for index, indicator in enumerate(indicators)}.values()
    )
    merged.pop("properties", None)
    return merged


def deduplicate_resources(
    *resource_groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Deduplicate uniformly normalized resources from one or more searches."""
    resources: dict[tuple[str, ...], dict[str, Any]] = {}
    for group in resource_groups:
        for resource in group:
            key = resource_identity(resource)
            if key in resources:
                resources[key] = merge_resources(resources[key], resource)
            else:
                resources[key] = resource
    return sorted(
        resources.values(),
        key=lambda item: (
            str(item.get("service") or ""),
            str(item.get("region") or ""),
            str(item.get("name") or item.get("arn") or ""),
        ),
    )


def group_resources_by_service(
    resources: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group common resources by service using stable ordering."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for resource in resources:
        service = str(resource.get("service") or "unknown")
        grouped.setdefault(service, []).append(resource)
    return dict(sorted(grouped.items()))
