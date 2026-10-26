# 规格更新后重新导入 → 上下文使用新内容（正式题面必做项 3）

- 生成：2026-10-26 11:23:39（Asia/Shanghai）
- 工程：demo/railway 临时工作副本（git baseline + 规格变更 commit）
- 模块：SpecWeaver（ingest 增量摄入 + context 组装）
- 推理：INFERENCE__PROVIDER=none（规则模式，不依赖外部模型；功能链路不变）

## 步骤与结果

| 步骤 | 命令 | 结果 |
|---|---|---|
| 1. 基线规格 | specs/requirement-schedule.md v1.0.0，含“相邻站间隔不得低于 **5 分钟**” | — |
| 2. 摄入 + 取上下文（改前） | ingest official-spec-20261026-112242 / context official-spec-20261026-112242 "为列车按站调整发车时间..." | REQ-1 v1.0.0，内容含 5 分钟 |
| 3. 更新规格并提交 | 版本 1.0.0→1.1.0；约束 5→**7 分钟**；git 546931c | 同一工程 |
| 4. 增量重导入 | ingest official-spec-20261026-112242（同 project_id） | 增量更新 |
| 5. 重新取上下文（改后） | context official-spec-20261026-112242 "<同一任务>" | REQ-1 **v1.1.0**，内容含 7 分钟、不含 5 分钟 |

## 机器校验（verification.txt）

`
BEFORE: REQ-1 present: True | version: 1.0.0 | content has 5min: True | content has 7min: False | citation versions: ['1.0.0']
AFTER:  REQ-1 present: True | version: 1.1.0 | content has 5min: False | content has 7min: True | citation versions: ['1.1.0']
CHECKS {"before_has_5min": true, "after_has_7min": true, "after_version_1_1_0": true, "after_not_stale_5min": true}
RESULT PASS

`

## 文件

- ingest-before.json / ingest-after.json：两次摄入报告
- context-before.json / context-after.json：改前/改后上下文 Bundle
- *-usage.csv：用量（摄入/组装后端调用）
- erification.txt：脚本断言结果（4 项全 PASS）

> 说明：本样例验证的是“规格更新 → 重新导入 → 上下文使用更新内容”（正式题面 §2.3 / §4.1 必做项 3）；工作副本为临时目录，可从 demo/railway 按本 README 复现。