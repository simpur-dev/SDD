from __future__ import annotations

import time

from pydantic import BaseModel

from ...domain.ports.activity import ActivityLogPort
from ...domain.ports.catalog import ArtifactFilter, CatalogPort
from ...domain.ports.memory import MemoryEntry, MemoryPort
from ...domain.ports.workspace import (
    TestRunnerPort,
    WorkspacePort,
)
from ..engines.reconciliation import ReconciliationEngine
from .base import UseCase


class CompleteTaskRequest(BaseModel):
    project_id: str
    task_id: str
    scope_id: str = ""
    base_ref: str
    test_command: str = "pytest"
    register_outcome: bool = True


class CompleteTaskReport(BaseModel):
    task_id: str
    success: bool
    test_total: int
    test_passed: int
    test_failed: int
    files_changed: int
    updated_ids: list[str]
    superseded_ids: list[str]
    change_set_id: str | None = None
    test_run_id: str


class CompleteTask(UseCase):
    """Core write path: run tests, reconcile artifacts, record change set/outcome."""

    name = "complete_task"

    def __init__(
        self,
        engine: ReconciliationEngine,
        catalog: CatalogPort | None,
        activity: ActivityLogPort | None,
        workspace: WorkspacePort,
        test_runner: TestRunnerPort,
        telemetry,
        memory: MemoryPort | None = None,
    ) -> None:
        super().__init__(telemetry)
        self._engine = engine
        self._catalog = catalog
        self._activity = activity
        self._workspace = workspace
        self._test_runner = test_runner
        self._memory = memory

    async def __call__(
        self, request: CompleteTaskRequest
    ) -> CompleteTaskReport:
        with self.span():
            head_ref = await self._workspace.current_ref()
            test_run = await self._test_runner.run(request.test_command)
            test_run.project_id = request.project_id
            test_run.task_id = request.task_id
            test_run.commit_ref = head_ref
            if self._activity is not None:
                await self._activity.record_test_run(test_run)

            success = test_run.failed == 0
            change_set_id = None
            updated_ids: list[str] = []
            superseded_ids: list[str] = []
            files_changed = 0

            if success and self._catalog is not None:
                existing_list = await self._catalog.list_artifacts(
                    ArtifactFilter(project_id=request.project_id)
                )
                existing = {a.id: a for a in existing_list}
                change_id = f"cs-{int(time.time() * 1000)}"
                result = await self._engine.run(
                    request.project_id,
                    request.task_id,
                    self._workspace,
                    request.base_ref,
                    head_ref,
                    existing,
                    change_id,
                )
                result.change_set.test_run_id = test_run.id
                files_changed = len(result.change_set.files_changed)
                for artifact in result.updated:
                    await self._catalog.upsert_artifact(artifact)
                for artifact in result.superseded:
                    await self._catalog.upsert_artifact(artifact)
                for relation in result.relations:
                    await self._catalog.upsert_relation(relation)
                if self._activity is not None:
                    await self._activity.record_change_set(
                        result.change_set
                    )
                change_set_id = result.change_set.id
                updated_ids = [a.id for a in result.updated]
                superseded_ids = [a.id for a in result.superseded]

            if (
                request.register_outcome
                and self._memory is not None
                and request.scope_id
            ):
                await self._memory.remember(
                    MemoryEntry(
                        scope_id=request.scope_id,
                        kind="task_outcome",
                        content=(
                            f"Task {request.task_id}: tests "
                            f"{test_run.passed}/{test_run.total}, "
                            f"{len(updated_ids)} artifacts updated"
                        ),
                        tags=["outcome", request.project_id],
                    )
                )

            return CompleteTaskReport(
                task_id=request.task_id,
                success=success,
                test_total=test_run.total,
                test_passed=test_run.passed,
                test_failed=test_run.failed,
                files_changed=files_changed,
                updated_ids=updated_ids,
                superseded_ids=superseded_ids,
                change_set_id=change_set_id,
                test_run_id=test_run.id,
            )
