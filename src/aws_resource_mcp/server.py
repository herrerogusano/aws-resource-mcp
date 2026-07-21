"""Local MCP server entry point."""

from mcp.server.fastmcp import FastMCP

from aws_resource_mcp.tools.health import health_check

mcp = FastMCP("aws-resource-mcp")
mcp.tool()(health_check)


def main() -> None:
    """Run the MCP server over standard input and output."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
