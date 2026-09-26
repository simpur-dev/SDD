# 扩展性两点对照（M6 批 c，2026-09-27）

回答"管线成本随语料规模怎么变"。**这是两点观察值，不是受控扫描**：两个项目的构件来源、任务文本与召回数都不同，因此只能得出"成本主要由召回量而非语料规模决定"的定性结论；受控曲线（同一语料按 18/60/159/600 构件抽样）仍是待办。

| 语料 | 构件数 | 用例 | 后端调用 | 跨度耗时 | 召回 recall | LLM 调用 | 数据出处 |
|---|---|---|---|---|---|---|---|
| `railway`（demo 教学项目，scratch git 副本） | 18 | `get_context` ×3 | 60 / 60 / 66 | 5560 / 5123 / 5880 ms | 18 / 19 / 20 | 1（qwen-flash 规划） | `evidence/railway-20260927-023632/usage.csv` |
| `mcp-verify`（整仓摄入） | 159 | `get_context` ×1 | 53 | 2592 ms | 20（n_results 上限） | 1 | `evidence/m5-20260927-005855/metrics-probe.txt` |

## 读法与结论

- 语料从 18 涨到 159（×8.8），`get_context` 的后端调用反而从 60-66 降到 53：成本由 `n_results`（=20）封顶的召回量决定，**不随语料规模线性增长**；耗时差异同样来自 LLM 规划往返抖动（railway 三次都有 1 次 planner 调用，5.1-5.9s；mcp-verify 2.6s）。
- 真正的规模敏感点在**全量核对类路径**：`verify_state` 在 159 构件语料上 `backend_calls=4`（活动表与目录各几批），但 `ResumeTask`/`VerifyState` 仍按项目全量列构件再逐个与工作区比对，属 O(文件数) 语义（设计上要"整仓一致性"，大仓需要增量/抽样策略，已挂账为局限）。
- 本次改动直接降低的部分：`ExplainSource` 的 upstream `based_on` 走查由"每引用一次 get"改为**每层一次批量 `get_artifacts`**（官方 `Collection.get(ids=[...])`），一个 depth=3 的链若每层 5 个引用，往返从最多 15 次降到 3 次。
- 已知仍未做：`RetrievalEngine` 每次取上下文仍做 2 次项目级 `list_artifacts`（模块白名单 + 约束保底）、`GapDetector` 每需求一次 `neighbors`；`GetContext` 单用例 53-66 次后端往返即来源于此。

## 复现

```powershell
cd specweaver
..\\.venv\Scripts\python.exe scripts\run_demo.py            # 产出 evidence/railway-<ts>/usage.csv
..\\.venv\Scripts\python.exe scripts\probe_metrics_http.py  # 产出 GET /metrics 全文
..\\.venv\Scripts\python.exe scripts\eval_retrieval.py --out ..\evidence\retrieval-railway-8000
..\\.venv\Scripts\python.exe scripts\eval_retrieval.py --budget-bytes 1500 --out ..\evidence\retrieval-railway-1500
```

## 与检索质量证据的关系

同一批 M6 测量（`evidence/retrieval-railway-8000/`、`-1500/`）显示：生产预算下 recall 1.0（关键词基线 0.847），但 **1500 字节紧预算下我们 0.319 落后于基线 0.500**。也就是说"规模不怕、选择性还不够狠"——下一条改进是按 aider 的渐进披露给低相关条目做紧凑（仅引用）渲染，让同样的字节装进更多金标构件。
