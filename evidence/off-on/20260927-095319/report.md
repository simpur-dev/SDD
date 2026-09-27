# OFF/ON 对比报告（docs/01 §11）

- 生成：2026-09-27 09:54:57；每臂 N=1；任务档位：hard · hint=full
- 开发 Agent：Claude Code（后端 deepseek-flash，非交互 `-p --output-format stream-json`，`--dangerously-skip-permissions`，工作副本为一次性临时 git 仓库）
- ON 臂差异：同一任务提示 + SpecWeaver MCP 工具（provider=qianwen：qwen-flash 规划 + text-embedding-v4@1536 语义向量）与推荐流程提示；OFF 臂无工具、无该提示
- 判据（对 Agent 隐藏，任务结束后注入）：3 条验收测试 + 全部遗留测试必须通过 + 有实际代码变更；success = 全部满足

| 臂 | 成功率 | 中位耗时(s) | 均值耗时(s) | 最快/最慢(s) | 中位轮数 | 中位 out tokens | 均值 out tokens | 中位 sw 调用 |
|---|---|---|---|---|---|---|---|---|
| ON | 1/1 | 96.6 | 96.6 | 96.6/96.6 | 43 | 8142 | 8142.0 | 11 |

## 每次运行明细

- **ON-0** success=True turns=43 sw=['sw_ping', 'sw_doctor', 'sw_ingest_project', 'sw_get_context', 'sw_record_decision', 'sw_handoff', 'sw_resume_task', 'sw_report_progress', 'sw_verify', 'sw_explain_source', 'sw_complete_task'] judge=17 passed in 0.05s

## 局限性（如实声明）

- 单任务、小样本（N 见头部），统计意义有限，趋势参考；
- ON 臂附带推荐流程提示（工具使用引导），差异包含'工具存在+使用指引'两因素，非纯上下文增益；
- Agent 后端为 deepseek-flash（赛题不限定模型品牌）；
- 两臂同机同仓库副本顺序执行，外部网络/容器状态波动计入耗时。
