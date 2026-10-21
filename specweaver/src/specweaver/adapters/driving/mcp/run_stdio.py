from __future__ import annotations

import asyncio
import os
import sys

from ....shared import di


def export_usage(app: di.SpecWeaverApp) -> None:
    """Write the server-side telemetry CSV when SPECWEAVER_USAGE_OUT is set.

    The stdio MCP server is a short-lived child process of an evaluation
    harness; without this hook its backend_calls/token evidence dies with
    the process. Export failures must never mask the session result, so
    they degrade to a warning on stderr.
    """
    target = os.environ.get("SPECWEAVER_USAGE_OUT")
    if not target:
        return
    try:
        app.telemetry.to_csv(target)
    except OSError as exc:
        print(f"[warn] usage export to {target} failed: {exc}", file=sys.stderr)


async def _amain() -> None:
    async with di.run() as app:
        try:
            await app.mcp.run_async(transport="stdio")
        finally:
            export_usage(app)


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
