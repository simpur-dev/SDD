"""按站调整发车时间的回归测试（REQ-1、REQ-4、REQ-3、RULE-3）。"""

import pytest

from api import submit_adjust_departure
from occupancy import Occupation
from publish import can_publish
from schedule import Train, adjust_departure, arrival_times


def make_train() -> Train:
    return Train(
        train_id="K1",
        start="08:00",
        legs={"A->B": 10, "B->C": 15},
    )


def test_adjust_departure_shifts_whole_timetable() -> None:
    adjusted = adjust_departure(make_train(), "09:00")
    assert adjusted.start == "09:00"
    assert adjusted.legs == {"A->B": 10, "B->C": 15}
    assert arrival_times(adjusted) == {
        "A": "09:00",
        "B": "09:10",
        "C": "09:25",
    }


def test_adjust_departure_returns_new_train_and_keeps_original() -> None:
    original = make_train()
    adjusted = adjust_departure(original, "07:30")
    assert adjusted is not original
    assert original.start == "08:00"
    assert arrival_times(original)["C"] == "08:25"
    assert adjusted.legs is not original.legs


def test_adjust_departure_rejects_invalid_time() -> None:
    with pytest.raises(ValueError):
        adjust_departure(make_train(), "not-a-time")


def test_submit_adjust_departure_returns_adjusted_times() -> None:
    assert submit_adjust_departure(make_train(), "09:00") == {
        "A": "09:00",
        "B": "09:10",
        "C": "09:25",
    }


def test_adjusted_train_still_blocked_when_occupied() -> None:
    """调整后与既有车辆占用窗口冲突的，仍然禁止发布（RULE-3）。"""
    train = make_train()
    busy = [Occupation("K1", 545, 555)]  # 09:05 - 09:15，与调整后的 A->B 重叠
    assert can_publish(train, busy)[0] is True

    adjusted = adjust_departure(train, "09:00")
    ok, reason = can_publish(adjusted, busy)
    assert not ok
    assert "禁止发布" in reason


def test_adjusted_train_publish_allowed_without_conflict() -> None:
    adjusted = adjust_departure(make_train(), "09:00")
    ok, reason = can_publish(adjusted, [])
    assert ok, reason
