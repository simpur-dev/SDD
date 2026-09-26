"""Boundary battery for adapter error translation (docs/03 §7.1 contract).

Rule: SDK/transport/shape failures must surface as shared.errors.SWError,
never as raw httpx/json/KeyError/ValueError.
"""
from __future__ import annotations

import httpx
import pytest

from specweaver.adapters.driven.powercontext.client import PowerContextClient
from specweaver.adapters.driven.powercontext.handoff import (
    PowerContextHandoff,
    decode_ref,
)
from specweaver.adapters.driven.powercontext.memory import PowerContextMemory
from specweaver.domain.ports.memory import MemoryEntry
from specweaver.shared.config import PowerContextSettings
from specweaver.shared.errors import SWError


def _client(handler) -> PowerContextClient:
    client = PowerContextClient(PowerContextSettings())
    client._http = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    return client


@pytest.mark.xfail(strict=True, reason="audit B-8: raw ValueError leak")
async def test_non_json_200_body_translates_to_swerror() -> None:
    """Audit B-8: resp.json() on garbage body leaks ValueError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<!doctype html> proxy error")

    with pytest.raises(SWError):
        await _client(handler).get("/v1/scopes")


@pytest.mark.xfail(strict=True, reason="audit B-9: raw KeyError leak")
async def test_missing_entry_key_translates_to_swerror() -> None:
    """Audit B-9: unexpected response shape must not leak KeyError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    memory = PowerContextMemory(_client(handler))
    with pytest.raises(SWError):
        await memory.remember(
            MemoryEntry(scope_id="s", kind="constraint", content="c")
        )


@pytest.mark.xfail(strict=True, reason="audit B-9b: raw KeyError leak")
async def test_ensure_scope_missing_scope_id_translates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"items": []})
        return httpx.Response(200, json={"id": "unexpected"})

    with pytest.raises(SWError):
        await _client(handler).ensure_scope("sw:x", "summary")


@pytest.mark.xfail(strict=True, reason="audit B-10: raw ValueError leak")
def test_decode_ref_rejects_malformed_rev() -> None:
    """Audit B-10: garbage revision must raise SWError, not ValueError."""
    with pytest.raises(SWError):
        decode_ref("handoff:not-a-ref")


@pytest.mark.xfail(strict=True, reason="audit B-10b: raw ValueError leak")
async def test_continue_with_malformed_rev_raises_swerror() -> None:
    handoff = PowerContextHandoff(_client(lambda r: httpx.Response(200, json={})))
    with pytest.raises(SWError):
        await handoff.continue_("scp-1", "junk")
