"""VerifyState: the standalone three-way consistency report.

workspace <-> catalog (engineering cross-check), catalog <-> activity log
(latest change set / test run freshness, junit report reconciliation) and
catalog <-> memory (rule artifacts vs constraint entries). ResumeTask uses
the same workspace check through consistency.check_artifacts.
"""
from __future__ import annotations

from pydantic import BaseModel

from ...domain.enums import ArtifactType
from ...domain.ports.activity import ActivityLogPort
from ...domain.ports.catalog import ArtifactFilter, CatalogPort
from ...domain.ports.memory import MemoryPort
from ...domain.ports.workspace import TestRunnerPort, WorkspacePort
from ...shared.errors import SWError
from .base import UseCase
from .consistency import StateMismatch, check_artifacts


class VerifyStateRequest(BaseModel):
    project_id: str
    scope_id: str = ""


class VerifyStateReport(BaseModel):
    project_id: str
    current_ref: str = ""
    checked: int = 0
    mismatches: list[StateMismatch] = []
    last_change_set_id: str | None = None
    change_set_stale: bool | None = None
    last_test_run_id: str | None = None
    test_report: str = "absent"  # absent | consistent | diverged | unparsable
    rules_in_catalog: int = 0
    constraint_entries_in_memory: int | None = None
    notes: list[str] = []


class VerifyState(UseCase):
    """Consistency report across workspace, seekdb catalog and memory."""

    name = "verify_state"

    def __init__(
        self,
        catalog: CatalogPort | None,
        workspace: WorkspacePort,
        telemetry,
        activity: ActivityLogPort | None = None,
        memory: MemoryPort | None = None,
        test_runner: TestRunnerPort | None = None,
    ) -> None:
        super().__init__(telemetry)
        self._catalog = catalog
        self._workspace = workspace
        self._activity = activity
        self._memory = memory
        self._test_runner = test_runner

    async def __call__(
        self, request: VerifyStateRequest
    ) -> VerifyStateReport:
        with self.span():
            if self._catalog is None:
                raise SWError(
                    "verify_state requires the seekdb catalog; "
                    "run `specweaver doctor`"
                )
            artifacts = await self._catalog.list_artifacts(
                ArtifactFilter(project_id=request.project_id)
            )
            report = VerifyStateReport(
                project_id=request.project_id,
                current_ref=await self._workspace.current_ref(),
                checked=len(artifacts),
                mismatches=await check_artifacts(
                    artifacts, self._workspace
                ),
                rules_in_catalog=sum(
                    1
                    for a in artifacts
                    if a.type == ArtifactType.rule
                ),
            )
            await self._check_activity(request, report)
            await self._check_memory(request, report)
            return report

    async def _check_activity(
        self, request: VerifyStateRequest, report: VerifyStateReport
    ) -> None:
        if self._activity is None:
            report.notes.append("activity log unavailable; skipped")
            return
        try:
            change_sets = await self._activity.list_change_sets(
                request.project_id
            )
            test_runs = await self._activity.list_test_runs(
                request.project_id
            )
        except SWError as exc:
            report.notes.append(f"activity check unavailable: {exc.message}")
            return
        if change_sets:
            latest = change_sets[0]
            report.last_change_set_id = latest.id
            if latest.head_checksum:
                report.change_set_stale = (
                    latest.head_checksum != report.current_ref
                )
                if report.change_set_stale:
                    report.notes.append(
                        "workspace moved past the last recorded change "
                        f"set ({latest.head_checksum[:8]}... -> "
                        f"{report.current_ref[:8]}...); run complete_task"
                    )
        if not test_runs:
            report.notes.append("no recorded test runs for this project")
            return
        latest_run = test_runs[0]
        report.last_test_run_id = latest_run.id
        if not latest_run.report_ref:
            report.notes.append(
                "last test run recorded no junit report_ref; counts come "
                "from the activity log alone"
            )
            return
        if self._test_runner is None:
            report.notes.append("no test runner port; junit report unparsed")
            return
        try:
            parsed = await self._test_runner.parse_report(
                latest_run.report_ref
            )
        except SWError as exc:
            report.test_report = "unparsable"
            report.notes.append(f"junit report unparsable: {exc.message}")
            return
        consistent = (
            parsed.total == latest_run.total
            and parsed.passed == latest_run.passed
            and parsed.failed == latest_run.failed
        )
        report.test_report = "consistent" if consistent else "diverged"
        if not consistent:
            report.notes.append(
                f"recorded run {latest_run.passed}/{latest_run.total} vs "
                f"junit report {parsed.passed}/{parsed.total}"
            )

    async def _check_memory(
        self, request: VerifyStateRequest, report: VerifyStateReport
    ) -> None:
        if self._memory is None or not request.scope_id:
            report.notes.append(
                "memory check skipped (no scope_id or memory port)"
            )
            return
        try:
            entries = await self._memory.list_entries(
                request.scope_id, include_inactive=True
            )
        except SWError as exc:
            report.notes.append(f"memory check unavailable: {exc.message}")
            return
        report.constraint_entries_in_memory = sum(
            1 for e in entries if e.kind == "constraint" and e.active
        )
        if report.constraint_entries_in_memory < report.rules_in_catalog:
            report.notes.append(
                f"{report.rules_in_catalog} rule artifacts vs "
                f"{report.constraint_entries_in_memory} active constraint "
                "memory entries: some rules were never precipitated"
            )
