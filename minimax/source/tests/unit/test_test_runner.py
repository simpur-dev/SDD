"""SubprocessTestRunner: summary parsing and junit reconciliation.

The completion red line ("tests really ran, and the recorded counts agree with
the report") lives in this adapter, and it also owns the docs/03 §7.1 promise
that a broken report surfaces as SWError rather than a raw OSError.
"""
from __future__ import annotations

import sys

import pytest

from specweaver.adapters.driven.workspace.git import SubprocessTestRunner
from specweaver.shared.config import WorkspaceSettings
from specweaver.shared.errors import SWError

JUNIT_OK = """<testsuite tests="4">
  <testcase classname="a" name="one"/>
  <testcase classname="a" name="two"/>
  <testcase classname="a" name="three"><failure message="boom"/></testcase>
  <testcase classname="a" name="four"><skipped/></testcase>
</testsuite>
"""


def _runner(tmp_path) -> SubprocessTestRunner:
    return SubprocessTestRunner(WorkspaceSettings(root=str(tmp_path)))


async def test_run_reports_passing_counts(tmp_path) -> None:
    runner = _runner(tmp_path)

    run = await runner.run(
        f'"{sys.executable}" -c "print(\'3 passed in 0.42s\')"'
    )

    assert (run.total, run.passed, run.failed) == (3, 3, 0)


async def test_run_counts_a_failing_exit_without_summary(tmp_path) -> None:
    runner = _runner(tmp_path)
    run = await runner.run(
        f'"{sys.executable}" -c "import sys; sys.exit(2)"'
    )
    # the completion red line: a non-zero exit with no parseable summary is
    # recorded as one failure, never as an empty "all green" run
    assert run.total == 1
    assert run.failed == 1
    assert run.passed == 0


async def test_parse_report_reads_a_valid_junit(tmp_path) -> None:
    report = tmp_path / "junit.xml"
    report.write_text(JUNIT_OK, encoding="utf-8")

    run = await _runner(tmp_path).parse_report("junit.xml")

    assert (run.total, run.passed, run.failed, run.skipped) == (4, 2, 1, 1)
    assert run.report_ref.endswith("junit.xml")


async def test_parse_report_of_missing_file_is_swerror(tmp_path) -> None:
    with pytest.raises(SWError) as excinfo:
        await _runner(tmp_path).parse_report("nope.xml")
    assert "unreadable" in excinfo.value.message


async def test_parse_report_of_malformed_xml_is_swerror(tmp_path) -> None:
    (tmp_path / "broken.xml").write_text("<testsuite", encoding="utf-8")
    with pytest.raises(SWError) as excinfo:
        await _runner(tmp_path).parse_report("broken.xml")
    assert "not valid XML" in excinfo.value.message
