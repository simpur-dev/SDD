"""占用检查回归测试（REQ-2）。"""

from occupancy import Occupation, conflicts, has_conflicts


def test_same_train_overlap_conflicts() -> None:
    a = Occupation("K1", 480, 500)
    b = Occupation("K1", 495, 520)
    assert conflicts(a, b)


def test_different_trains_never_conflict() -> None:
    a = Occupation("K1", 480, 500)
    b = Occupation("K2", 495, 520)
    assert not conflicts(a, b)


def test_adjacent_windows_do_not_conflict() -> None:
    a = Occupation("K1", 480, 500)
    b = Occupation("K1", 500, 520)
    assert not has_conflicts([a, b])
