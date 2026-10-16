import json
import os
import sys

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def call(tool: str, args: dict | None = None, env: dict | None = None):
    """Call a tool through the real stdio MCP protocol; return parsed JSON."""
    base = {k: v for k, v in os.environ.items()}
    if env is not None:
        base = {k: v for k, v in base.items() if not k.startswith("DOMINO_")}
        base.update(env)

    async def run():
        params = StdioServerParameters(command=sys.executable, args=["-m", "domino_governance_mcp.server"], env=base)
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool(tool, args or {})
                text = "".join(c.text for c in res.content if c.type == "text")
                return json.loads(text) if text else None

    return anyio.run(run)


@pytest.fixture(scope="session")
def tools():
    async def run():
        params = StdioServerParameters(command=sys.executable, args=["-m", "domino_governance_mcp.server"], env=dict(os.environ))
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                return {t.name: t for t in (await s.list_tools()).tools}
    return anyio.run(run)
