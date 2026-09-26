# OFF/ON 对比报告（docs/01 §11）

- 生成：2026-09-27 02:10:35；每臂 N=3；任务档位：hard
- 开发 Agent：Claude Code（后端 deepseek-flash，非交互 `-p --output-format stream-json`，`--dangerously-skip-permissions`，工作副本为一次性临时 git 仓库）
- ON 臂差异：同一任务提示 + SpecWeaver MCP 工具（provider=qianwen：qwen-flash 规划 + text-embedding-v4@1536 语义向量）与推荐流程提示；OFF 臂无工具、无该提示
- 判据（对 Agent 隐藏，任务结束后注入）：3 条验收测试 + 全部遗留测试必须通过 + 有实际代码变更；success = 全部满足

| 臂 | 成功率 | 中位耗时(s) | 均值耗时(s) | 最快/最慢(s) | 中位轮数 | 中位 out tokens | 均值 out tokens | 中位 sw 调用 |
|---|---|---|---|---|---|---|---|---|
| OFF | 3/3 | 82.3 | 83.5 | 68.5/99.8 | 34 | 14500 | 15224.7 | 0 |
| ON | 3/3 | 46.1 | 62.0 | 44.7/95.3 | 34 | 8185 | 10953.7 | 3 |

## 每次运行明细

- **OFF-0** success=True turns=28 sw=[] judge=21 passed in 0.04s
- **OFF-1** success=True turns=34 sw=[] judge=17 passed in 0.04s
- **OFF-2** success=True turns=37 sw=[] judge=20 passed in 0.05s
- **ON-0** success=True turns=38 sw=['sw_ingest_project', 'sw_get_context', 'sw_complete_task'] judge=20 passed in 0.03s
- **ON-1** success=True turns=34 sw=['sw_ingest_project', 'sw_get_context', 'sw_complete_task'] judge=20 passed in 0.03s
- **ON-2** success=True turns=30 sw=['sw_ingest_project', 'sw_get_context', 'sw_complete_task'] judge=19 passed in 0.03s



## 补充分析（工具调用构成，来自 transcript 实测解析）

| run | sw 调用 | Read | 探索类(Glob/Grep/PowerShell) | 编辑类(Edit/Write) |
|---|---|---|---|---|
| OFF-0 | 0 | 19 | 4 | 4 |
| OFF-1 | 0 | 20 | 10 | 3 |
| OFF-2 | 0 | 21 | 6 | 9 |
| ON-0 | 3 | 19 | 2 | 11 |
| ON-1 | 3 | 19 | 3 | 7 |
| ON-2 | 3 | 18 | 4 | 4 |

- 两臂成功率打平（3/3）：deepseek-flash 在 18 文件的小仓库上可以靠自主通读达到同等正确性；**ON 的优势体现在效率与方差**——中位耗时 46.1s vs 82.3s（-44%），均值 62.0s vs 83.5s（-26%），输出 tokens 中位 8185 vs 14500（-44%），且 OFF 臂试错型命令调用（PowerShell 探索）明显更多（4/10/6 vs 2/3/4）。
- **方差必须披露**：ON-0 用时 95.3s，劣于全部三个 OFF run；N=3 下均值与中位数背离正是这一次离群 run 造成的，结论以中位数 + 逐 run 明细为准，不宣称"必然更快"。
- ON 臂 Read 次数与 OFF 接近：这是 Context Bundle 的**渐进披露**设计使然（bundle 给代码摘要+回源引用，Agent 按引用精读），工具替代的是"盲目全仓探索"，不是精读本身。
- 推论（待更大仓库验证）：仓库规模与模块耦合度上升时，OFF 臂的探索成本近似随文件数线性增长，而 ON 臂检索+约束注入成本近似常数，差距会放大。
- easy 档对照见同目录上级 20260926-234841/（两臂同样 3/3，ON 反而慢：提示已含答案时工具是纯开销，如实记录）。



> 统计口径说明（M6-b，2026-09-27）：本次**未重跑任务**，仅把表格从单一均值改为「中位数 + 均值 + 最快/最慢」——N=3 时单个离群 run 即可主导均值（hard 档 ON-0=95.3s 劣于全部 OFF run，而 ON 中位 46.1s 优于 OFF 中位 82.3s）。逐 run 数据见明细与 summary.json，可复算。

## 局限性（如实声明）

- 单任务、小样本（N 见头部），统计意义有限，趋势参考；
- ON 臂附带推荐流程提示（工具使用引导），差异包含'工具存在+使用指引'两因素，非纯上下文增益；
- Agent 后端为 deepseek-flash（赛题不限定模型品牌）；
- 两臂同机同仓库副本顺序执行，外部网络/容器状态波动计入耗时。
