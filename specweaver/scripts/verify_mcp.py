from __future__ import annotations

import asyncio

from fastmcp import Client

from specweaver.adapters.driving.mcp.server import build_mcp
from specweaver.shared.config import Settings


async def main() -> None:
    mcp = build_mcp(Settings())
    async with Client(mcp) as client:
        tools = await client.list_tools()
        print(f"== {len(tools)} tools ==")
        for tool in tools:
            first_line = (tool.description or "").strip().splitlines()[0]
            print(f"  {tool.name}: {first_line}")
        ping = await client.call_tool("sw_ping", {})
        print("sw_ping ->", ping.content[0].text)
        doctor = await client.call_tool("sw_doctor", {})
        print("sw_doctor ->", doctor.content[0].text[:160], "...")


if __name__ == "__main__":
    asyncio.run(main())
