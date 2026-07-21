"""Tests for the public MCP tool registry."""

import asyncio

from aws_resource_mcp.server import mcp


def test_server_registers_expected_tools() -> None:
    tools = asyncio.run(mcp.list_tools())
    assert {tool.name for tool in tools} == {"health_check", "listar_recursos_aws"}
