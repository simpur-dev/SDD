from __future__ import annotations

from specweaver.domain.entities import ChangeSet, TestRun


class InMemoryActivityLog:
    def __init__(self) -> None:
        self.change_sets: list[ChangeSet] = []
        self.test_runs: list[TestRun] = []

    async def record_change_set(self, change_set: ChangeSet) -> None:
        self.change_sets.append(change_set)

    async def record_test_run(self, test_run: TestRun) -> None:
        self.test_runs.append(test_run)

    async def list_test_runs(
        self, project_id: str, task_id: str | None = None
    ) -> list[TestRun]:
        out = [
            tr for tr in reversed(self.test_runs) if tr.project_id == project_id
        ]
        if task_id is not None:
            out = [tr for tr in out if tr.task_id == task_id]
        return out

    async def list_change_sets(
        self, project_id: str, task_id: str | None = None
    ) -> list[ChangeSet]:
        out = [
            cs for cs in reversed(self.change_sets) if cs.project_id == project_id
        ]
        if task_id is not None:
            out = [cs for cs in out if cs.task_id == task_id]
        return out
