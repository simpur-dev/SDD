# SpecWeaver 规格模板（吸收/改造自 GitHub Spec Kit）

这些模板定义了**SpecWeaver 能读懂的工程资料形状**：按此写的 markdown 会被摄入引擎抽取为带 id、类型、模块、行为点与约束点的构件，进而参与混合检索、有效性判定与上下文组装（《01》§4.3）。

- 与 Spec Kit 的差异：只保留 SDD 闭环真正用到的字段，且字段名与 `application/engines/ingestion/parsers/markdown.py`、`normalize.py` 的解析规则一一对应（有回归测试锁定：`tests/unit/engines/test_templates_contract.py`）。
- 前置元数据（front matter）目前被消费的键：`id`、`type`、`title`、`module`。`version` / `status` 供人与 Agent 书写意图，**版本与状态的实际裁决权在工具**：状态由生命周期引擎与工作区事实决定（权威序：真实工作区 > seekdb > PowerContext），版本由 `complete_task` 回写时推进，因此不要在文档里手工改写状态来"骗过"核对。

| 模板 | 摄入类型 | 落地位置建议 |
|---|---|---|
| `constitution.md` | `rule`（别名 constitution） | `rules/` 或 `docs/constitution.md` |
| `spec-template.md` | `requirement` | `specs/<feature>.md` |
| `plan-template.md` | `design`（别名 adr） | `design/<module>.md` |
| `tasks-template.md` | 不入库（Agent 工作产物） | `specs/<feature>.tasks.md` |
| `checklist-template.md` | 不入库（验收清单） | `specs/<feature>.checklist.md` |

书写要点（决定分类质量）：

- 一句一条，行为用"应/必须/须/shall/must"，约束用"禁止/不得/严禁/must not"——含禁止类词的条目无论标题在哪都会被归入约束，检索时享受**约束保底**（不会被 LLM 收窄挤掉）；
- 交叉引用直接写 id（`REQ-1`、`RULE-3`）或用标签 `@implements REQ-1` / `@tests CODE-x` / `@covers REQ-2` / `@realizes REQ-1` / `@refines DES-2`，摄入时据此建边；
- 标题词影响归档桶：`需求/行为/功能/验收/场景/决策` → 行为；`约束/限制/非功能/规则/禁止` → 约束。
