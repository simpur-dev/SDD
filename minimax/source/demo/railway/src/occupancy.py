"""车辆占用检查：对照车辆其他任务检查时间窗冲突。

需求依据见 REQ-2。
"""

from dataclasses import dataclass


@dataclass
class Occupation:
    """一段车辆占用：车号 + 起止分钟。"""

    train_id: str
    start_min: int
    end_min: int


def conflicts(left: Occupation, right: Occupation) -> bool:
    """同一车辆的两段占用时间窗是否重叠。"""
    if left.train_id != right.train_id:
        return False
    return left.start_min < right.end_min and right.start_min < left.end_min


def has_conflicts(items: list[Occupation]) -> bool:
    for index, left in enumerate(items):
        for right in items[index + 1:]:
            if conflicts(left, right):
                return True
    return False
