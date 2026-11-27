"""Real SDK protocol test against a running, isolated Compose adapter."""

import asyncio
import os
import sys

from mcp.client.stdio import stdio_client

from mcp import ClientSession, StdioServerParameters


async def check(memory_enabled: bool, token: str, marker: str) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "drift.core.private_mcp"],
        env={
            "DRIFT_PLUGIN_TOKEN": token,
            "DRIFT_PORT": "8000",
            "DRIFT_MCP_MEMORY_READ": "1" if memory_enabled else "0",
        },
    )
    async with stdio_client(params) as (reader, writer), ClientSession(
        reader, writer
    ) as session:
        await session.initialize()
        tools = (await session.list_tools()).tools
        expected = {"drift_health"}
        if memory_enabled:
            expected.add("drift_memory_search")
        assert {tool.name for tool in tools} == expected
        for tool in tools:
            assert tool.annotations.readOnlyHint is True
        health = await session.call_tool("drift_health", {})
        if token != os.environ["DRIFT_PLUGIN_TOKEN"]:
            assert health.isError
            return
        assert not health.isError
        assert "ready" in str(health.content)
        denied = await session.call_tool("companion_think", {"prompt": "test"})
        assert denied.isError
        if memory_enabled:
            response = await session.call_tool(
                "drift_memory_search", {"query": marker, "limit": 3}
            )
            assert not response.isError
            assert marker in str(response.content)
            invalid = await session.call_tool(
                "drift_memory_search", {"query": marker, "limit": 100}
            )
            assert invalid.isError


async def main() -> None:
    token = os.environ["DRIFT_PLUGIN_TOKEN"]
    marker = os.environ["SMOKE_MARKER"]
    await check(False, token, marker)
    await check(True, token, marker)
    await check(False, "wrong-token-long-enough", marker)
    print("Real MCP initialization, allowlist, authentication and restarted memory recall passed")


if __name__ == "__main__":
    asyncio.run(main())
