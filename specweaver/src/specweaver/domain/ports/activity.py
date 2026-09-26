from __future__ import annotations

from typing import Protocol

from ..entities import ChangeSet, TestRun


class ActivityLogPort(Protocol):
    """Records task activity: structured change sets and test runs (evidence).

    list_* return entries newest-first, so index 0 is the most recent.
    """

    async def record_change_set(self, change_set: ChangeSet) -> None: ...

    async def record_test_run(self, test_run: TestRun) -> None: ...

    async def list_test_runs(
        self, project_id: str, task_id: str | None = None
    ) -> list[TestRun]: ...

    async def list_change_sets(
        self, project_id: str, task_id: str | None = None
    ) -> list[ChangeSet]: ...
