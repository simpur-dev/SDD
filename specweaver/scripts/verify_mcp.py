from __future__ import annotations

import asyncio
import json
import sys

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
                    "test_command": f'"{sys.executable}" -m pytest -q',
                },
            )
            print("sw_complete_task ->", done.content[0].text[:300])

            hand = await client.call_tool(
                "sw_handoff",
                {
                    "project_id": "mcp-verify",
                    "objective": "doctor 命令 装配 检查",
                    "state": ["MCP 全链路验证已执行"],
                    "next_steps": ["新会话接续并三方核对"],
                    "omissions": ["批 4/5 演示尚未执行"],
                },
            )
            rev = json.loads(hand.content[0].text)["handoff_rev"]
            print("sw_handoff ->", rev)

            resumed = await client.call_tool(
                "sw_resume_task",
                {
                    "project_id": "mcp-verify",
                    "objective": "doctor 命令 装配 检查",
                    "handoff_rev": rev,
                },
            )
            resume_payload = json.loads(resumed.content[0].text)
            print(
                "sw_resume_task ->",
                f"handoff_resumed={resume_payload['handoff_resumed']} "
                f"next_steps={resume_payload['next_steps']} "
                f"mismatches={len(resume_payload['mismatches'])}",
            )

            ctx2 = await client.call_tool(
                "sw_get_context",
                {"project_id": "mcp-verify", "task_text": "pytest"},
            )
            has_run = "last test run" in ctx2.content[0].text
            print(f"sw_get_context(after complete) -> last test run in bundle: {has_run}")


if __name__ == "__main__":
    asyncio.run(main())
