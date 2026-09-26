"""Relevance-driven ordering and budget trimming (docs/01 §4.4, aider-style).

Before this, the retrieval score was dropped at the assembly boundary, so the
budget cut whatever happened to sort last instead of what was least relevant.
"""
from __future__ import annotations

from fakes.catalog import InMemoryCatalog, InMemoryHybridSearch
from fakes.inference import ScriptedEmbedding

from specweaver.application.engines.assembly import AssemblyEngine
from specweaver.application.engines.assembly.sections import map_sections
from specweaver.application.engines.retrieval import (
    GraphExpander,
    QueryPlanner,
    RetrievalEngine,
)
from specweaver.application.engines.validity import (
    ConflictDetector,
    GapDetector,
    LifecycleValidator,
    ProvenanceDetector,
    SuspectDetector,
    ValidityEngine,
)
from specweaver.application.usecases.get_context import (
    GetContext,
    GetContextRequest,
)
from specweaver.domain.entities import Artifact, Task
from specweaver.domain.enums import ArtifactType
from specweaver.shared.telemetry import Telemetry


def _artifact(
    artifact_id: str,
    type: ArtifactType,
    content: str = "x" * 40,
    module: str = "m",
) -> Artifact:
    return Artifact(
        id=artifact_id,
        project_id="p",
        type=type,
        module=module,
        title=artifact_id,
        content=content,
    )


def _task() -> Task:
    return Task(
        id="t1", project_id="p", title="t", objective="adjust departure"
    )


def test_relevance_orders_within_a_type_but_never_across_types() -> None:
    low = _artifact("REQ-1", ArtifactType.requirement)
    high = _artifact("REQ-2", ArtifactType.requirement)
    rule = _artifact("RULE-1", ArtifactType.rule)

    sections = map_sections(
        [low, high, rule], relevance={high.id: 0.9, low.id: 0.1}
    )

    # RULE-1 scored nothing yet stays ahead of both requirements: the link
    # role of a constraint outranks any similarity score.
    assert [a.id for a in sections.goal_and_constraints] == [
        "RULE-1",
        "REQ-2",
        "REQ-1",
    ]


async def test_budget_drops_the_least_relevant_entry_first() -> None:
    strict = _artifact("CODE-1", ArtifactType.code, content="c" * 400)
    related = _artifact("CODE-2", ArtifactType.code, content="d" * 400)
    artifacts = [strict, related]

    without = await AssemblyEngine(1400).run(
        _task(), artifacts, findings=[]
    )
    with_relevance = await AssemblyEngine(1400).run(
        _task(), artifacts, findings=[], relevance={related.id: 5.0}
    )

    assert with_relevance.budget.truncated
    assert with_relevance.budget.used_bytes <= 1400
    kept_without = {a.id for a in without.design_and_implementation}
    kept_with = {a.id for a in with_relevance.design_and_implementation}
    assert kept_without == {"CODE-1"}  # id order wins when nothing is scored
    assert kept_with == {"CODE-2"}


class _RecordingAssembly(AssemblyEngine):
    def __init__(self) -> None:
        super().__init__(8000)
        self.seen_relevance: dict[str, float] | None = None

    async def run(
        self,
        task,
        valid,
        findings,
        last_test_run=None,
        relevance=None,
    ):
        self.seen_relevance = relevance
        return await super().run(
            task,
            valid,
            findings,
            last_test_run=last_test_run,
            relevance=relevance,
        )


async def test_get_context_hands_retrieval_scores_to_assembly() -> None:
    catalog = InMemoryCatalog()
    await catalog.upsert_artifact(
        _artifact("REQ-7", ArtifactType.requirement, content="调整 发车时间")
    )
    assembly = _RecordingAssembly()
    usecase = GetContext(
        RetrievalEngine(
            QueryPlanner(None),
            ScriptedEmbedding(8),
            InMemoryHybridSearch(catalog),
            GraphExpander(catalog, depth=1),
            n_results=5,
        ),
        ValidityEngine(
            LifecycleValidator(),
            ConflictDetector(),
            GapDetector(catalog),
            SuspectDetector(catalog),
            ProvenanceDetector(),
        ),
        assembly,
        Telemetry(),
    )

    await usecase(
        GetContextRequest(project_id="p", task_text="调整 发车时间")
    )

    assert assembly.seen_relevance is not None
    assert "REQ-7" in assembly.seen_relevance
    assert isinstance(assembly.seen_relevance["REQ-7"], float)
