"""Smoke test manual: conecta al servidor MCP vía stdio y lista las tools."""

import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EVAMCP = r"C:\Users\Francisco\Documents\eva-cli\.venv\Scripts\eva-mcp.exe"


async def main() -> None:
    params = StdioServerParameters(command=EVAMCP, args=[], env=None)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        resp = await session.list_tools()
        names = sorted(t.name for t in resp.tools)
        print(f"TOOLS ({len(names)}):")
        for n in names:
            print(f"  - {n}")


if __name__ == "__main__":
    asyncio.run(main())
