"""入口冒烟测试（REQ-4）。"""

from api import show_timetable, submit_publish
from schedule import Train


def make_train() -> Train:
    return Train(train_id="K1", start="08:00", legs={"A->B": 10, "B->C": 15})


def test_show_timetable() -> None:
    assert show_timetable(make_train())["C"] == "08:25"


def test_submit_publish_passes_through() -> None:
    ok, _ = submit_publish(make_train(), [])
    assert ok
