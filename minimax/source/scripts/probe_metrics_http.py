"""Launch the streamable-http MCP server and probe /metrics for real.

The probe starts `run_http` as a subprocess, lists tools and calls all 11 of
them over HTTP with a real MCP client (handoff -> resume and context ->
explain_source chained through their returned ids), then scrapes /metrics to
prove the Prometheus endpoint serves the same process telemetry: a missing
usecase span means the traffic never reached the application layer. Every line
is mirrored into an evidence file so `gate.py --live` leaves a trace.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

import httpx
from fastmcp import Client

ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.environ.get("SPECWEAVER_METRICS_PROBE_PORT", "8791"))


class _Tee:
    """Mirror stdout into the evidence file (utf-8, line-for-line)."""

    def __init__(self, path: Path) -> None:
        self._file = path.open("w", encoding="utf-8")

    def write(self, data: str) -> int:
        sys.__stdout__.write(data)
        self._file.write(data)
        return len(data)

    def flush(self) -> None:
        sys.__stdout__.flush()
        self._file.flush()

    def close(self) -> None:
        self._file.close()



def _wait_for_port(timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", PORT)) == 0:
                return True
        time.sleep(0.5)
    return False


async def _mcp_traffic() -> tuple[int, str]:
    """Drive the whole tool surface over the transport an Agent actually uses."""
    async with Client(f"http://127.0.0.1:{PORT}/mcp") as client:
        tools = await client.list_tools()
        calls: list[tuple[str, dict]] = [
            ("sw_ping", {}),
            ("sw_doctor", {}),
            ("sw_ingest_project", {"project_id": "mcp-verify"}),
            (
                "sw_get_context",
                {
                    "project_id": "mcp-verify",
                    "task_text": "doctor 命令 装配 检查",
                },
            ),
            (
                "sw_record_decision",
                {
                    "project_id": "mcp-verify",
                    "decision": f"http 探针决策 {time.strftime('%H%M%S')}",
                    "rationale": "验证 11 工具经 streamable-http 全链路可用",
                },
            ),
            (
                "sw_report_progress",
                {
                    "project_id": "mcp-verify",
                    "note": f"http 探针进度 {time.strftime('%H%M%S')}",
                    "update_handoff": True,
                    "next_steps": ["抓取 /metrics"],
                    "omissions": ["无"],
                },
            ),
            (
                "sw_handoff",
                {
                    "project_id": "mcp-verify",
                    "objective": "http 传输全工具探针",
                    "state": ["11 工具经 streamable-http 调用"],
                    "next_steps": ["接续验证"],
                    "omissions": ["真 Agent 自主决策未覆盖"],
                },
            ),
            ("sw_verify", {"project_id": "mcp-verify"}),
        ]
        for name, args in calls:
            await client.call_tool(name, args)
        # resume needs the rev the handoff calls just returned
        handoff = await client.call_tool(
            "sw_handoff",
            {
                "project_id": "mcp-verify",
                "objective": "http 传输全工具探针",
                "state": ["handoff 链第二次提交"],
                "next_steps": ["resume 验证"],
                "omissions": ["无"],
            },
        )
        rev = json.loads(handoff.content[0].text)["handoff_rev"]
        await client.call_tool(
            "sw_resume_task",
            {"project_id": "mcp-verify", "handoff_rev": rev},
        )
        context = await client.call_tool(
            "sw_get_context",
            {
                "project_id": "mcp-verify",
                "task_text": "doctor 命令 装配 检查",
            },
        )
        cited = json.loads(context.content[0].text)["cited"]
        if cited:
            await client.call_tool(
                "sw_explain_source",
                {"project_id": "mcp-verify", "artifact_id": cited[0]},
            )
        await client.call_tool(
            "sw_complete_task",
            {
                "project_id": "mcp-verify",
                "task_id": "http-probe-task",
                "base_ref": "HEAD~1",
                "test_command": f'"{sys.executable}" -m pytest -q',
            },
        )
        return len(tools), tools[0].name


def _probe() -> int:
    env = {**os.environ, "SERVER__PORT": str(PORT)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "specweaver.adapters.driving.mcp.run_http"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        if not _wait_for_port():
            print("server never came up; log follows")
            print(proc.stdout.read() if proc.stdout else "")
            return 1

        base = f"http://127.0.0.1:{PORT}"
        before = httpx.get(f"{base}/metrics", timeout=10)
        print("GET /metrics ->", before.status_code)
        print("\n".join(before.text.splitlines()[:6]))

        n_tools, first = asyncio.run(_mcp_traffic())
        print(f"MCP over http -> {n_tools} tools (first={first})")

        after = httpx.get(f"{base}/metrics", timeout=10)
        print("GET /metrics(after traffic) ->", after.status_code)
        print(after.text.rstrip())

        # every usecase-backed tool must show up as a span, or the traffic did
        # not actually reach the application layer
        expected_spans = {
            "ingest_project",
            "get_context",
            "complete_task",
            "create_handoff",
            "resume_task",
            "record_decision",
            "report_progress",
            "verify_state",
            "explain_source",
        }
        seen_spans = {
            line.split('span="')[1].split('"')[0]
            for line in after.text.splitlines()
            if line.startswith("sw_spans_total{")
        }
        missing = sorted(expected_spans - seen_spans)
        if missing:
            print(f"MISSING SPANS: {missing}")

        ok = (
            before.status_code == 200
            and "# TYPE sw_spans_total counter" not in before.text
            and n_tools >= 11
            and after.status_code == 200
            and not missing
            and "# TYPE sw_span_duration_ms histogram" in after.text
            and any(
                line.startswith('sw_engine_metric_sum{span="get_context",')
                for line in after.text.splitlines()
            )
        )
        print("PROBE", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(
            ROOT.parent
            / "evidence"
            / f"http-transport-{datetime.now():%Y%m%d-%H%M%S}"
        ),
        help="evidence directory for probe.txt",
    )
    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    tee = _Tee(out_dir / "probe.txt")
    try:
        with redirect_stdout(tee):
            rc = _probe()
    finally:
        tee.close()
    print(f"evidence -> {out_dir / 'probe.txt'}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())