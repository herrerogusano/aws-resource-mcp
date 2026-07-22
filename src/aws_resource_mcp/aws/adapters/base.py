"""Common adapter contract, metadata, context, and pagination helpers."""

from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal, Protocol, runtime_checkable

from aws_resource_mcp.aws.operations import OperationGuard
from aws_resource_mcp.models import InventoryError, Resource

Scope = Literal["regional", "global"]


@dataclass(frozen=True)
class AdapterMetadata:
    service_name: str
    scope: Scope
    operations: tuple[tuple[str, str], ...]
    resource_types: tuple[str, ...]
    supports_discovery: bool = True
    supports_enrichment: bool = True
    detail_fields: tuple[str, ...] = ()
    cost_indicator_types: tuple[str, ...] = ()


@dataclass
class AdapterContext:
    session: Any
    account_id: str | None
    regions: list[str]
    primary_region: str
    operation_guard: OperationGuard
    include_details: bool = True
    include_cost_indicators: bool = True
    errors: list[InventoryError] = field(default_factory=list)
    operations_executed: list[dict[str, str]] = field(default_factory=list)

    def call(
        self,
        service: str,
        operation: str,
        *,
        region: str | None = None,
        **parameters: Any,
    ) -> Any:
        client = self.session.client(service, region_name=region) if region else self.session.client(service)
        response = self.operation_guard.call(
            client,
            service=service,
            operation=operation,
            **parameters,
        )
        self.operations_executed.append(
            {"service": service, "operation": operation, "region": region or "global"}
        )
        return response


@runtime_checkable
class ResourceAdapter(Protocol):
    metadata: AdapterMetadata

    def discover(self, context: AdapterContext) -> list[Resource]: ...

    def enrich(
        self,
        resources: list[Resource],
        context: AdapterContext,
    ) -> list[Resource]: ...


class BaseAdapter:
    """Default behavior shared by every registered adapter."""

    metadata: ClassVar[AdapterMetadata]

    def regions(self, context: AdapterContext) -> list[str]:
        return ["global"] if self.metadata.scope == "global" else context.regions

    def enrich(
        self,
        resources: list[Resource],
        context: AdapterContext,
    ) -> list[Resource]:
        return resources


def pages(
    context: AdapterContext,
    service: str,
    operation: str,
    result_key: str,
    *,
    region: str | None = None,
    parameters: dict[str, Any] | None = None,
    request_token: str = "NextToken",
    response_token: str = "NextToken",
) -> list[Any]:
    """Execute every page through the operation guard."""
    results: list[Any] = []
    token: str | None = None
    while True:
        request = dict(parameters or {})
        if token:
            request[request_token] = token
        response = context.call(service, operation, region=region, **request)
        container = response.get(result_key, [])
        value = container
        if isinstance(container, dict) and "Items" in container:
            value = container["Items"]
        results.extend(value or [])
        token = response.get(response_token)
        if not token and isinstance(container, dict):
            token = container.get(response_token)
        if not token:
            return results


def selected_tags(tags: Collection[dict[str, Any]] | None) -> dict[str, str]:
    """Return only non-sensitive identifying tags."""
    allowed = {"Name", "Environment", "Project"}
    return {
        str(tag.get("Key")): str(tag.get("Value"))
        for tag in tags or []
        if tag.get("Key") in allowed and tag.get("Value") is not None
    }
