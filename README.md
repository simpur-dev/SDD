# SpecWeaver（规格织网）

第 6 届 OceanBase 开发者大赛 · **SDD 工程上下文工具**赛道参赛作品。

在开发 Agent 动手之前，给出**当前有效、最小充分、来源可核对**的工程依据；任务完成后把代码变化与验证结果**反向织回**工程记录，并支持跨会话/跨 Agent 接续。

- 工程资料库与混合检索：**OceanBase seekdb**（关键词 + 语义 + 版本/状态/模块收窄，RRF 融合）
- 工作记忆与任务交接：**PowerContext**（Memory remember/revise/retire、Handoff 提交与接续）
- 对 Agent 的接口：**MCP**（stdio / streamable-http，11 个工具）与 **CLI**（7 个命令：doctor · ingest · context · finish · handoff · resume · version）
- 推理后端不绑定品牌：`none | minimax | deepseek | qianwen`（OpenAI 兼容 chat + 各家 embeddings 差异由适配器吸收）

## 架构（冻结）

五层六边形：`domain`（零依赖） ← `application`（9 用例 + 5 引擎） ← `adapters`（driving: MCP/CLI；driven: seekdb/PowerContext/git/LLM），`shared/di.py` 是唯一装配根。
权威次序：**真实工作区 > seekdb 工程库 > PowerContext 记忆**。
详见 [`docs/01-架构设计说明书.md`](docs/01-架构设计说明书.md)（设计；其 §2 是赛题对齐矩阵与**交付物清单状态**）、[`docs/03-工程骨架设计.md`](docs/03-工程骨架设计.md)（骨架与契约）与 [`docs/02-调研纪要.md`](docs/02-调研纪要.md)（§7 为两个后端的容器实测与官方能力边界）。

## 五分钟跑通

```powershell
# 1) 起两个后端（WSL2 + Docker，含镜像与坑位说明）
#    见 specweaver/deploy/README.md
# 2) 安装（editable）
.\.venv\Scripts\python -m pip install -e ".\specweaver[seekdb,powercontext,mcp,cli,server,dev]"
# 3) 配置推理网关（可选：不配则自动降级为规则模式，功能链路不变）
Copy-Item .\specweaver\.env.example .\specweaver\.env   # 填自己的 key
# 4) 自检 + 门禁
specweaver doctor
.\.venv\Scripts\python .\specweaver\scripts\gate.py           # 离线：ruff + 单元/契约
.\.venv\Scripts\python .\specweaver\scripts\gate.py --live    # 在线：doctor + 11 工具 + /metrics
# 5) 铁路调度教学演示（赛题第七章），产出完整证据链
.\.venv\Scripts\python .\specweaver\scripts\run_demo.py
```

## 接入现成 Agent

MCP 配置样例（把 `python.exe` 与 `WORKSPACE__ROOT` 换成你机器上的路径）：

| 传输 | 样例 | 适用 |
|---|---|---|
| stdio | [`specweaver/deploy/mcp.stdio.json`](specweaver/deploy/mcp.stdio.json) | Agent 本地拉起，单项目 |
| streamable-http | [`specweaver/deploy/mcp.http.json`](specweaver/deploy/mcp.http.json) | 共享服务（先跑 `python -m specweaver.adapters.driving.mcp.run_http`），并可在同端口 `GET /metrics` 抓 Prometheus 指标 |

与**官方 seekdb MCP Server** 的分工：官方那套是"数据库运维面"（`execute_sql` / `hybrid_search` / seekdb 自带 memory 函数），SpecWeaver 是"工程上下文语义面"（构件/关系/有效性/预算/接续），并把 seekdb 与 PowerContext 织成一条链路——赛题要求两者同时使用，故不自建 MCP 无法成立。详见《03》§7.2。

## 仓库地图

```
赛题.md / 附件2.md            赛题说明（两文件内容相同，仅行尾差异）
docs/                         01 架构说明书 · 02 调研纪要 · 03 工程骨架设计 · architecture-map/
specweaver/src/specweaver/    工具源码（domain/application/adapters/shared）
specweaver/tests/             unit（含 boundary 审计组）· contract · integration（真后端）· fakes
specweaver/scripts/           gate.py · run_demo.py · run_off_on.py · verify_mcp.py · probe_metrics_http.py · eval_retrieval.py · scaling_probe.py
specweaver/deploy/            docker-compose + WSL 脚本 + mcp.*.json 样例
demo/railway/                 铁路调度教学项目（演示标的）+ gold/ 检索金标标注
evidence/                     railway-* 全链路 · retrieval-* 金标质量 · scaling-* 规模扫描 · off-on-* 效率对照 · m5-* / http-transport-* 接口与指标实测
research/                     调研克隆（spec-kit / powercontext，不随交付）
```

