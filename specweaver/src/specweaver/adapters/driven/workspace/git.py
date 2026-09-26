from __future__ import annotations

import asyncio
import hashlib
import re
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from ....domain.entities import FileChange, TestRun
from ....shared.config import WorkspaceSettings
from ....shared.errors import SWError

_GIT_TIMEOUT = 30.0
_RUN_TIMEOUT = 600.0

_STATUS_MAP = {"A": "added", "M": "modified", "D": "deleted", "R": "added"}


class GitWorkspace:
    def __init__(self, settings: WorkspaceSettings) -> None:
        self._settings = settings
        self.root = Path(settings.root).resolve()

    async def _git(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-c",
            "core.quotepath=off",
            *args,
            cwd=self.root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(
                proc.communicate(), _GIT_TIMEOUT
            )
        except TimeoutError as exc:
            proc.kill()
            raise SWError(f"git {' '.join(args)} timed out") from exc
        if proc.returncode != 0:
            raise SWError(
                f"git {' '.join(args)} failed: "
                f"{err.decode(errors='ignore')[:200]}"
            )
        return out.decode(errors="ignore").strip()

    async def list_files(self) -> list[str]:
        tracked = await self._git("ls-files")
        others = await self._git(
            "ls-files", "--others", "--exclude-standard"
        )
        files = set(tracked.splitlines())
        if others:
            files.update(others.splitlines())
        return sorted(files)

    async def current_ref(self) -> str:
        return await self._git("rev-parse", "HEAD")

    async def changed_files(
        self, base: str, head: str
    ) -> list[FileChange]:
        # --relative keeps paths consistent with list_files/read_file,
        # which are workspace-root relative (git repo may be a parent).
        text = await self._git(
            "diff", "--name-status", "--relative", base, head
        )
        changes: list[FileChange] = []
        for line in text.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            code = parts[0][0]
            changes.append(
                FileChange(
                    path=parts[-1],
                    change_type=_STATUS_MAP.get(code, "modified"),
                )
            )
        return changes

    def _abs(self, path: str) -> Path:
        return (self.root / path).resolve()

    async def read_file(self, path: str) -> str:
        return self._abs(path).read_text(
            encoding="utf-8", errors="replace"
        )

    async def exists(self, path: str) -> bool:
        return self._abs(path).exists()

    async def checksum(self, path: str) -> str:
        h = hashlib.sha256()
        with self._abs(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                h.update(chunk)
        return "sha256:" + h.hexdigest()


def _parse_summary(text: str, returncode: int):
    def find(pattern):
        match = re.search(pattern, text)
        return int(match.group(1)) if match else 0

    passed = find(r"(\d+) passed")
    failed = find(r"(\d+) failed")
    skipped = find(r"(\d+) skipped")
    errors = find(r"(\d+) error")
    failed += errors
    total = passed + failed + skipped
    if total == 0 and returncode != 0:
        return 1, 0, 1, 0
    return total, passed, failed, skipped


def _parse_junit(path: Path) -> TestRun:
    root = ET.parse(path).getroot()
    total = passed = failed = skipped = 0
    for case in root.iter("testcase"):
        total += 1
        if case.find("failure") is not None or case.find("error") is not None:
            failed += 1
        elif case.find("skipped") is not None:
            skipped += 1
        else:
            passed += 1
    return TestRun(
        id=f"tr-report-{uuid.uuid4().hex[:8]}",
        task_id="",
        report_ref=str(path),
        total=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
    )


class SubprocessTestRunner:
    def __init__(self, settings: WorkspaceSettings) -> None:
        self.root = Path(settings.root).resolve()

    async def run(self, command: str) -> TestRun:
        start = time.time()
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=self.root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(
                proc.communicate(), _RUN_TIMEOUT
            )
        except TimeoutError:
            proc.kill()
            return TestRun(
                id=f"tr-{int(start * 1000)}-{uuid.uuid4().hex[:6]}",
                task_id="",
                command=command,
                failed=1,
                total=1,
            )
        text = out.decode(errors="ignore") + "\n" + err.decode(
            errors="ignore"
        )
        total, passed, failed, skipped = _parse_summary(
            text, proc.returncode
        )
        return TestRun(
            id=f"tr-{int(start * 1000)}-{uuid.uuid4().hex[:6]}",
            task_id="",
            command=command,
            total=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
        )

    async def parse_report(self, uri: str) -> TestRun:
        path = Path(uri)
        if not path.is_absolute():
            path = self.root / path
        return _parse_junit(path)
