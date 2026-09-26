from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

from ....domain.entities import Artifact, Relation
from ....domain.enums import ArtifactType, RelationKind
from .parsers.base import ParsedDocument


@dataclass(frozen=True)
class _EdgeKey:
    src: str
    dst: str
    kind: RelationKind


def edge_id(project_id: str, src: str, kind: RelationKind, dst: str) -> str:
    """Deterministic project-scoped edge id (seekdb uq_edge convention)."""
    raw = f"{project_id}|{src}|{kind}|{dst}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _classify_explicit(
    source: ArtifactType, target: ArtifactType
) -> RelationKind | None:
    if source == ArtifactType.code and target in (
        ArtifactType.requirement,
        ArtifactType.design,
    ):
        return RelationKind.realizes
    if source == ArtifactType.design and target == ArtifactType.requirement:
        return RelationKind.realizes
    if source == ArtifactType.test and target == ArtifactType.requirement:
        return RelationKind.covers
    if source == ArtifactType.test and target in (
        ArtifactType.code,
        ArtifactType.design,
    ):
        return RelationKind.tests
    if source == ArtifactType.rule:
        return RelationKind.constrains
    if (
        source == ArtifactType.requirement
        and target == ArtifactType.requirement
    ):
        return RelationKind.refines
    return None


class _EdgeAccumulator:
    def __init__(self) -> None:
        self._edges: dict[_EdgeKey, tuple[float, str]] = {}

    def add(
        self,
        src: str,
        dst: str,
        kind: RelationKind,
        confidence: float,
        evidence: str,
    ) -> None:
        key = _EdgeKey(src, dst, kind)
        existing = self._edges.get(key)
        if existing is None or confidence > existing[0]:
            self._edges[key] = (confidence, evidence)

    def relations(self, project_id: str) -> list[Relation]:
        out: list[Relation] = []
        for key, (confidence, evidence) in self._edges.items():
            out.append(
                Relation(
                    id=edge_id(project_id, key.src, key.kind, key.dst),
                    project_id=project_id,
                    src=key.src,
                    dst=key.dst,
                    kind=key.kind,
                    confidence=confidence,
                    evidence=evidence,
                )
            )
        return sorted(out, key=lambda r: r.id)


def mine_relations(
    project_id: str, pairs: list[tuple[ParsedDocument, Artifact]]
) -> list[Relation]:
    """Fuse explicit tags, AST structure and naming conventions into edges."""
    by_id: dict[str, tuple[ParsedDocument, Artifact]] = {}
    code_by_stem: dict[str, str] = {}
    for doc, artifact in pairs:
        by_id[artifact.id] = (doc, artifact)
        if artifact.type == ArtifactType.code:
            stem = os.path.splitext(
                doc.path.replace("\\", "/").rsplit("/", 1)[-1]
            )[0]
            code_by_stem.setdefault(stem, artifact.id)

    acc = _EdgeAccumulator()

    # evidence 1: explicit tags / references
    for doc, artifact in pairs:
        for ref in doc.references:
            # audit B3: a file quoting its own id (front-matter always does)
            # is not a traceability edge
            if ref == artifact.id:
                continue
            target = by_id.get(ref)
            if target is None:
                continue
            kind = _classify_explicit(artifact.type, target[1].type)
            if kind is not None:
                acc.add(
                    artifact.id,
                    target[1].id,
                    kind,
                    0.95,
                    f"explicit reference to {ref}",
                )

    # evidence 2/3: AST imports and test naming conventions
    for doc, artifact in pairs:
        if artifact.type == ArtifactType.test:
            target_module = doc.front_matter.get("test_target_module")
            code_id = code_by_stem.get(str(target_module))
            if code_id is not None:
                acc.add(
                    artifact.id,
                    code_id,
                    RelationKind.tests,
                    0.6,
                    f"naming convention test_{target_module}",
                )
        elif artifact.type == ArtifactType.code:
            for imported in doc.imports:
                top = imported.split(".", 1)[0]
                code_id = code_by_stem.get(top)
                if code_id is not None and code_id != artifact.id:
                    acc.add(
                        artifact.id,
                        code_id,
                        RelationKind.depends_on,
                        0.85,
                        f"imports {imported}",
                    )

    # evidence 3: module/path naming convention links implementation to requirements
    requirements_by_module: dict[str, list[str]] = {}
    for _doc, artifact in pairs:
        if artifact.type == ArtifactType.requirement and artifact.module:
            requirements_by_module.setdefault(
                artifact.module, []
            ).append(artifact.id)
    for _doc, artifact in pairs:
        if artifact.type not in (
            ArtifactType.design,
            ArtifactType.code,
        ) or not artifact.module:
            continue
        for requirement_id in requirements_by_module.get(
            artifact.module, []
        ):
            acc.add(
                artifact.id,
                requirement_id,
                RelationKind.realizes,
                0.6,
                f"module naming convention '{artifact.module}'",
            )

    return acc.relations(project_id)
