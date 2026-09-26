# 任务拆解：<特性名>

> 工作产物模板，不入库检索（无 front matter 的 `type`）。它是 Agent 的**执行契约**：
> 每个任务完成后调用 `sw_complete_task`，由工具把代码变化反向织回 `REQ-/DES-/TST-` 构件。

- 关联规格：REQ-<n>（本文件从该规格展开）
- 基线 ref：`<git rev>`（`sw_get_context` / `sw_complete_task` 都要用到，别凭记忆填）

## 任务

| # | 任务 | 覆盖 | 验收 | 状态 |
|---|---|---|---|---|
| 1 | <动作 + 落点> | REQ-<n> | <测试名或可观察结果> | todo |
| 2 | <为上一任务补测试> | TST-<m> | `pytest -q` 全绿 | todo |

## 顺序与依赖

- 先 1 后 2；任何时刻工作区状态必须可编译、可运行既有测试。
- 每完成一项，把状态改为 done 并记录实际改动的文件清单（与 `sw_complete_task` 输出的 `files_changed` 对齐）。

## 中断接续

- 长任务在收工前调用 `sw_handoff`（`state` 填已完成的事实清单，`next_steps` 填下一棒要做的具体动作，`omissions` 填尚未验证的部分），新会话用 `sw_resume_task` 带 `handoff_rev` 接续。
- 不要用手改本文"状态列"的方式替代工具核对：`sw_verify` 会以工作区事实为准给出偏差。
