from __future__ import annotations

import asyncio

from fastmcp import Client

from specweaver.shared import di


async def main() -> None:
    async with di.run() as app:
        async with Client(app.mcp) as client:
            tools = await client.list_tools()
            print(f"== {len(tools)} tools ==")
            for tool in tools:
                first_line = (tool.description or "").strip().splitlines()[0]
                print(f"  {tool.name}: {first_line}")

            ping = await client.call_tool("sw_ping", {})
            print("sw_ping ->", ping.content[0].text)

            doctor = await client.call_tool("sw_doctor", {})
            print("sw_doctor ->", doctor.content[0].text[:200], "...")

            ingest = await client.call_tool(
                "sw_ingest_project", {"project_id": "mcp-verify"}
            )
            print("sw_ingest_project ->", ingest.content[0].text[:300])

            ctx = await client.call_tool(
                "sw_get_context",
                {
                    "project_id": "mcp-verify",
                    "task_text": "doctor 命令 装配 检查",
                },
            )
            print("sw_get_context ->", ctx.content[0].text[:300])

            done = await client.call_tool(
                "sw_complete_task",
                {
                    "project_id": "mcp-verify",
                    "task_id": "mcp-verify-task",
                    "base_ref": "HEAD~1",
                    "test_command": "python -m pytest -q",
                },
            )
            print("sw_complete_task ->", done.content[0].text[:300])

            resumed = await client.call_tool(
                "sw_resume_task",
                {
                    "project_id": "mcp-verify",
                    "objective": "doctor 命令 装配 检查",
                },
            )
            print("sw_resume_task ->", resumed.content[0].text[:400])

            ctx2 = await client.call_tool(
                "sw_get_context",
                {"project_id": "mcp-verify", "task_text": "pytest"},
            )
            has_run = "last test run" in ctx2.content[0].text
            print(f"sw_get_context(after complete) -> last test run in bundle: {has_run}")


if __name__ == "__main__":
    asyncio.run(main())
