from __future__ import annotations

from fastmcp import FastMCP

from ....shared.config import Settings
from ...driven.powercontext.health import check_powercontext
from ...driven.seekdb.health import check_seekdb


def build_mcp(settings: Settings) -> FastMCP:
    mcp = FastMCP("SpecWeaver")

    @mcp.tool
    async def sw_ping() -> str:
        """Liveness probe."""
        return "pong"

    @mcp.tool
    async def sw_doctor() -> dict:
        """Report seekdb / PowerContext connectivity."""
        result: dict = {}
        try:
            result["seekdb"] = await check_seekdb(settings.seekdb)
        except Exception as exc:  # noqa: BLE001
            result["seekdb"] = {"ok": False, "error": str(exc)}
        try:
            result["powercontext"] = await check_powercontext(settings.powercontext)
        except Exception as exc:  # noqa: BLE001
            result["powercontext"] = {"ok": False, "error": str(exc)}
        return result

    return mcp
