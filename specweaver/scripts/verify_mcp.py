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
            ctx_payload = json.loads(ctx.content[0].text)
            cited = ctx_payload["cited"]
            print(
                "sw_get_context ->",
                f"cited={len(cited)} "
                f"markdown={len(ctx_payload['markdown'])}B",
            )

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

            dec = await client.call_tool(
                "sw_record_decision",
                {
                    "project_id": "mcp-verify",
                    "decision": "MCP 验证以 9 个工具为验收面",
                    "rationale": "覆盖四用例与 /metrics 的全部出口",
                },
            )
            dec_payload = json.loads(dec.content[0].text)
            entry_id = dec_payload["entry_id"]
            print(
                f"sw_record_decision -> {dec_payload['action']} "
                f"entry={entry_id}"
            )

            rev_dec = await client.call_tool(
                "sw_record_decision",
                {
                    "project_id": "mcp-verify",
                    "decision": "MCP 验证以 9 个工具 + 1 个错误探针为验收面",
                    "rationale": "补充 SWError -> ToolError 映射的可观测性",
                    "replaces_entry_id": entry_id,
                },
            )
            print(
                "sw_record_decision(revise) ->",
                json.loads(rev_dec.content[0].text)["action"],
            )

            try:
                await client.call_tool(
                    "sw_record_decision",
                    {
                        "project_id": "mcp-verify",
                        "decision": "互斥参数探针",
                        "replaces_entry_id": entry_id,
                        "retire_entry_id": entry_id,
                    },
                )
                print("sw_record_decision(guard) -> UNEXPECTED success")
            except Exception as exc:  # noqa: BLE001
                print(
                    "sw_record_decision(guard) -> ToolError:",
                    str(exc)[:160],
                )

            ret_dec = await client.call_tool(
                "sw_record_decision",
                {
                    "project_id": "mcp-verify",
                    "decision": "验收脚本退役早期的单一决策记录口径",
                    "retire_entry_id": entry_id,
                },
            )
            print(
                "sw_record_decision(retire) ->",
                json.loads(ret_dec.content[0].text)["action"],
            )

            prog = await client.call_tool(
                "sw_report_progress",
                {
                    "project_id": "mcp-verify",
                    "note": "9 工具链路验证进行中",
                    "next_steps": ["核对 /metrics 与一致性报告"],
                    "omissions": ["批 5 效率指标未复测"],
                    "update_handoff": True,
                },
            )
            prog_payload = json.loads(prog.content[0].text)
            print(
                "sw_report_progress -> "
                f"entry={prog_payload['entry_id']} "
                f"handoff_rev={prog_payload['handoff_rev']}"
            )

            verify = await client.call_tool(
                "sw_verify", {"project_id": "mcp-verify"}
            )
            v_payload = json.loads(verify.content[0].text)
            print(
                "sw_verify -> "
                f"checked={v_payload['checked']} "
                f"mismatches={len(v_payload['mismatches'])} "
                f"change_set_stale={v_payload['change_set_stale']} "
                f"test_report={v_payload['test_report']} "
                f"rules={v_payload['rules_in_catalog']} "
                f"constraints={v_payload['constraint_entries_in_memory']} "
                f"notes={len(v_payload['notes'])}"
            )

            if cited:
                # prefer a spec-side artifact so the upstream chain is real
                target = next(
                    (a for a in cited if not a.startswith("CODE-")), cited[0]
                )
                exp = await client.call_tool(
                    "sw_explain_source",
                    {"project_id": "mcp-verify", "artifact_id": target},
                )
                e_payload = json.loads(exp.content[0].text)
                print(
                    f"sw_explain_source({target}) -> "
                    f"root={e_payload['root']['type']} "
                    f"upstream={len(e_payload['upstream'])} "
                    f"downstream={len(e_payload['downstream'])} "
                    f"missing_refs={len(e_payload['missing_refs'])}"
                )
            else:
                print("sw_explain_source -> skipped (nothing cited)")

            metrics = app.telemetry.to_prometheus()
            print(
                f"telemetry -> spans={len(app.telemetry.records)} "
                f"prometheus_lines={len(metrics.splitlines())}"
            )
            for line in metrics.splitlines()[-4:]:
                print(" ", line)


if __name__ == "__main__":
    asyncio.run(main())
