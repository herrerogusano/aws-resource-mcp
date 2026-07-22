"""General AWS resource discovery through read-only Resource Explorer APIs."""

from datetime import datetime, timezone
from typing import Any

from aws_resource_mcp.aws.errors import describe_aws_error
from aws_resource_mcp.models import InventoryError, to_iso8601


def _paginated_call(
    client: Any,
    operation: str,
    result_key: str,
    **parameters: Any,
) -> list[Any]:
    results: list[Any] = []
    next_token: str | None = None
    while True:
        request = dict(parameters)
        if next_token:
            request["NextToken"] = next_token
        response = getattr(client, operation)(**request)
        results.extend(response.get(result_key, []))
        next_token = response.get("NextToken")
        if not next_token:
            return results


def list_resource_explorer_indexes(client: Any) -> list[dict[str, str | None]]:
    """List accessible Resource Explorer indexes with pagination."""
    indexes = _paginated_call(client, "list_indexes", "Indexes")
    return sorted(
        (
            {
                "arn": item.get("Arn"),
                "region": item.get("Region"),
                "type": item.get("Type"),
            }
            for item in indexes
        ),
        key=lambda item: (item["region"] or "", item["arn"] or ""),
    )


def list_resource_explorer_views(client: Any) -> list[str]:
    """List accessible Resource Explorer view ARNs with pagination."""
    return sorted(_paginated_call(client, "list_views", "Views"))


def list_supported_resource_types(client: Any) -> list[dict[str, Any]]:
    """List Resource Explorer types dynamically with pagination."""
    resource_types = _paginated_call(
        client,
        "list_supported_resource_types",
        "ResourceTypes",
    )
    return sorted(
        (
            {
                "service": item.get("Service"),
                "resource_type": item.get("ResourceType"),
                "cfn_resource_types": list(item.get("CFNResourceTypes", [])),
            }
            for item in resource_types
        ),
        key=lambda item: (item["service"] or "", item["resource_type"] or ""),
    )


def build_search_query(
    *,
    services: list[str] | None = None,
    resource_types: list[str] | None = None,
    region: str | None = None,
    query: str | None = None,
) -> str:
    """Build a Resource Explorer query from validated high-level filters."""
    parts = [query.strip() if query and query.strip() else "*"]
    if services:
        parts.append(f"service:{','.join(services)}")
    if resource_types:
        parts.append(f"resourcetype:{','.join(resource_types)}")
    if region:
        parts.append(f"region:{region}")
    return " ".join(parts)


def _resource_name(resource: dict[str, Any]) -> str | None:
    for item in resource.get("Properties", []):
        if str(item.get("Name", "")).lower() in {"name", "resourcename"}:
            data = item.get("Data")
            if isinstance(data, str) and data:
                return data
            if isinstance(data, dict):
                value = data.get("Value") or data.get("Name")
                if value:
                    return str(value)
    arn = resource.get("Arn")
    if arn:
        return str(arn).rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    return None


def normalize_resource_explorer_resource(resource: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Resource Explorer result without assuming property shapes."""
    properties = {
        str(item.get("Name")): item.get("Data")
        for item in resource.get("Properties", [])
        if item.get("Name")
    }
    return {
        "arn": resource.get("Arn"),
        "service": resource.get("Service"),
        "resource_type": resource.get("CfnResourceType")
        or resource.get("ResourceType"),
        "region": resource.get("Region") or "global",
        "account_id": resource.get("OwningAccountId"),
        "name": _resource_name(resource),
        "sources": ["resource_explorer"],
        "last_reported_at": to_iso8601(resource.get("LastReportedAt")),
        "properties": properties,
    }


def search_resource_explorer(
    client: Any,
    view_arn: str,
    query_string: str,
) -> list[dict[str, Any]]:
    """Search one Resource Explorer view and normalize every result page."""
    resources = _paginated_call(
        client,
        "search",
        "Resources",
        QueryString=query_string,
        ViewArn=view_arn,
    )
    return [normalize_resource_explorer_resource(resource) for resource in resources]


def discover_with_resource_explorer(
    session: Any,
    enabled_regions: list[str],
    *,
    primary_region: str,
    services: list[str] | None = None,
    resource_types: list[str] | None = None,
    query: str | None = None,
    region_filter: str | None = None,
) -> dict[str, Any]:
    """Discover resources using an aggregator index or accessible local indexes."""
    coverage: dict[str, Any] = {
        "available": False,
        "aggregator_index": False,
        "regions_indexed": [],
        "supported_resource_type_count": 0,
        "services_recognized": [],
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "permission_errors": [],
        "limitations": [],
    }
    errors: list[InventoryError] = []

    probe_regions = list(dict.fromkeys([primary_region, *enabled_regions]))
    indexes: list[dict[str, str | None]] | None = None
    for probe_region in probe_regions:
        try:
            client = session.client("resource-explorer-2", region_name=probe_region)
            indexes = list_resource_explorer_indexes(client)
            coverage["available"] = True
            break
        except Exception as error:
            described = describe_aws_error("resource-explorer-2", error)
            if described["error_type"] == "access_denied":
                coverage["permission_errors"].append(described["message"])
                errors.append(described)
                break

    if indexes is None:
        coverage["limitations"].append(
            "Resource Explorer could not be queried in the enabled Regions."
        )
        return {"resources": [], "coverage": coverage, "errors": errors}

    coverage["regions_indexed"] = sorted(
        index["region"] for index in indexes if index.get("region")
    )
    aggregators = [index for index in indexes if index.get("type") == "AGGREGATOR"]
    selected_indexes = aggregators[:1] if aggregators else indexes
    coverage["aggregator_index"] = bool(aggregators)

    if not selected_indexes:
        coverage["limitations"].append(
            "No accessible Resource Explorer index exists; general inventory is unavailable."
        )
        return {"resources": [], "coverage": coverage, "errors": errors}

    search_query = build_search_query(
        services=services,
        resource_types=resource_types,
        region=region_filter,
        query=query,
    )
    discovered: list[dict[str, Any]] = []
    types_loaded = False

    for index in selected_indexes:
        index_region = index.get("region")
        if not index_region:
            continue
        try:
            client = session.client("resource-explorer-2", region_name=index_region)
            if not types_loaded:
                supported = list_supported_resource_types(client)
                coverage["supported_resource_type_count"] = len(supported)
                coverage["services_recognized"] = sorted(
                    {item["service"] for item in supported if item.get("service")}
                )
                types_loaded = True
            views = list_resource_explorer_views(client)
            if not views:
                coverage["limitations"].append(
                    f"No accessible Resource Explorer view exists in {index_region}."
                )
                continue
            discovered.extend(search_resource_explorer(client, views[0], search_query))
        except Exception as error:
            described = describe_aws_error("resource-explorer-2", error)
            errors.append(described)
            if described["error_type"] == "access_denied":
                coverage["permission_errors"].append(described["message"])

    if not aggregators and indexes:
        coverage["limitations"].append(
            "Only local Resource Explorer indexes were available; coverage depends on indexed Regions."
        )

    return {"resources": discovered, "coverage": coverage, "errors": errors}
