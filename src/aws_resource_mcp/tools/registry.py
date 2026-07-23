"""Stable, public registry for the MCP tools exposed by the server."""

from collections.abc import Callable
from typing import Any


def registered_tools() -> tuple[Callable[..., dict[str, Any]], ...]:
    """Return tool callables in their public registration order."""
    from aws_resource_mcp.tools.analyze_activity import analizar_actividad_recursos
    from aws_resource_mcp.tools.diagnose_coverage import diagnosticar_cobertura_aws
    from aws_resource_mcp.tools.health import health_check
    from aws_resource_mcp.tools.list_resources import listar_recursos_aws

    return (
        health_check,
        listar_recursos_aws,
        analizar_actividad_recursos,
        diagnosticar_cobertura_aws,
    )


def registered_tool_names() -> list[str]:
    """Return tool names dynamically without inspecting FastMCP internals."""
    return [tool.__name__ for tool in registered_tools()]
