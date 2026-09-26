from __future__ import annotations

import httpx

from ....shared.config import PowerContextSettings
from ....shared.errors import BackendConnectionError
from .client import auth_headers


async def check_powercontext(
    settings: PowerContextSettings, transport=None
) -> dict:
    """Lightweight readiness probe (used by doctor).

    Official docs keep /health/* public, but the configured token is sent so
    the probe behaves the same under access_mode=enforced, and every failure
    arrives as the adapter error contract instead of a raw httpx exception.
    """
    url = f"{settings.base_url}/health/ready"
    try:
        async with httpx.AsyncClient(
            timeout=settings.timeout,
            headers=auth_headers(settings),
            transport=transport,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except (
        httpx.RequestError,
        httpx.HTTPStatusError,
        ValueError,
    ) as exc:
        raise BackendConnectionError(
            f"powercontext not ready at {url}: {exc}"
        ) from exc
    return {"name": "powercontext", "ok": True, "detail": data}
