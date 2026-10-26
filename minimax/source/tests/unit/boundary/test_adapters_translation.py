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


async def test_non_json_200_body_translates_to_swerror() -> None:
    """Audit B-8: resp.json() on garbage body leaks ValueError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<!doctype html> proxy error")

    with pytest.raises(SWError):
        await _client(handler).get("/v1/scopes")


async def test_missing_entry_key_translates_to_swerror() -> None:
    """Audit B-9: unexpected response shape must not leak KeyError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    memory = PowerContextMemory(_client(handler))
    with pytest.raises(SWError):
        await memory.remember(
            MemoryEntry(scope_id="s", kind="constraint", content="c")
        )


PC_ENTRY = {
    "citation": {
        "memory_ref": {
            "family": "memory",
            "artifact_id": "memory",
            "revision": 4,
        },
        "entry_id": "mem-1",
        "entry_version_id": "mem_ver_1",
    },
    "version": 1,
    "kind": "decision",
    "text": "目录用 seekdb 存",
    "state": "active",
    "source_refs": [],
    "artifact_refs": [],
}


async def test_remember_of_duplicate_text_returns_the_stored_entry() -> None:
    """Measured 2026-09-27: PowerContext de-duplicates identical text inside
    one memory and answers ``entry: null`` with the same revision - remember
    must stay idempotent instead of failing a re-run of the same task."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path.endswith("/remember"):
            return httpx.Response(
                200, json={"memory": {"revision": 4}, "entry": None}
            )
        return httpx.Response(200, json={"entries": [PC_ENTRY]})

    memory = PowerContextMemory(_client(handler))
    out = await memory.remember(
        MemoryEntry(
            scope_id="scp-1",
            kind="decision",
            content="目录用 seekdb 存",
            tags=["decision", "railway"],
        )
    )

    assert out.id == "mem-1"
    assert out.active is True
    assert out.tags == ["decision", "railway"]
    assert out.citation is not None
    assert out.citation.source.checksum == "4"
    assert seen == ["/v1/memory/remember", "/v1/memory/entries/list"]


async def test_remember_of_unknown_duplicate_still_translates() -> None:
    """entry=null but nothing matching locally: never a silent success."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/remember"):
            return httpx.Response(
                200, json={"memory": {"revision": 4}, "entry": None}
            )
        return httpx.Response(200, json={"entries": []})

    memory = PowerContextMemory(_client(handler))
    with pytest.raises(SWError) as excinfo:
        await memory.remember(
            MemoryEntry(scope_id="s", kind="constraint", content="c")
        )
    assert "neither a new nor an existing entry" in excinfo.value.message


async def test_ensure_scope_missing_scope_id_translates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"items": []})
        return httpx.Response(200, json={"id": "unexpected"})

    with pytest.raises(SWError):
        await _client(handler).ensure_scope("sw:x", "summary")


def test_decode_ref_rejects_malformed_rev() -> None:
    """Audit B-10: garbage revision must raise SWError, not ValueError."""
    with pytest.raises(SWError):
        decode_ref("handoff:not-a-ref")


async def test_continue_with_malformed_rev_raises_swerror() -> None:
    handoff = PowerContextHandoff(_client(lambda r: httpx.Response(200, json={})))
    with pytest.raises(SWError):
        await handoff.continue_("scp-1", "junk")
