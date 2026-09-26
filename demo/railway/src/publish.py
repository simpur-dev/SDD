"""发布判断：检测到冲突则阻止发布（受 RULE-3 约束）。

需求依据见 REQ-3。
"""

from occupancy import Occupation, has_conflicts
from schedule import Train, arrival_times, to_minutes


def windows_for(train: Train) -> list[Occupation]:
    """按停站时刻近似为占用区间（教学模型：站间即为占用）。"""
    stops = train.stops()
    times = arrival_times(train)
    return [
        Occupation(
            train_id=train.train_id,
            start_min=to_minutes(times[stops[index]]),
            end_min=to_minutes(times[stops[index + 1]]),
        )
        for index in range(len(stops) - 1)
    ]


def can_publish(
    train: Train, fleet: list[Occupation]
) -> tuple[bool, str]:
    """本车占用与车队既有占用冲突则禁止发布。"""
    mine = windows_for(train)
    if has_conflicts([*mine, *fleet]):
        return False, "occupied: 存在车辆占用冲突，禁止发布"
    return True, "publish ok"
