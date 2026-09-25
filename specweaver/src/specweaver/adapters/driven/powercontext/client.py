from __future__ import annotations

import httpx

from ....shared.config import PowerContextSettings


class PowerContextClient:
    """Async HTTP client for the PowerContext server."""

    def __init__(self, settings: PowerContextSettings) -> None:
        self._settings = settings
        self._http: httpx.AsyncClient | None = None
        self._scope_cache: dict[str, str] = {}

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
        resp = await self._http.request(
            method, path, json=payload, params=params
        )
        resp.raise_for_status()
        if not resp.content:
            return {}
        return resp.json()

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
            if item.get("title") == title:
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
        scope_id = created["scope_id"]
        self._scope_cache[title] = scope_id
        return scope_id
