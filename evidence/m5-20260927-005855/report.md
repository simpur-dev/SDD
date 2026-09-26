# M5 交付验收证据（2026-09-27 00:59）

M5 承诺清单的落地证明：`RecordDecision / ReportProgress / VerifyState / ExplainSource` 四用例经 MCP 暴露，
`MemoryPort.revise/retire/list_entries`、`TestRunnerPort.parse_report`、`ActivityLogPort.list_change_sets` 全部被真实消费，
引擎级埋点与 Prometheus `/metrics` 导出可抓取。

## 环境（实测）

- seekdb：`5.7.25-OceanBase seekdb-v1.4.0.0`（Docker 容器 `sw-seekdb`，healthy）
- PowerContext：容器 `sw-powercontext`，`status: ready`（memory/handoff/experience 均 enabled）
- 推理：`provider=qianwen`（`qwen-flash` 规划 + `text-embedding-v4` @1536 语义向量），配置在 gitignore 的 `specweaver/.env`
- Python 3.11 venv；本次全量门禁：`pytest -q` **181 passed**、`ruff check .` **All checks passed**

## 文件

| 文件 | 内容 |
|---|---|
| `verify-mcp.txt` | `scripts/verify_mcp.py`：in-process FastMCP 客户端把 **11 个工具**逐个真实调用一遍（真 seekdb + 真 PowerContext + 真 LLM） |
| `metrics-probe.txt` | `scripts/probe_metrics_http.py`：以子进程启动 `run_http`（streamable-http），真实 MCP 流量跑 `sw_get_context`+`sw_verify` 后抓取 `GET /metrics` 全文 |

## 关键结果（逐条可核对）

- 工具注册数：`== 11 tools ==`（7 个既有 + M5 的 `sw_record_decision`/`sw_report_progress`/`sw_verify`/`sw_explain_source`）
- 决策三段：`remembered entry=mem_ent_e0288381260543f69cbf180de0893e09` → `revised` → `retired`（`revise/retire` 走真实 citation 定位，非内存假件）
- 错误契约：互斥参数探针返回 `ToolError: [SW-ERROR] record_decision takes either replaces_entry_id or retire_entry_id, not both`
  （文件首行的 `Error calling tool 'sw_record_decision'` 是服务端对这次**预期失败**的日志，非缺陷）
- 一致性核对：`checked=159 mismatches=0 change_set_stale=False test_report=absent rules=0 constraints=0 notes=1`
  （`notes=1` = “last test run recorded no junit report_ref; counts come from the activity log alone”，主动披露而非静默）
- 接续链路：`sw_handoff -> handoff:handoff:12`，`sw_resume_task -> handoff_resumed=True ... mismatches=0`
- 回写链路：`sw_complete_task -> success=true, test_total=181, test_passed=181, test_failed=0, files_changed=12`
- `/metrics`：`GET /metrics -> 200`（空进程时仅 `# trace_id` 注释行，符合 Prometheus 文本格式），真实流量后聚合出
  `sw_spans_total{span="get_context"} 1`、`sw_span_duration_ms_sum{span="get_context"} 2591.866`（含真实 LLM 规划耗时）、
  `sw_llm_prompt_tokens_total{span="get_context"} 177` / `sw_llm_completion_tokens_total ... 103`、
  `sw_backend_calls_total{span="get_context"} 53`，以及引擎级 `sw_engine_metric_sum{span="get_context",metric=...}`：
  `recall=20.0 valid=20.0 excluded=0.0 findings=10.0 bundle_bytes=7864.0 assembly_ms=0.8`
- MCP 传输未被 `/metrics` 插入破坏：`MCP over http -> 11 tools (first=sw_ping)`（lifespan/会话管理器正常）

## 本轮发现并修复的真实缺陷

`POST /v1/memory/remember` 对**同一 scope 内文本完全相同**的写入做了去重：返回 200 但 `entry: null`（revision 不推进）。
原适配器用 `require(res, "entry", ...)` 读取，导致“同一任务重复跑第二次”直接失败（`sw_complete_task` 复跑时实测触发）。
修复：适配器在 `entry=null` 时经 `/v1/memory/entries/list` 按文本回读既有条目并保持 `remember` 幂等；
找不到匹配项才抛 `SWError`。`verify-mcp.txt` 中 `sw_report_progress -> entry=mem_ent_ca7f3f6eba5348018ce5720dd5d91b40`
与上一轮同 id，即该回读路径的实测证据（同文本第二次写入未新增条目）。
对照组实测：`entries/revise` 写入重复文本**不**去重（正常返回新 revision 条目），但携带陈旧 citation 会 `409 revision_conflict`
——适配器 `revise()` 先 `entries/list` 取最新 citation，故不受影响。

## 局限性（不美化）

1. `sw_verify` 的 `rules=0/constraints=0`：`mcp-verify` 项目是对整仓的摄入，本仓未写 `rule` 类构件；规则↔约束对账在 `demo/railway` 侧才有非零样本。
2. `test_report=absent`：`SubprocessTestRunner` 只在配置了 junit 产物时才有 `report_ref`，当前演示命令未产出，报告以 `notes` 明示而非假装一致。
3. `sw_explain_source` 抽查目标是 `code` 构件（`upstream=0 downstream=0`）；`based_on` 上游链在需求/规则构件上才成链，此处仅证明图查询与去重路径可用。
4. `/metrics` 为**进程累计值**：可求均值（sum/count），p95 需 histogram，尚未实现；逐跨度分布仍由 `--usage-out` CSV 承担。
5. 探针跑在 `127.0.0.1`，未涉鉴权；共享服务部署时的 `/metrics` 访问控制属部署侧议题（`deploy/`）。

## 复现

```powershell
# 在 specweaver/ 目录下（需先起 deploy/docker-compose.yml 的两个容器）
..\\.venv\\Scripts\\python.exe scripts\\verify_mcp.py
..\\.venv\\Scripts\\python.exe scripts\\probe_metrics_http.py     # 退出码 0 = PROBE PASS
```
