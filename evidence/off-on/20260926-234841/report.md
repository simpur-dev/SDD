# OFF/ON 对比报告（docs/01 §11）

- 生成：2026-09-27 02:11:20；每臂 N=3；任务档位：easy
- 开发 Agent：Claude Code（后端 deepseek-flash，非交互 `-p --output-format stream-json`，`--dangerously-skip-permissions`，工作副本为一次性临时 git 仓库）
- ON 臂差异：同一任务提示 + SpecWeaver MCP 工具（provider=qianwen：qwen-flash 规划 + text-embedding-v4@1536 语义向量）与推荐流程提示；OFF 臂无工具、无该提示
- 判据（对 Agent 隐藏，任务结束后注入）：3 条验收测试 + 全部遗留测试必须通过 + 有实际代码变更；success = 全部满足

| 臂 | 成功率 | 中位耗时(s) | 均值耗时(s) | 最快/最慢(s) | 中位轮数 | 中位 out tokens | 均值 out tokens | 中位 sw 调用 |
|---|---|---|---|---|---|---|---|---|
| OFF | 3/3 | 23.9 | 24.0 | 23.6/24.5 | 21 | 3988 | 3964.0 | 0 |
| ON | 3/3 | 36.1 | 35.4 | 32.6/37.5 | 27 | 5471 | 5376.3 | 3 |

## 每次运行明细

- **OFF-0** success=True turns=20 sw=[] judge=18 passed in 0.04s
- **OFF-1** success=True turns=28 sw=[] judge=18 passed in 0.05s
- **OFF-2** success=True turns=21 sw=[] judge=19 passed in 0.05s
- **ON-0** success=True turns=24 sw=['sw_ingest_project', 'sw_get_context', 'sw_complete_task'] judge=19 passed in 0.03s
- **ON-1** success=True turns=27 sw=['sw_ingest_project', 'sw_get_context', 'sw_complete_task'] judge=18 passed in 0.04s
- **ON-2** success=True turns=32 sw=['sw_ingest_project', 'sw_get_context', 'sw_complete_task'] judge=18 passed in 0.03s



> 统计口径说明（M6-b，2026-09-27）：本次**未重跑任务**，仅把表格从单一均值改为「中位数 + 均值 + 最快/最慢」——N=3 时单个离群 run 即可主导均值（hard 档 ON-0=95.3s 劣于全部 OFF run，而 ON 中位 46.1s 优于 OFF 中位 82.3s）。逐 run 数据见明细与 summary.json，可复算。

## 局限性（如实声明）


- 单任务、小样本（N 见头部），统计意义有限，趋势参考；
- ON 臂附带推荐流程提示（工具使用引导），差异包含'工具存在+使用指引'两因素，非纯上下文增益；
- Agent 后端为 deepseek-flash（赛题不限定模型品牌）；
- 两臂同机同仓库副本顺序执行，外部网络/容器状态波动计入耗时。
