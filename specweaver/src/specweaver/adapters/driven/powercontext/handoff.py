from __future__ import annotations

import uuid

from ....domain.ports.handoff import HandoffDraft, HandoffView
from .client import PowerContextClient


def encode_ref(ref: dict) -> str:
    return f"{ref['family']}:{ref['artifact_id']}:{ref['revision']}"


def decode_ref(rev: str) -> dict:
    family, artifact_id, revision = rev.split(":")
    return {
        "family": family,
        "artifact_id": artifact_id,
        "revision": int(revision),
    }


def _claim(text: str) -> dict:
    return {"text": text, "basis": "declared", "evidence": []}


def content_to_view(scope_id: str, content: dict, raw: dict | None = None):
    state = [s.get("text", "") for s in content.get("state", [])]
    next_action = content.get("next_action") or {}
    omissions = [
        o.get("text", "") if isinstance(o, dict) else str(o)
        for o in content.get("omissions", [])
    ]
    return HandoffView(
        scope_id=scope_id,
        objective=content.get("objective", ""),
        progress="\n".join(s for s in state if s),
        next_steps=[next_action.get("text", "")] if next_action else [],
        unverified=omissions,
        raw=raw or {},
    )


class PowerContextHandoff:
    def __init__(self, client: PowerContextClient) -> None:
        self._client = client

    async def prepare_current(self, draft: HandoffDraft) -> HandoffView:
        # PC contract (docs/02 §7.4 实测): state items and non-null
        # next_action.text must be non-blank; same source_id with different
        # content is a 409, so an unset source gets a unique milestone id.
        state = [s.strip() for s in draft.state if s.strip()]
        omissions = [o.strip() for o in draft.omissions if o.strip()]
        next_steps = [n.strip() for n in draft.next_steps if n.strip()]
        source_id = draft.source_id or (
            f"sw-handoff-{draft.scope_id}-{uuid.uuid4().hex[:8]}"
        )
        payload = {
            "scope_id": draft.scope_id,
            "source_id": source_id,
            "handoff": {
                "schema": "powercontext.current-work-handoff.v1",
                "trust": "untrusted_input",
                "objective": draft.objective,
                "state": [_claim(s) for s in state],
                "disposition": draft.disposition,
                "next_action": (
                    _claim(next_steps[0]) if next_steps else None
                ),
                "omissions": omissions,
            },
        }
        res = await self._client.post(
            "/v1/work/handoffs/prepare-current", payload
        )
        prepared = res["handoff"]
        view = content_to_view(draft.scope_id, prepared["content"])
        view.raw = {"prepared": prepared, "source_id": source_id}
        return view

    async def commit(self, view: HandoffView) -> HandoffView:
        prepared = view.raw["prepared"]
        res = await self._client.post(
            "/v1/handoff/commit",
            {"scope_id": view.scope_id, "handoff": prepared},
        )
        view.rev = encode_ref(res["reference"])
        view.raw = dict(view.raw)
        view.raw["committed"] = res
        return view

    async def continue_(self, scope_id: str, rev: str) -> HandoffView:
        res = await self._client.post(
            "/v1/handoff/continue",
            {
                "scope_id": scope_id,
                "selection": "exact",
                "revision": decode_ref(rev),
            },
        )
        content = res["content"]
        return content_to_view(scope_id, content)

    async def record_outcome(
        self, scope_id: str, source_id: str, outcome: dict
    ) -> None:
        observations = outcome.get("observations") or [
            outcome.get("summary") or outcome.get("objective") or "task updated"
        ]
        task_outcome = {
            "schema": "powercontext.task-outcome.v1",
            "trust": "untrusted_observation",
            "objective": outcome.get("objective", ""),
            "status": outcome.get("status", "unknown"),
            "summary": outcome.get("summary", ""),
            "observations": [_claim(o) for o in observations],
            "checks": [
                {
                    "name": c.get("name", "check"),
                    "status": c.get("status", "unknown"),
                    "details": c.get("details", ""),
                    "basis": "declared",
                    "evidence": [],
                }
                for c in outcome.get("checks", [])
            ],
            "produced_artifacts": outcome.get("produced_artifacts", []),
            "remaining_work": outcome.get("remaining_work", []),
        }
        await self._client.post(
            "/v1/work/outcomes/record",
            {
                "scope_id": scope_id,
                "source_id": source_id,
                "outcome": task_outcome,
            },
        )
