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

### 按站调整发车时间（升版：含审计）  [REQ-6 v2.0.0 · specs/requirement-schedule-v2.md]
---
id: REQ-06
type: requirement
module: schedule
version: 2.0.0
status: active
supersedes: REQ-01
title: 按站调整发车时间（升版：含审计）
---

# 按站调整发车时间（升版）

本需求为 REQ-1 的升版：

- 调度员应能按站点修改发车时间并自动重算后续各站时刻
- 每次调整必须记录审计日志

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
def submit_adjust_departure(
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
def adjust_departure(train: Train, new_start: str) -> Train:
def adjust_departure_logged(train: Train, new_start: str) -> Train:
(full source: see the citation uri)

## ③ Verification method and results
### test_adjust  [TST-885ea3f0b041 v0.1.0 · tests/test_adjust.py]
def make_train() -> Train:
def test_adjust_departure_shifts_whole_timetable() -> None:
(full source: see the citation uri)

### test_audit  [TST-bf4598def6a1 v0.1.0 · tests/test_audit.py]
def make_train() -> Train:
def test_audit_log_records_adjustment() -> None:
def test_adjusted_train_still_checked_for_occupancy() -> None:
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
- last test run [PASS] task=railway-20260926-211737-audit: 13/13 passed, 0 failed, 0 skipped, ref=d56014c5aba36db18b8f7b28f591bf66b18a6f74, cmd="E:\2026ob_projects\SDD\.venv\Scripts\python.exe" -m pytest -q

## ④ Task status and sources
- task id: task-762d505ec6
- phase: analyzing
- base ref: d56014c5aba36db18b8f7b28f591bf66b18a6f74
- sources cited: RULE-3, RULE-2, RULE-1, REQ-4, REQ-5, REQ-2, REQ-3, REQ-6, DES-2, DES-1, CODE-e662196c212e, CODE-4bfabc68a8f6, CODE-12d4b7620710, CODE-2335993c1bbc, TST-885ea3f0b041, TST-bf4598def6a1, TST-da7154c71d35, TST-d4cf3c71d337, TST-e9c84656fadf

## ⑤ Findings (conflicts · gaps · confirmations)
- (warning/gap) Requirement '调度操作入口' has no design layer
    suggestion: Add a design realizing this requirement.
    sources: REQ-4
- (warning/gap) Requirement '发布前预览接口' has no design layer
    suggestion: Add a design realizing this requirement.
    sources: REQ-5
- (warning/gap) Requirement '发布前预览接口' has no code layer
    suggestion: Add an implementation of this requirement.
    sources: REQ-5
- (warning/gap) Requirement '发布前预览接口' has no test layer
    suggestion: Add tests covering the implementation.
    sources: REQ-5
- (warning/gap) Requirement '车辆占用检查' has no design layer
    suggestion: Add a design realizing this requirement.
    sources: REQ-2
- (warning/suspect) '按站调整发车时间（升版：含审计）' is based on REQ-1, whose status is superseded
    suggestion: Review and update this downstream artifact against the current upstream version.
    sources: REQ-6, REQ-1
- (warning/suspect) '时刻计算设计' is based on REQ-1, whose status is superseded
    suggestion: Review and update this downstream artifact against the current upstream version.
    sources: DES-1, REQ-1
- (warning/suspect) 'schedule' is based on REQ-1, whose status is superseded
    suggestion: Review and update this downstream artifact against the current upstream version.
    sources: CODE-2335993c1bbc, REQ-1
- (warning/suspect) 'test_adjust' is based on REQ-1, whose status is superseded
    suggestion: Review and update this downstream artifact against the current upstream version.
    sources: TST-885ea3f0b041, REQ-1
- (warning/suspect) 'test_schedule' is based on REQ-1, whose status is superseded
    suggestion: Review and update this downstream artifact against the current upstream version.
    sources: TST-e9c84656fadf, REQ-1

## ⑥ Budget and usage
- context size: 7741/8000 bytes
- generated at: 2026-09-26 21:17:53.712753