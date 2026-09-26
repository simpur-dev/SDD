"""One command quality gate for SpecWeaver.

Default (offline): ruff over src/tests/scripts + the unit and contract suites.
``--live`` adds the checks that need the seekdb and PowerContext containers:
doctor, the 11-tool MCP walkthrough, the /metrics endpoint probe.
``--demo`` additionally replays the railway demo into evidence/.

The gate never reports success on an empty run: pytest must collect tests,
and every live step has to exit 0.
"""
from __future__ import annotations

import argparse
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEEKDB_PORT, PC_PORT = 2881, 8000


def _port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(1.0)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _run(label: str, args: list[str]) -> bool:
    print(f"\n=== {label}: {' '.join(args[1:])}", flush=True)
    proc = subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = ((proc.stdout or "") + (proc.stderr or "")).splitlines()
    if proc.returncode == 0:
        print(f"PASS {label}: {output[-1] if output else '(no output)'}")
        return True
    print(f"FAIL {label} (exit {proc.returncode})")
    print("\n".join(output[-40:]))
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="also run the container-backed checks (slow: verify_mcp runs "
        "the full test suite inside complete_task)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="with --live: replay the railway demo and write evidence/",
    )
    args = parser.parse_args()

    py = sys.executable
    steps: list[tuple[str, list[str]]] = [
        ("ruff", [py, "-m", "ruff", "check", "."]),
        ("pytest", [py, "-m", "pytest", "-q"]),
    ]
    if args.live:
        if not (_port_open(SEEKDB_PORT) and _port_open(PC_PORT)):
            print(
                f"[warn] seekdb(:{SEEKDB_PORT}) or powercontext(:{PC_PORT}) "
                "unreachable - start deploy/docker-compose.yml; the live "
                "steps below will fail"
            )
        steps += [
            ("doctor", _cli("doctor")),
            ("mcp-11-tools", [py, str(ROOT / "scripts" / "verify_mcp.py")]),
            (
                "metrics-endpoint",
                [py, str(ROOT / "scripts" / "probe_metrics_http.py")],
            ),
        ]
        if args.demo:
            steps.append(("railway-demo", [py, str(ROOT / "scripts" / "run_demo.py")]))

    results = [(label, _run(label, argv)) for label, argv in steps]
    print("\n=== gate summary ===")
    for label, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    failed = [label for label, ok in results if not ok]
    if failed:
        print(f"GATE FAIL: {', '.join(failed)}")
        return 1
    print(f"GATE PASS ({len(results)} steps)")
    return 0


def _cli(*command: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "specweaver.adapters.driving.cli.app",
        *command,
    ]


if __name__ == "__main__":
    raise SystemExit(main())
