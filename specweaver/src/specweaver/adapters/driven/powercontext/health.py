from __future__ import annotations

import httpx

from ....shared.config import PowerContextSettings


async def check_powercontext(settings: PowerContextSettings) -> dict:
    """Lightweight readiness probe (used by doctor)."""
    async with httpx.AsyncClient(timeout=settings.timeout) as client:
        resp = await client.get(f"{settings.base_url}/health/ready")
        resp.raise_for_status()
        data = resp.json()
    return {"name": "powercontext", "ok": True, "detail": data}
