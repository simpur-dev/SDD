"""Reconciliation/test-summary parsing boundaries (git.py _parse_summary)."""
from __future__ import annotations

from specweaver.adapters.driven.workspace.git import _parse_summary


def test_counts_pass_fail_skip_error() -> None:
    total, passed, failed, skipped = _parse_summary(
        "= 5 passed, 2 failed, 1 error, 3 skipped =", 1
    )
    assert (passed, failed, skipped) == (5, 3, 3)  # errors fold into failed
    assert total == passed + failed + skipped


def test_no_counts_zero_returncode_is_vacuous_pass() -> None:
    """Audit B-12 (documented current behaviour): a command that exits 0
    without running any tests counts as success=True with total=0, which
    lets CompleteTask reconcile on a vacuously green run."""
    total, passed, failed, skipped = _parse_summary("ok\n", 0)
    assert (total, passed, failed, skipped) == (0, 0, 0, 0)


def test_no_counts_nonzero_returncode_is_one_failure() -> None:
    total, passed, failed, skipped = _parse_summary("boom", 4)
    assert (total, failed) == (1, 1)


def test_plural_and_singular_forms() -> None:
    assert _parse_summary("1 passed in 0.10s", 0)[1] == 1
    assert _parse_summary("1 failed in 0.10s", 1)[2] == 1
