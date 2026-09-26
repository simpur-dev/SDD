"""Reusable port-contract suites, shared by fakes and real adapters."""

from __future__ import annotations

from specweaver.domain.entities import Artifact, Relation
from specweaver.domain.enums import (
    ArtifactType,
    LifecycleStatus,
    RelationKind,
)
from specweaver.domain.ports.catalog import (
    ArtifactFilter,
    HybridQuery,
)
from specweaver.domain.ports.handoff import HandoffDraft
from specweaver.domain.ports.memory import MemoryEntry


def vec(seed, dim=8):
    return [
        round(float((seed * (j + 1)) % 9) / 9, 4) for j in range(dim)
    ]


def make_artifacts(project="p") -> list[Artifact]:
    return [
        Artifact(id="req-1", project_id=project,
                 type=ArtifactType.requirement, title="发车时间需求",
                 content="调度员可按站点调整列车发车时间，重新计算时刻",
                 status=LifecycleStatus.active, embedding=vec(1)),
        Artifact(id="des-1", project_id=project, type=ArtifactType.design,
                 module="schedule", title="时刻设计",
                 content="schedule 按偏移量重新计算发车时刻",
                 status=LifecycleStatus.active, embedding=vec(2)),
        Artifact(id="code-1", project_id=project, type=ArtifactType.code,
                 module="schedule", title="schedule.py",
                 content="def recalc_departure 计算发车时刻",
                 status=LifecycleStatus.active, embedding=vec(3)),
        Artifact(id="test-1", project_id=project, type=ArtifactType.test,
                 module="schedule", title="test_schedule.py",
                 content="test_recalc_departure 验证发车时刻",
                 status=LifecycleStatus.active, embedding=vec(4)),
        Artifact(id="code-old", project_id=project, type=ArtifactType.code,
                 module="schedule", title="old_schedule.py",
                 content="旧的发车时刻逻辑，已被取代",
                 status=LifecycleStatus.superseded, embedding=vec(9)),
    ]


async def catalog_suite(catalog) -> None:
    artifacts = make_artifacts()
    for artifact in artifacts:
        await catalog.upsert_artifact(artifact)

    got = await catalog.get_artifact("p", "code-1")
    assert got is not None
    assert got.title == "schedule.py"
    assert got.embedding[0] == artifacts[2].embedding[0]

    req_only = await catalog.list_artifacts(
        ArtifactFilter(project_id="p", types=[ArtifactType.requirement])
    )
    assert {a.id for a in req_only} == {"req-1"}

    in_module = await catalog.list_artifacts(
        ArtifactFilter(project_id="p", modules=["schedule"])
    )
    assert {a.id for a in in_module} == {
        "des-1", "code-1", "test-1", "code-old"
    }

    active = await catalog.list_artifacts(
        ArtifactFilter(project_id="p", status=LifecycleStatus.active)
    )
    assert "code-old" not in {a.id for a in active}

    edges = [
        ("req-1", "des-1", RelationKind.refines),
        ("des-1", "code-1", RelationKind.realizes),
        ("test-1", "code-1", RelationKind.tests),
    ]
    for src, dst, kind in edges:
        await catalog.upsert_relation(
            Relation(project_id="p", src=src, dst=dst, kind=kind)
        )

    one_hop = await catalog.neighbors(
        "p", "req-1", [RelationKind.refines], depth=1
    )
    assert {a.id for a in one_hop} == {"des-1"}

    chain = await catalog.neighbors(
        "p",
        "req-1",
        [RelationKind.refines, RelationKind.realizes,
         RelationKind.tests],
        depth=3,
    )
    assert {a.id for a in chain} == {"des-1", "code-1", "test-1"}


