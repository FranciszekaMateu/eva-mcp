"""Smoke test manual: llama eva_cursos contra el EVA real vía stdio."""

import asyncio
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EVAMCP = r"C:\Users\Francisco\Documents\eva-cli\.venv\Scripts\eva-mcp.exe"


async def main() -> None:
    params = StdioServerParameters(command=EVAMCP, args=[], env=None)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("eva_cursos", {})
        for content in result.content:
            if hasattr(content, "text"):
                data = json.loads(content.text)
                print(f"CURSOS ({len(data)}):")
                for c in data:
                    print(f"  {c['id']:>4}  {c['nombre']}")


if __name__ == "__main__":
    asyncio.run(main())
