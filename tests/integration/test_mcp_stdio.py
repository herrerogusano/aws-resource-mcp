"""Local end-to-end MCP protocol checks with no AWS calls."""

import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_server_initializes_lists_tools_and_keeps_stdout_protocol_clean() -> None:
    async def exercise_server() -> None:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "aws_resource_mcp.server"],
        )
        async with (
            stdio_client(parameters) as (reader, writer),
            ClientSession(reader, writer) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool("health_check", {"check_aws": False})

        assert {tool.name for tool in tools.tools} == {
            "health_check",
            "listar_recursos_aws",
            "analizar_actividad_recursos",
            "diagnosticar_cobertura_aws",
            "analizar_riesgo_costes",
            "revisar_free_tier",
            "consultar_costes_aws",
        }
        assert result.isError is False

    asyncio.run(exercise_server())
