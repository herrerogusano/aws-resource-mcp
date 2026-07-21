"""Health-check tool for the MCP server."""

from typing import TypedDict


class HealthCheckResult(TypedDict):
    """Structured response returned by :func:`health_check`."""

    status: str
    server: str
    message: str


def health_check() -> HealthCheckResult:
    """Return the operational status of the local MCP server."""
    return {
        "status": "ok",
        "server": "aws-resource-mcp",
        "message": "MCP server is running",
    }
