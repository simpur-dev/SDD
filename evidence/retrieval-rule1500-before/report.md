# 检索质量金标评测（docs/01 §11 / docs/03 §11）

- 生成：20260927-064048；语料：demo/railway @ v1.1.0 (20 artifacts: 5 REQ / 3 RULE / 2 DES / 4 code / 4 test)
- 标注方法：金标由本项目人工标注，口径对齐 ContextBench 的 minimal-context 原则：以『完成该任务所需的最小充分依据』为准，逐条给出推导链（derivation），并可由 demo/railway 的 front matter 与关系图复核。标注者不是模型，且标注在评测前冻结。
- 两臂**同字节公平**：keyword 臂拿到的预算 = SpecWeaver 在该用例实际花在**构件**上的字节（chrome/findings 不计入），并用同一 `entry_block` 成本模型填充、只保留有命中的文档；因此 recall/precision 差异反映的是选择质量而非预算差异
- 推理 provider：`none`（规则模式下 planner 不产生 LLM 调用，混合检索仍走真实 seekdb）

## 宏平均

| 臂 | recall | precision | F1 |
|---|---|---|---|
| keyword | 0.375 | 0.5833 | 0.381 |
| specweaver | 0.1945 | 0.3055 | 0.2195 |

## 逐用例

| 用例 | 期望 | 交付 | keyword R/F1 | specweaver R/F1 | SpecWeaver 漏检 |
|---|---|---|---|---|---|
| t1-adjust-departure | 6 | 2 | 0.1667/0.2857 | 0.1667/0.25 | CODE-2335993c1bbc, DES-1, REQ-1, RULE-2, TST-e9c84656fadf |
| t2-occupancy-window | 4 | 2 | 0.25/0.3333 | 0.0/0.0 | CODE-4bfabc68a8f6, REQ-2, RULE-1, TST-da7154c71d35 |
| t3-block-publish-on-conflict | 6 | 3 | 0.3333/0.5 | 0.5/0.6667 | DES-2, REQ-3, TST-d4cf3c71d337 |
| t4-submit-page-api | 3 | 2 | 0.0/0.0 | 0.0/0.0 | CODE-e662196c212e, REQ-4, TST-46ecef6a906e |
| t5-preview-before-publish | 1 | 3 | 1.0/0.6667 | 0.0/0.0 | REQ-5 |
| t6-regression-redline | 2 | 3 | 0.5/0.5 | 0.5/0.4 | TST-e9c84656fadf |

## 代价与用量

- `GetContext` 跨度耗时(ms)：中位 357.54999999999995 / 最大 481.7（样本 n=6，p95 需更大样本量，直方图已在 `metrics.txt`）
- 平均 bundle bytes：1382.5（预算 1500）；平均每用例后端调用：69
- LLM 规划调用合计 0 次，prompt/completion tokens 0/0

## 局限性

- 金标由本项目人工标注（非公开基准），语料是 20 构件的教学项目，结论只在该语料与该标注口径下成立；
- **预算这次是硬约束**：bundle 平均 1382.5 bytes 用掉预算 1500 的 92%，条目额度被固定开销（框架 + findings 份额）挤占，所以本行的 recall 才是裁剪策略的真实成绩单；
- 单任务、无历史会话，不测多轮补召回；
- keyword 臂不建索引、不看图、无约束保底，但**给了与 SpecWeaver 相同的字节预算且只保留有命中文档**，不是刻意做弱的对照；
- 若启用 `--pc-project`，第三臂 `pc_prepare` 走的是官方 `/v1/context/prepare`（`max_bytes` 与 SpecWeaver 同预算、`include_code=true`）。它装配的是 PowerContext 侧的 source/memory 证据，工程构件（DES/CODE/TST）本就不在其中，因此只报 recall 与 blob 字节，不与另两臂比 precision：这一行度量的是官方上下文装配与工程上下文装配的覆盖面差异，而不是实现优劣。
