from __future__ import annotations

import json
from datetime import datetime

from ....domain.entities import ChangeSet, FileChange, TestRun

CHANGESET_TABLE = "sw_change_set"
TESTRUN_TABLE = "sw_test_run"


class SeekdbActivityLog:
    """Stores change sets and test runs in seekdb SQL tables."""

    def __init__(self, client) -> None:
        self._client = client

    async def record_test_run(self, test_run: TestRun) -> None:
        sql = (
            f"INSERT INTO {TESTRUN_TABLE} "
            "(test_run_id,task_id,project_id,command,total,passed,failed,"
            "skipped,commit_ref,report_ref,ts) VALUES "
            "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
            "total=VALUES(total),passed=VALUES(passed),failed=VALUES(failed),"
            "skipped=VALUES(skipped),commit_ref=VALUES(commit_ref)"
        )
        args = (
            test_run.id,
            test_run.task_id,
            test_run.project_id,
            test_run.command,
            test_run.total,
            test_run.passed,
            test_run.failed,
            test_run.skipped,
            test_run.commit_ref,
            test_run.report_ref,
            datetime.now(),
        )

        def _op() -> None:
            with self._client.raw_connection().cursor() as cur:
                cur.execute(sql, args)

        await self._client.run_op(_op, "record_test_run")

    async def record_change_set(self, change_set: ChangeSet) -> None:
        files = json.dumps(
            [fc.model_dump() for fc in change_set.files_changed],
            ensure_ascii=False,
        )
        sql = (
            f"INSERT INTO {CHANGESET_TABLE} "
            "(change_id,task_id,project_id,files_changed,test_run_id,"
            "base_checksum,head_checksum,ts) VALUES "
            "(%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
            "files_changed=VALUES(files_changed),test_run_id=VALUES(test_run_id),"
            "head_checksum=VALUES(head_checksum)"
        )
        args = (
            change_set.id,
            change_set.task_id,
            change_set.project_id,
            files,
            change_set.test_run_id,
            change_set.base_checksum,
            change_set.head_checksum,
            datetime.now(),
        )

        def _op() -> None:
            with self._client.raw_connection().cursor() as cur:
                cur.execute(sql, args)

        await self._client.run_op(_op, "record_change_set")

    async def list_test_runs(
        self, project_id: str, task_id: str | None = None
    ) -> list[TestRun]:
        sql = (
            f"SELECT * FROM {TESTRUN_TABLE} WHERE project_id=%s "
            + ("AND task_id=%s " if task_id else "")
            + "ORDER BY ts DESC LIMIT 100"
        )
        params = (project_id, task_id) if task_id else (project_id,)

        def _op() -> list[TestRun]:
            with self._client.raw_connection().cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
            return [
                TestRun(
                    id=r["test_run_id"],
                    project_id=r.get("project_id", ""),
                    task_id=r["task_id"],
                    command=r.get("command", ""),
                    total=r.get("total", 0),
                    passed=r.get("passed", 0),
                    failed=r.get("failed", 0),
                    skipped=r.get("skipped", 0),
                    commit_ref=r.get("commit_ref"),
                    report_ref=r.get("report_ref"),
                )
                for r in rows
            ]

        return await self._client.run_op(_op, "list_test_runs")

    async def list_change_sets(
        self, project_id: str, task_id: str | None = None
    ) -> list[ChangeSet]:
        sql = (
            f"SELECT * FROM {CHANGESET_TABLE} WHERE project_id=%s "
            + ("AND task_id=%s " if task_id else "")
            + "ORDER BY ts DESC LIMIT 100"
        )
        params = (project_id, task_id) if task_id else (project_id,)

        def _op() -> list[ChangeSet]:
            with self._client.raw_connection().cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
            result = []
            for r in rows:
                try:
                    raw_files = json.loads(r.get("files_changed") or "[]")
                    files = [FileChange(**item) for item in raw_files]
                except (json.JSONDecodeError, TypeError, ValueError):
                    files = []
                result.append(
                    ChangeSet(
                        id=r["change_id"],
                        project_id=r.get("project_id", ""),
                        task_id=r["task_id"],
                        files_changed=files,
                        test_run_id=r.get("test_run_id"),
                        base_checksum=r.get("base_checksum"),
                        head_checksum=r.get("head_checksum"),
                    )
                )
            return result

        return await self._client.run_op(_op, "list_change_sets")
