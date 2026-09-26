"""The seekdb boundary must bound its own waits (docs/03 §7.1).

`pyseekdb.RemoteServerClient` takes no read timeout, so a wedged backend —
the usual symptom of WSL reclaiming the containers mid-run — would otherwise
leave `run_op` awaiting a worker thread forever.
"""
from __future__ import annotations

import time

import pytest

from specweaver.adapters.driven.seekdb import client as client_mod
from specweaver.adapters.driven.seekdb.client import SeekdbClient
from specweaver.shared.config import Settings
from specweaver.shared.errors import SWError


def _client() -> SeekdbClient:
    return SeekdbClient(Settings().seekdb, dimension=4)


async def test_a_wedged_backend_surfaces_as_the_domain_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client_mod, "OP_TIMEOUT_SECONDS", 0.05)

    def wedged() -> str:
        time.sleep(0.3)
        return "too late"

    with pytest.raises(SWError, match="timed out"):
        await _client().run_op(wedged, "probe")


async def test_a_failing_backend_still_translates_to_the_domain_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client_mod, "OP_TIMEOUT_SECONDS", 5)

    def boom() -> None:
        raise OSError("connection reset")

    with pytest.raises(SWError, match="probe failed"):
        await _client().run_op(boom, "probe")
