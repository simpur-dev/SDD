# SpecWeaver（规格织网）

规格驱动开发（SDD）的**工程上下文运行层**：在 Agent 动手前给出当前有效、最小充分、来源可核对的工程依据；
任务完成后把代码变化与验证结果反向织回工程记录，支持跨会话/跨 Agent 接续。

- 工程资料库与混合检索：**seekdb**
- 工作记忆与任务交接：**PowerContext**
- 对 Agent 接口：**MCP**（stdio / streamable-http）与 **CLI**

## 快速开始

```powershell
# 1) 起依赖（见 deploy/README.md）
# 2) 安装
.\.venv\Scripts\python -m pip install -e '.\specweaver[seekdb,powercontext,mcp,cli,dev]'
# 3) 自检
specweaver doctor
```

详见 `../docs/01-架构设计说明书.md`、`../docs/03-工程骨架设计.md`。
