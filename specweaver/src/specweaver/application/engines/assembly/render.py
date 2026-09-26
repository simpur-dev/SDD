from __future__ import annotations

import re

from ....domain.entities import Artifact, ContextBundle
from ....domain.enums import ArtifactType
from ....domain.values import Citation, Finding

_SIGNATURE_RE = re.compile(r"^\s*(async\s+def|def|class)\s")
_CODE_TYPES = frozenset({ArtifactType.code, ArtifactType.test})
_CODE_SUMMARY_LINES = 12
_CODE_SUMMARY_CHARS = 700


def citation_tag(artifact: Artifact) -> str:
    source = artifact.source
    if source is not None:
        locator = f"#{source.locator}" if source.locator else ""
        pointer = f"{source.uri}{locator}"
    else:
        pointer = artifact.id
    return f"[{artifact.id} v{artifact.version} · {pointer}]"


def _summarize_code(content: str) -> str:
    signatures = [
        line.strip()
        for line in content.splitlines()
        if _SIGNATURE_RE.match(line)
    ]
    text = "\n".join(signatures[:_CODE_SUMMARY_LINES])
    if len(text) > _CODE_SUMMARY_CHARS:
        text = text[:_CODE_SUMMARY_CHARS] + " …"
    if not text:
        text = content[:_CODE_SUMMARY_CHARS]
    return text + "\n(full source: see the citation uri)"


def entry_block(artifact: Artifact) -> str:
    """Render one artifact; code/tests are summarized for progressive disclosure."""
    heading = f"### {artifact.title}  {citation_tag(artifact)}"
    if artifact.type in _CODE_TYPES:
        body = _summarize_code(artifact.content)
    else:
        body = artifact.content.strip()
    return f"{heading}\n{body}"


def _finding_line(finding: Finding) -> str:
    refs = ", ".join(c.artifact_id for c in finding.refs)
    confirm = " [needs confirmation]" if finding.needs_confirmation else ""
    lines = [f"- ({finding.severity.value}/{finding.kind.value}){confirm} "
             f"{finding.message}"]
    if finding.suggestion:
        lines.append(f"    suggestion: {finding.suggestion}")
    if refs:
        lines.append(f"    sources: {refs}")
    return "\n".join(lines)


def findings_block(findings: list[Finding]) -> str:
    if not findings:
        return "- none"
    return "\n".join(_finding_line(f) for f in findings)


def _entries(artifacts: list[Artifact]) -> str:
    if not artifacts:
        return "_(none)_"
    return "\n\n".join(entry_block(a) for a in artifacts)


def _status_lines(bundle: ContextBundle) -> str:
    task = bundle.task
    lines = [
        f"- task id: {task.id}",
        f"- phase: {task.phase.value}",
        f"- base ref: {task.base_ref or '(unspecified)'}",
    ]
    cited = ", ".join(c.artifact_id for c in bundle.citations) or "(none)"
    lines.append(f"- sources cited: {cited}")
    return "\n".join(lines)


def render_markdown(bundle: ContextBundle) -> str:
    budget = bundle.budget
    if budget is not None:
        usage = f"{budget.used_bytes}/{budget.max_bytes} bytes"
        trunc = (
            "\n- warning: context truncated to budget; some relevant artifacts "
            "were omitted (request a larger budget if needed)"
            if budget.truncated
            else ""
        )
    else:
        usage = "unknown"
        trunc = ""
    sections = [
        f"# Context: {bundle.task.title}",
        "## ① Current goal and effective constraints\n"
        + _entries(bundle.goal_and_constraints),
        "## ② Related design and implementation\n"
        + _entries(bundle.design_and_implementation),
        "## ③ Verification method and results\n"
        + _entries(bundle.verification),
        "## ④ Task status and sources\n" + _status_lines(bundle),
        "## ⑤ Findings (conflicts · gaps · confirmations)\n"
        + findings_block(bundle.findings),
        "## ⑥ Budget and usage\n"
        f"- context size: {usage}\n"
        f"- generated at: {bundle.generated_at}{trunc}",
    ]
    return "\n\n".join(sections)


def render_json(bundle: ContextBundle) -> str:
    return bundle.model_dump_json(indent=2)


def citations_for(artifacts: list[Artifact]) -> list[Citation]:
    from ..validity.citations import cite

    return [cite(artifact) for artifact in artifacts]
