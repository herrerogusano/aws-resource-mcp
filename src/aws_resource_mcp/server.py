"""Local MCP server entry point."""

from mcp.server.fastmcp import FastMCP

from aws_resource_mcp.tools.analyze_activity import analizar_actividad_recursos
from aws_resource_mcp.tools.health import health_check
from aws_resource_mcp.tools.list_resources import listar_recursos_aws

mcp = FastMCP("aws-resource-mcp")
mcp.tool()(health_check)
mcp.tool()(listar_recursos_aws)
mcp.tool()(analizar_actividad_recursos)


def main() -> None:
    """Run the MCP server over standard input and output."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
