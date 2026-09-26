# OFF/ON 对比报告（docs/01 §11）

- 生成：2026-09-26 23:51:46；每臂 N=3
- 开发 Agent：Claude Code（后端 deepseek-flash，非交互 `-p --output-format stream-json`，`--dangerously-skip-permissions`，工作副本为一次性临时 git 仓库）
- ON 臂差异：同一任务提示 + SpecWeaver MCP 工具（provider=qianwen：qwen-flash 规划 + text-embedding-v4@1536 语义向量）与推荐流程提示；OFF 臂无工具、无该提示
- 判据（对 Agent 隐藏，任务结束后注入）：3 条验收测试 + 全部遗留测试必须通过 + 有实际代码变更；success = 全部满足

| 臂 | 成功率 | 平均耗时(s) | 平均轮数 | 平均 in/out tokens | 平均 sw 调用 |
|---|---|---|---|---|---|
| OFF | 3/3 | 24.0 | 23.0 | 20697.0/3964.0 | 0.0 |
| ON | 3/3 | 35.4 | 27.7 | 23403.0/5376.3 | 3.0 |

## 每次运行明细

- **OFF-0** success=True turns=20 sw=[] judge=18 passed in 0.04s
- **OFF-1** success=True turns=28 sw=[] judge=18 passed in 0.05s
- **OFF-2** success=True turns=21 sw=[] judge=19 passed in 0.05s
- **ON-0** success=True turns=24 sw=['sw_ingest_project', 'sw_get_context', 'sw_complete_task'] judge=19 passed in 0.03s
- **ON-1** success=True turns=27 sw=['sw_ingest_project', 'sw_get_context', 'sw_complete_task'] judge=18 passed in 0.04s
- **ON-2** success=True turns=32 sw=['sw_ingest_project', 'sw_get_context', 'sw_complete_task'] judge=18 passed in 0.03s

## 局限性（如实声明）

- 单任务、小样本（N 见头部），统计意义有限，趋势参考；
- ON 臂附带推荐流程提示（工具使用引导），差异包含'工具存在+使用指引'两因素，非纯上下文增益；
- Agent 后端为 deepseek-flash（赛题不限定模型品牌）；
- 两臂同机同仓库副本顺序执行，外部网络/容器状态波动计入耗时。
