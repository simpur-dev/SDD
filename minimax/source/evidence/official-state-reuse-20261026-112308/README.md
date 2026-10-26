# 状态保存 → 模块重启 → 读取并复用（正式题面必做项 5）

- 生成：2026-10-26 11:23:39（Asia/Shanghai）
- 工程：demo/railway 临时工作副本
- project_id：$stateProject（全新 id ⇒ PowerContext scope 从空状态创建）
- 推理：规则模式（INFERENCE__PROVIDER=none），聚焦状态持久化/复用本身

## 两次进程（模块重启语义）

每次 python -m specweaver.adapters.driving.cli.app ... 都是新的 OS 进程；PowerContext 运行在独立 server 中：

| 进程 | 命令 | 结果 |
|---|---|---|
| A1 | ingest official-state-20261026-112308 | 摄入 18 个构件（a1-ingest.json） |
| A2 | handoff official-state-20261026-112308 --objective ... --state ... --next-step ... | 保存任务状态，返回 handoff_rev=handoff:handoff:1（a2-handoff.json） |
| **进程 A 结束** | — | — |
| B1 | esume official-state-20261026-112308 --handoff-rev handoff:handoff:1（新进程） | handoff_resumed=true、objective/progress/next_steps 全部恢复、mismatches=0（b1-resume.json） |
| B2 | context official-state-20261026-112308 "实现 adjust_departure 并补回归测试"（再一个新进程） | 组装 Bundle 6363 B、18 citations、findings 6（b2-context.json） |

## 关键字段（b1-resume.json）

- objective: 按站调整发车时间并重算后续各站
- progress: 已读取有效规格 REQ-1/RULE-1；已确认时刻计算实现位于 src/schedule.py
- 
ext_steps: ["实现 adjust_departure 并补回归测试"]
- handoff_resumed: true；mismatches: 0；context：重启后重建的 Bundle（含 18 条 citations）

## 文件

- 1-ingest.json、2-handoff.json、1-resume.json、2-context.json
- handoff-rev.txt、*-usage.csv（各进程用量；b1 含 resume_task span）
- 本 README

> 说明：正式题面只要求“模块重启后能够读取并使用保存的状态”，不要求恢复完整 Agent 会话；本样例用新进程验证了保存/读取/重建上下文全链路。