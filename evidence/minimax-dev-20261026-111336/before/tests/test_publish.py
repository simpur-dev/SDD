"""发布判断回归测试（REQ-3、RULE-3）。"""

from occupancy import Occupation
from publish import can_publish
from schedule import Train


def make_train() -> Train:
    return Train(train_id="K1", start="08:00", legs={"A->B": 10, "B->C": 15})


def test_publish_allowed_without_conflict() -> None:
    ok, reason = can_publish(make_train(), [])
    assert ok, reason


def test_publish_blocked_by_conflict() -> None:
    busy = [Occupation("K1", 485, 495)]
    ok, reason = can_publish(make_train(), busy)
    assert not ok
    assert "禁止发布" in reason