## 效果与证据（不美化）

| 维度 | 现状数字 | 出处 |
|---|---|---|
| 自动化测试 | 220 项（unit 含 boundary 审计组 + contract；容器在位时另跑 integration 真后端套件，`--live` 下有 skip 即判失败） | `scripts/gate.py` |
| 检索质量金标（6 任务，人工标注，三方对照） | recall：SpecWeaver **1.0** / 朴素关键词 0.847 / 官方 `/v1/context/prepare` 0.208（记忆侧装配，工程构件本不在其中）；precision 仅 0.204（bundle 平均 6363B＝预算 80%，未触及约束）；**紧预算 1500B：同一份金标三次独立运行 0.319 / 0.264 / 0.1945，基线 0.500 / 0.500 / 0.444 —— 此时我们稳定落后，缺陷未解**（"仅引用"紧凑渲染已试并因无增益回退） | `evidence/retrieval-railway-{8000,1500}-v2/`（修复前对照：`retrieval-railway-{8000,1500}/`） |
| 上下文预算保证 | 声明的字节预算现在对**交付文本**成立：④段引用清单计入成本 + 渲染后复测重裁；扫描 7 档预算断言渲染字节 ≤ 预算（其中 4 档含默认 8000B 在修复前会超），预算小于裸框架时由⑥段明确宣告 | `specweaver/tests/unit/engines/assembly/test_budget_guarantee.py` |
| 受控规模扫描（2 语料 × 3 召回上限 × 8 重复） | `n_results=5` 时 18 与 354 构件语料均 40 次后端调用（与规模无关）；`40` 时 65 vs 178（增量来自核对循环与图扩展）；p95 5.47-6.74s 由单次 LLM 规划主导 | `evidence/scaling-sweep-20260927/sweep.md` |
| 真实后端接口（进程内） | 11 个 MCP 工具逐个跑通（含 revise/retire/guard 探针与 `ToolAnnotations` 声明） | `evidence/m5-20260927-005855/` |
| 真实后端接口（streamable-http 传输） | 11 工具经真实 HTTP 传输全跑一遍：9/9 用例 span 全部出现、0 error、`sw_span_duration_ms` 直方图在位（span 缺失即判失败，用于区分"请求被应答"与"打到应用层"） | `evidence/http-transport-20260927-033036/probe.txt` |
| 全链路演示（M6 重跑） | 11/11 → 13/13 真实回归；`usage.csv` 含引擎级 `metrics` 列；Bundle ④段回读 PowerContext 工作记忆（该部署记忆侧只有 fts 词面召回，命中 0 属正常，见《02》§7.6） | `evidence/railway-20260927-023632/` |
| 效率对照（hard 档，N=3） | 成功率 3/3 vs 3/3；ON 中位耗时 46.1s vs OFF 82.3s，输出 tokens 中位 8185 vs 14500；**均值 -26%/-28%，但 ON 最差一次劣于全部 OFF** | `evidence/off-on/20260926-235601/` |
| 上下文组装用量（同一次 HTTP 探针内） | `get_context` 3 次真实 planner 调用：prompt/completion 336/292 tokens、召回 57 条（有效 9、排除 48）、装配 7322 bytes；整条 11 工具链共 381 次后端往返 | `evidence/http-transport-20260927-033036/probe.txt` |

已知局限（检索质量缺金标指标、大仓库全量核对成本、演示基线只有"无工具"一臂、`/metrics` 无鉴权等）诚实记录在《01》§11 与各 `evidence/*/report.md` 内。

## 开发约定

- 每个改动必须过 `scripts/gate.py`；碰后端链路的改动必须过 `--live`。
- 提交用 Conventional Commits（英文），按模块/依赖顺序分批推送。
- 适配层不得向应用层泄漏非 `SWError` 异常（《03》§7.1 契约），错误码需在 MCP/CLI 两端可见。
- `specweaver/.env` 已被 gitignore，**切勿提交凭据**；对外分享仓库前确认包内无 `.env`。

## 许可

Apache-2.0，见 [LICENSE](LICENSE)。
