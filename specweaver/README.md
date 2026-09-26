# SpecWeaver（规格织网）

规格驱动开发（SDD）的**工程上下文运行层**：Agent 动手前给出当前有效、最小充分、来源可核对的工程依据；任务完成后把代码变化与验证结果反向织回工程记录，支持跨会话/跨 Agent 接续。

- 工程资料库与混合检索：**seekdb**
- 工作记忆与任务交接：**PowerContext**
- 对 Agent 接口：**MCP**（stdio / streamable-http）与 **CLI**

架构与设计取舍见 [`../docs/01-架构设计说明书.md`](../docs/01-架构设计说明书.md)、[`../docs/03-工程骨架设计.md`](../docs/03-工程骨架设计.md)；本文件只写**怎么用怎么测**。

## 安装

```powershell
# 在仓库根 E:\2026ob_projects\SDD 执行
..\.\.venv\Scripts\python -m pip install -e ".\specweaver[seekdb,powercontext,mcp,cli,server,dev]"
```

| extra | 内容 | 何时需要 |
|---|---|---|
| `seekdb` | pyseekdb | 工程目录与混合检索 |
| `powercontext` | httpx | 记忆与交接 |
| `mcp` | fastmcp | MCP 工具面 |
| `cli` | typer + rich | CLI 命令 |
| `server` | uvicorn | streamable-http 服务与 `/metrics` |
| `dev` | pytest / pytest-asyncio / pytest-cov / ruff / httpx | 开发与门禁 |

后端容器（seekdb + PowerContext）的启动、镜像与 WSL 坑位见 [`deploy/README.md`](deploy/README.md)。

## MCP 工具（11 个，均可被任意 MCP Agent 调用）

| 工具 | 读/写 | 幂等 | 作用 |
|---|---|---|---|
| `sw_ping` | 读 | ✅ | 存活探针 |
| `sw_doctor` | 读 | ✅ | 后端连通 + 推理模式（只 `SELECT version()` 与 `/health`，不写） |
| `sw_get_context` | 读 | ✅ | **核心**：组装带预算与引用的 Context Bundle |
| `sw_verify` | 读 | ✅ | 三方一致性核对报告（工作区/目录/活动/记忆） |
| `sw_explain_source` | 读 | ✅ | 单构件回源链：source 指针 + upstream `based_on` + downstream 关系 |
| `sw_ingest_project` | 写 | ✅ | 增量摄入（upsert 收敛；记忆写入按 PowerContext 幂等语义） |
| `sw_complete_task` | 写 | ❌ | 跑测试 + 反向回写 + 记录变更集/结果（每次追加新证据行） |
| `sw_resume_task` | 写 | ❌ | 接续 Handoff（服务端登记接续）+ 核对 + 重建上下文 |
| `sw_handoff` | 写 | ❌ | 提交交接快照，返回 `handoff_rev` |
| `sw_record_decision` | 写 | ❌ | 决策沉淀：新记 / 改判（revise）/ 停用（retire） |
| `sw_report_progress` | 写 | ❌ | 进度备忘，可顺带提交 Handoff |

读写/幂等声明即 MCP `ToolAnnotations`，Agent 据此判断能否安全重试。接入配置见 [`deploy/mcp.stdio.json`](deploy/mcp.stdio.json) / [`deploy/mcp.http.json`](deploy/mcp.http.json)。

## CLI

```
specweaver doctor
specweaver ingest  <project_id> [--scope-id ...] [--register-source/--no-register-source]
specweaver context <project_id> "<任务描述>" [--base-ref ...]
specweaver finish  <project_id> <task_id> <base_ref> [--test-command ...] [--scope-id ...]
specweaver handoff <project_id> [--objective ...] [--state ...]x [--next-step ...]x [--omission ...]x
specweaver resume  <project_id> [--objective ...] [--handoff-rev ...] [--use-handoff/--no-use-handoff]
specweaver version
```

公共选项 `--json`（机器可读）、`--usage-out <path>`（导出跨度 CSV，含引擎级 `metrics` JSON 列）。退出码：0 正常 / 1 测试未过（`finish`）/ 2 用例或后端错误 / 3 `--usage-out` 写入失败。

## 测试与门禁

```powershell
python scripts\gate.py            # 离线：ruff + 单元/契约（无需容器）
python scripts\gate.py --live     # 追加：doctor + 11 工具真实链路 + /metrics 探针（慢，verify_mcp 内部会跑全量测试）
python scripts\gate.py --live --demo   # 再追加：铁路演示并写 evidence/
```

分层口径：`tests/unit/`（含 `unit/boundary/` 审计回归组）注入 fakes，不碰网络；`tests/contract/` 用同一组行为用例校验端口可替换性；`tests/integration/` 打真容器（容器不在时会跳过，`--live` 门禁会显式提醒）。

## 脚本

| 脚本 | 用途 |
|---|---|
| `scripts/gate.py` | 一键门禁（离线/在线） |
| `scripts/run_demo.py` | 铁路调度教学演示 → `evidence/<project>-<ts>/` |
| `scripts/run_off_on.py` | 工具 OFF/ON 双臂对照（Claude Code 驱动，隐藏验收判据） |
| `scripts/verify_mcp.py` | 11 工具逐个真实调用（in-process MCP 客户端 + 真后端） |
| `scripts/probe_metrics_http.py` | 起 streamable-http 服务，跑真实 MCP 流量后抓 `GET /metrics` |

## 配置

`specweaver/.env`（已 gitignore）按"变量名 = 字段路径 + 双下划线"覆盖，例如：

```
INFERENCE__PROVIDER=qianwen
INFERENCE__BASE_URL=https://<gateway>/compatible-mode/v1
INFERENCE__MODEL=qwen-flash
INFERENCE__EMBED_MODEL=text-embedding-v4
INFERENCE__DIM=1536
INFERENCE__API_KEY=<your key>
WORKSPACE__ROOT=E:/path/to/target/repo
```

进程环境变量优先于 `.env`；`.env` 的定位与当前工作目录无关（项目根的那份是兜底，cwd 的那份优先），因此在任何目录跑 `doctor` 都不会静默退回规则模式。无 key 时自动降级为规则规划 + 确定性向量，功能链路不变。
