from __future__ import annotations

from typing import Any

import httpx

from ....shared.config import PowerContextSettings
from ....shared.errors import BackendConnectionError, SWError


def require(payload: Any, key: str, what: str) -> Any:
    """Read a mandatory response field without leaking KeyError upstream."""
    if not isinstance(payload, dict) or payload.get(key) is None:
        raise SWError(
            f"powercontext {what} is missing field {key!r} in the response"
        )
    return payload[key]


class PowerContextClient:
    """Async HTTP client for the PowerContext server."""

    def __init__(
        self, settings: PowerContextSettings, telemetry=None
    ) -> None:
        self._settings = settings
        self._http: httpx.AsyncClient | None = None
        self._scope_cache: dict[str, str] = {}
        self._telemetry = telemetry

    def open(self) -> None:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self._settings.base_url, timeout=20.0
            )

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def __aenter__(self) -> PowerContextClient:
        self.open()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def request(self, method, path, payload=None, params=None):
        if self._http is None:
            self.open()
        try:
            resp = await self._http.request(
                method, path, json=payload, params=params
            )
        except httpx.RequestError as exc:
            raise BackendConnectionError(
                f"powercontext unreachable: {exc}"
            ) from exc
        if self._telemetry is not None:
            self._telemetry.record_backend_call()
        if resp.status_code >= 400:
            raise SWError(
                f"powercontext {resp.status_code} on {method} {path}: "
                f"{resp.text[:200]}"
            )
        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError as exc:
            raise SWError(
                f"powercontext returned a non-JSON body on {method} {path}: "
                f"{resp.text[:200]}"
            ) from exc

    async def post(self, path, payload):
        return await self.request("POST", path, payload)

    async def get(self, path, params=None):
        return await self.request("GET", path, params=params)

    async def ensure_scope(self, title: str, summary: str) -> str:
        """Resolve a stable scope by title; create it if missing (idempotent)."""
        if title in self._scope_cache:
            return self._scope_cache[title]
        page = await self.get("/v1/scopes")
        for item in page.get("items", []):
            if item.get("title") == title and item.get("scope_id"):
                self._scope_cache[title] = item["scope_id"]
                return item["scope_id"]
        created = await self.post(
            "/v1/scopes",
            {
                "title": title,
                "summary": summary,
                "idempotency_key": f"sw-scope-{title}",
            },
        )
        scope_id = created.get("scope_id")
        if not isinstance(scope_id, str) or not scope_id:
            raise SWError(
                "powercontext scope creation returned no scope_id "
                f"for title {title!r}"
            )
        self._scope_cache[title] = scope_id
        return scope_id
