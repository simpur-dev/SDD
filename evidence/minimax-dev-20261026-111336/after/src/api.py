"""页面/接口：选择目标站点、提交新车发时间（功能入口）。

需求依据见 REQ-4。
"""

from publish import can_publish
from schedule import Train, adjust_departure, arrival_times


def show_timetable(train: Train) -> dict[str, str]:
    """展示各站时刻。"""
    return arrival_times(train)


def submit_adjust_departure(train: Train, new_start: str) -> dict[str, str]:
    """提交新的发车时间：返回调整后各站时刻（依据 REQ-1、REQ-4）。"""
    return arrival_times(adjust_departure(train, new_start))


def submit_publish(train: Train, fleet: list) -> tuple[bool, str]:
    """提交发布：先经占用与发布判断。"""
    return can_publish(train, fleet)
