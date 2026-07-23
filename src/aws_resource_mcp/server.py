"""Local MCP server entry point."""

from mcp.server.fastmcp import FastMCP

from aws_resource_mcp.tools.registry import registered_tools

mcp = FastMCP("aws-resource-mcp")
for tool in registered_tools():
    mcp.tool()(tool)


def main() -> None:
    """Run the MCP server over standard input and output."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