async def catalog_isolation_suite(catalog) -> None:
    """Artifact ids collide across projects (REQ-1); access must stay scoped."""
    shared = make_artifacts("iso-a") + make_artifacts("iso-b")
    for artifact in shared:
        await catalog.upsert_artifact(artifact)

    only_a = await catalog.get_artifact("iso-a", "code-1")
    other = await catalog.get_artifact("iso-b", "code-1")
    assert only_a is not None and other is not None
    assert {only_a.project_id, other.project_id} == {"iso-a", "iso-b"}

    await catalog.upsert_relation(
        Relation(
            project_id="iso-a", src="req-1", dst="des-1",
            kind=RelationKind.refines,
        )
    )
    await catalog.upsert_relation(
        Relation(
            project_id="iso-b", src="req-1", dst="code-old",
            kind=RelationKind.refines,
        )
    )
    from_a = await catalog.neighbors(
        "iso-a", "req-1", [RelationKind.refines], depth=2
    )
    assert {a.id for a in from_a} == {"des-1"}


async def hybrid_suite(hybrid) -> None:
    query = HybridQuery(
        project_id="p", text="发车", query_embedding=vec(3), n_results=5
    )
    hits = await hybrid.hybrid_search(query)
    ids = [h.artifact.id for h in hits]
    assert "code-1" in ids
    assert all(h.artifact.project_id == "p" for h in hits)
    assert "code-old" not in ids  # only_active by default

    without_filter = HybridQuery(
        project_id="p", text="旧", query_embedding=vec(9),
        n_results=5, only_active=False,
    )
    old_hits = await hybrid.hybrid_search(without_filter)
    assert "code-old" in [h.artifact.id for h in old_hits]


async def memory_suite(memory, project_id: str) -> None:
    scope_id = await memory.resolve_scope(project_id)
    assert scope_id
    assert await memory.resolve_scope(project_id) == scope_id

    e1 = await memory.remember(
        MemoryEntry(scope_id=scope_id, kind="constraint",
                    content="必须保留原有发车时刻计算行为")
    )
    assert e1.id and e1.citation
    e2 = await memory.remember(
        MemoryEntry(scope_id=scope_id, kind="decision",
                    content="发车时间调整需联动重新检查 occupancy")
    )

    hits = await memory.search(scope_id, "发车", n=5)
    assert e1.id in {h.id for h in hits}

    listed = await memory.list_entries(scope_id)
    assert len(listed) == 2

    revised = await memory.revise(
        e1.citation, "必须保留原有发车时刻计算行为（已更新）"
    )
    assert "已更新" in revised.content

    await memory.retire(e2.citation, "该决策已过时")
    active = await memory.list_entries(scope_id)
    assert e2.id not in {h.id for h in active}

    everything = await memory.list_entries(
        scope_id, include_inactive=True
    )
    assert len(everything) == 2


async def handoff_suite(handoff, scope_id: str, source_id: str):
    draft = HandoffDraft(
        scope_id=scope_id,
        source_id=source_id,
        objective="为铁路调度增加按站调整发车时间",
        state=["已更新 schedule 时刻计算", "已联动 occupancy 重新检查"],
        next_steps=["回归 publish 发布判断"],
        omissions=["publish 回归测试尚未执行"],
        disposition="continuable",
    )
    view = await handoff.prepare_current(draft)
    assert view.objective == "为铁路调度增加按站调整发车时间"
    assert "schedule" in view.progress
    assert view.next_steps == ["回归 publish 发布判断"]
    assert view.unverified == ["publish 回归测试尚未执行"]

    view = await handoff.commit(view)
    assert view.rev

    resumed = await handoff.continue_(scope_id, view.rev)
    assert resumed.objective == "为铁路调度增加按站调整发车时间"
    assert "occupancy" in resumed.progress
    assert resumed.next_steps == ["回归 publish 发布判断"]
    assert resumed.unverified == ["publish 回归测试尚未执行"]

    await handoff.record_outcome(
        scope_id,
        f"{source_id}::outcome",
        {
            "objective": draft.objective,
            "status": "partial",
            "summary": "schedule/occupancy 已改，publish 待回归",
            "remaining_work": ["回归 publish"],
        },
    )
    return view
