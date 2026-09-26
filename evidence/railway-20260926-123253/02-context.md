# Context: 为列车按站调整发车时间并重算后续各站时刻，检查占用冲突并阻止发布

## ① Current goal and effective constraints
### 冲突禁发  [RULE-3 v1.0.0 · rules/publish-rule.md]
---
id: RULE-03
type: rule
module: publish
version: 1.0.0
status: active
title: 冲突禁发
---

# 冲突禁发

- 检测到占用冲突时禁止发布

### 全量回归  [RULE-2 v1.0.0 · rules/regression-rule.md]
---
id: RULE-02
type: rule
version: 1.0.0
status: active
title: 全量回归
---

# 全量回归

- 任何时刻表变更必须通过全量回归测试

### 最小站间隔（现行规章）  [RULE-1 v1.0.0 · rules/interval-rule.md]
---
id: RULE-01
type: rule
module: schedule
version: 1.0.0
status: active
title: 最小站间隔（现行规章）
---

# 最小站间隔

- 相邻站间隔不得低于 3 分钟

### 调度操作入口  [REQ-4 v1.0.0 · specs/requirement-api.md]
---
id: REQ-04
type: requirement
module: api
version: 1.0.0
status: active
title: 调度操作入口
---

# 调度操作入口

- 页面提供选择目标站点与提交新车发时间的入口

### 发布前预览接口  [REQ-5 v1.0.0 · specs/requirement-dryrun.md]
---
id: REQ-05
type: requirement
module: dryrun
version: 1.0.0
status: active
title: 发布前预览接口
---

# 发布前预览接口

- 应提供发布前预览能力，返回将要变更的时刻表差异

### 车辆占用检查  [REQ-2 v1.0.0 · specs/requirement-occupancy.md]
---
id: REQ-02
type: requirement
module: occupancy
version: 1.0.0
status: active
title: 车辆占用检查
---

# 车辆占用检查

- 调整时刻后必须对照该车辆当日其他任务检查时间窗冲突

### 发布判断  [REQ-3 v1.0.0 · specs/requirement-publish.md]
---
id: REQ-03
type: requirement
module: publish
version: 1.0.0
status: active
title: 发布判断
---

# 发布判断

- 发布前必须复核车辆占用，存在冲突时阻止发布

### 按站调整发车时间  [REQ-1 v1.0.0 · specs/requirement-schedule.md]
---
id: REQ-01
type: requirement
module: schedule
version: 1.0.0
status: active
title: 按站调整发车时间
---

# 按站调整发车时间

- 调度员应能按站点修改发车时间并自动重算后续各站时刻
- 相邻站间隔不得低于 5 分钟

## ② Related design and implementation
### 发布链路设计  [DES-2 v1.0.0 · design/publish-design.md]
---
id: DES-02
type: design
module: publish
version: 1.0.0
status: active
title: 发布链路设计
---

# 发布链路设计

publish 模块把停站时刻折算为占用时间窗，交由 occupancy 复核，
覆盖 REQ-3 并遵守 RULE-3 的禁止发布约束。

### 时刻计算设计  [DES-1 v1.0.0 · design/schedule-design.md]
---
id: DES-01
type: design
module: schedule
version: 1.0.0
status: active
title: 时刻计算设计
---

# 时刻计算设计

schedule 模块以"始发时刻 + 站间运行时分"推导各站时刻，实现 REQ-1。
调整发车时间时平移始发时刻即可重算后续各站。

### api  [CODE-e662196c212e v0.1.0 · src/api.py]
def show_timetable(train: Train) -> dict[str, str]:
def submit_publish(train: Train, fleet: list) -> tuple[bool, str]:
(full source: see the citation uri)

### occupancy  [CODE-4bfabc68a8f6 v0.1.0 · src/occupancy.py]
class Occupation:
def conflicts(left: Occupation, right: Occupation) -> bool:
def has_conflicts(items: list[Occupation]) -> bool:
(full source: see the citation uri)

### publish  [CODE-12d4b7620710 v0.1.0 · src/publish.py]
def windows_for(train: Train) -> list[Occupation]:
def can_publish(
(full source: see the citation uri)

### schedule  [CODE-2335993c1bbc v0.1.0 · src/schedule.py]
def to_minutes(hhmm: str) -> int:
def to_hhmm(total: int) -> str:
class Train:
def stops(self) -> list[str]:
def arrival_times(train: Train) -> dict[str, str]:
(full source: see the citation uri)

## ③ Verification method and results
### test_api  [TST-46ecef6a906e v0.1.0 · tests/test_api.py]
def make_train() -> Train:
def test_show_timetable() -> None:
def test_submit_publish_passes_through() -> None:
(full source: see the citation uri)

### test_occupancy  [TST-da7154c71d35 v0.1.0 · tests/test_occupancy.py]
def test_same_train_overlap_conflicts() -> None:
def test_different_trains_never_conflict() -> None:
def test_adjacent_windows_do_not_conflict() -> None:
(full source: see the citation uri)

### test_publish  [TST-d4cf3c71d337 v0.1.0 · tests/test_publish.py]
def make_train() -> Train:
def test_publish_allowed_without_conflict() -> None:
def test_publish_blocked_by_conflict() -> None:
(full source: see the citation uri)

### test_schedule  [TST-e9c84656fadf v0.1.0 · tests/test_schedule.py]
def make_train() -> Train:
def test_stop_order() -> None:
def test_arrival_times_accumulate() -> None:
def test_minute_helpers_roundtrip() -> None:
(full source: see the citation uri)

## ④ Task status and sources
- task id: task-db730d8a4e
- phase: analyzing
- base ref: 3c9f526ee92c7cb7fc34aa2aba6618d50150ea58
- sources cited: RULE-3, RULE-2, RULE-1, REQ-4, REQ-5, REQ-2, REQ-3, REQ-1, DES-2, DES-1, CODE-e662196c212e, CODE-4bfabc68a8f6, CODE-12d4b7620710, CODE-2335993c1bbc, TST-46ecef6a906e, TST-da7154c71d35, TST-d4cf3c71d337, TST-e9c84656fadf

## ⑤ Findings (conflicts · gaps · confirmations)
- (warning/conflict) [needs confirmation] Conflicting constraints in module 'schedule': 相邻站间隔不得低于 5 分钟
    suggestion: Confirm the authoritative constraint before editing this area.
    sources: REQ-1, RULE-1
- (warning/gap) Requirement '车辆占用检查' has no design layer
    suggestion: Add a design realizing this requirement.
    sources: REQ-2
- (warning/gap) Requirement '发布前预览接口' has no design layer
    suggestion: Add a design realizing this requirement.
    sources: REQ-5
- (warning/gap) Requirement '发布前预览接口' has no code layer
    suggestion: Add an implementation of this requirement.
    sources: REQ-5
- (warning/gap) Requirement '发布前预览接口' has no test layer
    suggestion: Add tests covering the implementation.
    sources: REQ-5
- (warning/gap) Requirement '调度操作入口' has no design layer
    suggestion: Add a design realizing this requirement.
    sources: REQ-4

## ⑥ Budget and usage
- context size: 6178/8000 bytes
- generated at: 2026-09-26 12:32:58.478115