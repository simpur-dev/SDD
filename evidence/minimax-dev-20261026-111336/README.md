# MiniMax 实际参与开发记录（轨道验证）

- 生成：20261026-111336（Asia/Shanghai）
- 目的：验证正式题面必做项「MiniMax 实际参与代码修改」，并形成可复盘的开发记录。
- 结论：**通过**。MiniMax 模型通过 Claude Code（Anthropic 兼容端点）完成实际代码修改，产出的 diff、测试与上下文来源均可核对。

## 1. 环境与模型

| 项 | 值 |
|---|---|
| 开发助手 | Claude Code 2.1.261（claude -p --output-format stream-json） |
| 模型服务 | MiniMax Coding Plan（pi.minimaxi.com） |
| 模型 | **MiniMax-M2.7**（ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic） |
| 配置方式 | --settings 局部 settings（模板见 minimax-claude-settings.template.json；真实 key 仅在本机临时文件，未入库） |
| 上下文模块 | SpecWeaver（本仓库）：ingest 摄入 + get_context 生成 Bundle，MiniMax 同时用于规划/向量（MiniMaxEmbedding embo-01） |
| 数据库 | seekdb v1.4.0（本机 127.0.0.1:12881，因同机其他项目占用默认端口而临时改端口） |
| 记忆 | PowerContext（127.0.0.1:18000，API 1.1.0） |

- 代码快照：`before/`（改前）与 `after/`（改后），差异见 `agent.diff`；
- 一键复现：`reproduce.md`（应用 diff → pytest 10→16 passed → target 5/5 FAIL→PASS → hidden 3/3）。

## 2. 任务与上下文

- 工程：demo/railway @ baseline $base
- 任务：按接口契约新增 schedule.adjust_departure 与 pi.submit_adjust_departure，保持既有搜索/占用/发布行为
- 提供给 Agent 的上下文：context.md（6531 B；来源见 context.json）
  - citations（18）：REQ-1、REQ-2、REQ-3、REQ-4、REQ-5、RULE-1、RULE-2、RULE-3、DES-1、DES-2、CODE-e662196c212e、CODE-2335993c1bbc、CODE-4bfabc68a8f6、CODE-12d4b7620710、TST-e9c84656fadf、TST-da7154c71d35、TST-d4cf3c71d337、TST-46ecef6a906e
  - findings：1 conflict + 5 gap（与演示标的一致）
- 实际发送的 prompt：prompt.txt（SHA256 前缀 FC85C2460A19671B）

## 3. MiniMax 用量（Agent 侧）

`json
{
  "model": "MiniMax-M2.7",
  "num_turns": 16,
  "tool_calls": {
    "Bash": 4,
    "Read": 8,
    "Edit": 2,
    "Write": 1
  },
  "usage": {
    "input_tokens": 18697,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 114342,
    "output_tokens": 2809,
    "output_tokens_details": {
      "thinking_tokens": 803
    },
    "server_tool_use": {
      "web_search_requests": 0,
      "web_fetch_requests": 0
    },
    "service_tier": "standard",
    "cache_creation": {
      "ephemeral_1h_input_tokens": 0,
      "ephemeral_5m_input_tokens": 0
    },
    "inference_geo": "",
    "iterations": [],
    "speed": "standard"
  },
  "transcript_bytes": 105148
}
`

- 结果事件：16 turns；工具调用 Bash×4、Read×8、Edit×2、Write×1；模型名 MiniMax-M2.7 出现在响应中。
- 注：Claude Code 对非官方模型名会打印 [claude-code:unrecognized_model]（仅本地计价提示），不影响请求与执行。

## 4. 代码修改与测试证据

git diff 52a62068ef34..HEAD：

`
 src/api.py           |  7 +++++-
 src/schedule.py      | 14 +++++++++++
 tests/test_adjust.py | 67 ++++++++++++++++++++++++++++++++++++++++++++++++++++
 3 files changed, 87 insertions(+), 1 deletion(-)

`

| 检查 | 修改前 | 修改后 |
|---|---|---|
| 目标行为测试（behavior-level，见 	arget-tests.py） | FAIL（	arget-before.txt，5/5 失败，原因是目标行为/接口尚未实现） | PASS（	arget-after.txt，5/5 通过） |
| 工程测试 python -m pytest -q | 10 passed（aseline-pytest.txt） | **16 passed**（post-pytest.txt） |
| 隐藏验收 
ailway-acceptance.py（diff 捕获后注入） | — | **3 passed**（hidden-acceptance.txt） |

- 代码 diff：gent.diff（SHA256 前缀 24BA30A90B84E621）
- 改动文件：src/schedule.py、src/api.py、	ests/test_adjust.py（未改动既有测试）
- Agent 提交：3f5884 feat: adjust departure by stop

## 5. 数据库 / 记忆记录

db-powercontext-record.json：

- seekdb：18 个 artifact（requirement 5 / rule 3 / design 2 / code 4 / test 4）
- 上下文生成实际后端调用：context-usage.csv（get_context span：1 次 LLM、67 次 backend、recall 18 / valid 16 / excluded 2 / bundle 5866 B）
- PowerContext：scope 解析成功，1 条 ingestion 记忆；测试运行留痕表当前为空（本条只做读路径）

## 6. 可复现步骤（真实 key 用环境变量注入）

`powershell
# 1) 起 backend（本机默认端口被其他栈占用，这里用临时端口）
wsl -d Ubuntu-24.04 -u root -- bash -lc "cd /mnt/e/2026ob_projects/SDD/specweaver/deploy && SEEKDB_SQL_PORT=12881 SEEKDB_HTTP_PORT=12886 PC_PORT=18000 docker compose -f docker-compose.yml -f docker-compose.run.yml up -d"
# 2) SpecWeaver 环境变量（provider=minimax, embed=embo-01@1536）
#    INFERENCE__PROVIDER=minimax / BASE_URL=https://api.minimaxi.com/v1 / MODEL=MiniMax-M2.7
#    INFERENCE__API_KEY=<key> / SEEKDB__PORT=12881 / POWERCONTEXT__BASE_URL=http://127.0.0.1:18000
# 3) ingest + get_context（本记录使用 CLI + Python API 生成 context.md/context.json）
# 4) claude --settings <minimax settings> -p ...（模型 MiniMax-M2.7）
# 5) 记录 diff / pytest / 目标测试 / hidden acceptance
`

- 文件摘要（SHA256 前 16 位）：prompt=FC85C2460A19671B，agent.diff=24BA30A90B84E621，context.md=A69A1BE158E7E965

## 7. 诚实记录

- MiniMax 通过本机 Anthropic 兼容端点接入；Claude Code 的 	otal_cost_usd 按官方价格估算，仅作参考，不对应 MiniMax 账单。
- 本机同时运行了其他项目的 Docker 栈，故本次将 SpecWeaver 后端映射到 12881/12886/18000；正式交付仍使用默认 2881/8000，且不需要开发者本机环境。
- 本次只验证「MiniMax 实际参与代码修改」；正式题面其余必做项（干净环境运行、状态复用、规格更新后重导入、一页说明等）另行补证。