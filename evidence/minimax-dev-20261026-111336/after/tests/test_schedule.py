"""时刻计算回归测试（REQ-1）。"""

from schedule import Train, arrival_times, to_hhmm, to_minutes


def make_train() -> Train:
    return Train(
        train_id="K1",
        start="08:00",
        legs={"A->B": 10, "B->C": 15},
    )


def test_stop_order() -> None:
    assert make_train().stops() == ["A", "B", "C"]


def test_arrival_times_accumulate() -> None:
    assert arrival_times(make_train()) == {
        "A": "08:00",
        "B": "08:10",
        "C": "08:25",
    }


def test_minute_helpers_roundtrip() -> None:
    assert to_minutes("09:30") == 570
    assert to_hhmm(570) == "09:30"
