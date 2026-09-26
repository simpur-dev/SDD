# 检索质量金标评测（docs/01 §11 / docs/03 §11）

- 生成：20260927-020817；语料：demo/railway @ v1.1.0 (20 artifacts: 5 REQ / 3 RULE / 2 DES / 4 code / 4 test)
- 标注方法：金标由本项目人工标注，口径对齐 ContextBench 的 minimal-context 原则：以『完成该任务所需的最小充分依据』为准，逐条给出推导链（derivation），并可由 demo/railway 的 front matter 与关系图复核。标注者不是模型，且标注在评测前冻结。
- 两臂**同字节公平**：keyword 臂拿到的预算 = SpecWeaver 在该用例实际花在**构件**上的字节（chrome/findings 不计入），并用同一 `entry_block` 成本模型填充、只保留有命中的文档；因此 recall/precision 差异反映的是选择质量而非预算差异
- 推理 provider：`qianwen`（规则模式下 planner 不产生 LLM 调用，混合检索仍走真实 seekdb）

## 宏平均

| 臂 | recall | precision | F1 |
|---|---|---|---|
| keyword | 0.8472 | 0.2573 | 0.3668 |
| specweaver | 1.0 | 0.2037 | 0.3258 |

## 逐用例

| 用例 | 期望 | 交付 | keyword R/F1 | specweaver R/F1 | SpecWeaver 漏检 |
|---|---|---|---|---|---|
| t1-adjust-departure | 6 | 18 | 0.8333/0.5556 | 1.0/0.5 | — |
| t2-occupancy-window | 4 | 18 | 0.75/0.375 | 1.0/0.3636 | — |
| t3-block-publish-on-conflict | 6 | 18 | 0.8333/0.625 | 1.0/0.5 | — |
| t4-submit-page-api | 3 | 18 | 0.6667/0.2667 | 1.0/0.2857 | — |
| t5-preview-before-publish | 1 | 18 | 1.0/0.1429 | 1.0/0.1053 | — |
| t6-regression-redline | 2 | 18 | 1.0/0.2353 | 1.0/0.2 | — |

## 代价与用量

- `GetContext` 跨度耗时(ms)：中位 5011.549999999999 / 最大 5305.1（样本 n=6，p95 需更大样本量，直方图已在 `metrics.txt`）
- 平均 bundle bytes：6178（预算 8000）；平均每用例后端调用：56
- LLM 规划调用合计 6 次，prompt/completion tokens 758/637

## 局限性

- 金标由本项目人工标注（非公开基准），语料是 20 构件的教学项目，结论只在该语料与该标注口径下成立；
- **小语料下预算不构成约束**：本次 bundle 平均 6178 bytes / 预算 8000，precision 宏平均仅 0.2037——即『最小充分』在未触及预算时退化为『接近全量交付』，选择性必须靠紧预算与大语料实验来证明（见 report 中 `budget_bytes` 参数）；
- 单任务、无历史会话，不测多轮补召回；
- keyword 臂不建索引、不看图、无约束保底，但**给了与 SpecWeaver 相同的字节预算且只保留有命中文档**，不是刻意做弱的对照。
