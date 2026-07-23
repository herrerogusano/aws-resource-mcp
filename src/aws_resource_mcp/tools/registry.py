"""Stable, public registry for the MCP tools exposed by the server."""

from collections.abc import Callable
from typing import Any


def registered_tools() -> tuple[Callable[..., dict[str, Any]], ...]:
    """Return tool callables in their public registration order."""
    from aws_resource_mcp.tools.analyze_activity import analizar_actividad_recursos
    from aws_resource_mcp.tools.analyze_cost_risk import analizar_riesgo_costes
    from aws_resource_mcp.tools.diagnose_coverage import diagnosticar_cobertura_aws
    from aws_resource_mcp.tools.health import health_check
    from aws_resource_mcp.tools.list_resources import listar_recursos_aws
    from aws_resource_mcp.tools.query_costs import consultar_costes_aws
    from aws_resource_mcp.tools.review_free_tier import revisar_free_tier

    return (
        health_check,
        listar_recursos_aws,
        analizar_actividad_recursos,
        diagnosticar_cobertura_aws,
        analizar_riesgo_costes,
        revisar_free_tier,
        consultar_costes_aws,
    )


def registered_tool_names() -> list[str]:
    """Return tool names dynamically without inspecting FastMCP internals."""
    return [tool.__name__ for tool in registered_tools()]
