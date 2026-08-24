"""Reusable contracts that every registered resource adapter must satisfy."""

from aws_resource_mcp.aws.adapters.registry import get_adapters
from aws_resource_mcp.aws.operations import OPERATION_REGISTRY


def test_every_adapter_declares_only_registered_read_operations() -> None:
    for adapter in get_adapters():
        metadata = adapter.metadata
        assert metadata.service_name
        assert metadata.scope in {"global", "regional"}
        assert metadata.resource_types
        assert metadata.operations
        assert set(metadata.discovery_operations) <= set(metadata.operations)
        assert set(metadata.enrichment_operations) <= set(metadata.operations)
        assert set(metadata.paginated_operations) <= set(metadata.operations)
        for operation in metadata.operations:
            spec = OPERATION_REGISTRY[operation]
            assert spec.access == "read"
            assert spec.cost_classification != "write"
            assert spec.component == f"adapter:{metadata.service_name}"


def test_adapter_metadata_has_no_duplicate_operations_or_resource_types() -> None:
    for adapter in get_adapters():
        metadata = adapter.metadata
        assert len(metadata.operations) == len(set(metadata.operations))
        assert len(metadata.resource_types) == len(set(metadata.resource_types))
