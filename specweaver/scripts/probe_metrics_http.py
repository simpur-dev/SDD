"""Launch the streamable-http MCP server and probe /metrics for real.

The probe starts `run_http` as a subprocess, talks MCP over HTTP with a real
client (tool list + one usecase call), then scrapes /metrics to prove the
Prometheus endpoint serves the same process telemetry.
"""
from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time

import httpx
from fastmcp import Client

PORT = int(os.environ.get("SPECWEAVER_METRICS_PROBE_PORT", "8791"))


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
    async with Client(f"http://127.0.0.1:{PORT}/mcp") as client:
        tools = await client.list_tools()
        await client.call_tool(
            "sw_get_context",
            {
                "project_id": "mcp-verify",
                "task_text": "doctor 命令 装配 检查",
            },
        )
        await client.call_tool("sw_verify", {"project_id": "mcp-verify"})
        return len(tools), tools[0].name


def main() -> int:
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

        ok = (
            before.status_code == 200
            and "# TYPE sw_spans_total counter" not in before.text
            and n_tools >= 11
            and after.status_code == 200
            and any(
                line.startswith('sw_spans_total{span="get_context"}')
                for line in after.text.splitlines()
            )
            and any(
                line.startswith(
                    'sw_engine_metric_sum{span="get_context",'
                    'metric="recall"}'
                )
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


if __name__ == "__main__":
    raise SystemExit(main())
