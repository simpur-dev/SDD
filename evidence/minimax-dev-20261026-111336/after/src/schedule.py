"""时刻计算：更新当前站发车时间、重算后续各站时间。

需求依据见 REQ-1。
"""

from dataclasses import dataclass, field


def to_minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def to_hhmm(total: int) -> str:
    return f"{total // 60 % 24:02d}:{total % 60:02d}"


@dataclass
class Train:
    """一趟车：始发时刻 + 各站间运行时分（"A->B" -> 分钟）。"""

    train_id: str
    start: str
    legs: dict[str, int] = field(default_factory=dict)

    def stops(self) -> list[str]:
        """按 leg 顺序推导站序：首站 + 各 leg 的终点。"""
        stops: list[str] = []
        for leg in self.legs:
            origin, _, destination = leg.partition("->")
            if not stops:
                stops.append(origin)
            stops.append(destination)
        return stops


def adjust_departure(train: Train, new_start: str) -> Train:
    """调整发车时间：返回新车发时刻的列车，站间运行时分保持不变。

    站间运行时分不变意味着整张时刻表整体平移，后续各站时刻随之重算
    （依据 REQ-1 与 DES-01）。
    """
    to_minutes(new_start)  # 校验时刻格式，非法输入直接报错
    return Train(
        train_id=train.train_id,
        start=new_start,
        legs=dict(train.legs),
    )


def arrival_times(train: Train) -> dict[str, str]:
    """各站时刻 = 始发时刻 + 累计运行时分。"""
    stops = train.stops()
    clock = to_minutes(train.start)
    times = {stops[0]: to_hhmm(clock)}
    for index, minutes in enumerate(train.legs.values()):
        clock += minutes
        times[stops[index + 1]] = to_hhmm(clock)
    return times
