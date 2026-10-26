# minimax/ 提交材料索引

> 本目录对正式题面（2026-10-26）§三「提交材料」：作品材料放在参赛仓库 **`minimax/`** 目录，评审以平台记录的固定提交为准。
> 六项必做的合规状态与证据索引见 [`合规核对.md`](合规核对.md)。

## 提交到比赛私有仓（正式渠道）

正式提交**不在本仓库**：请基于 https://github.com/oceanbase/powercontext/tree/2026-competition-ecosystem 导入的私有仓库，在其同名分支 2026-competition-ecosystem 上开发与提交。

1. 克隆平台分配的私有仓库，切到 2026-competition-ecosystem 分支；
2. 将本目录全部内容复制到该仓库根目录的 minimax/（覆盖空 .gitkeep；其他四家的目录保持不动）；
3. 在私有仓内：git add minimax && git commit -m "feat(minimax): SDD context module + validation sample + technical records" && git push origin 2026-competition-ecosystem；
4. 记录**完整 40 位 commit SHA**（git rev-parse HEAD），在测评平台按该分支 + commit 提交；
5. 提交后从远端重新克隆该 commit，按 运行说明.md 做一次冷启动核对。

> 详细步骤与校验见本目录 [`合规核对.md`](合规核对.md) §3。

## 材料清单

| 正式题面要求 | 本目录落点 | 状态 |
|---|---|---|
| 完整源码（上下文模块、Agent 接入代码及配套程序） | `source/`（已生成：SpecWeaver 源码/部署/脚本 + `demo/railway/` + 证据；由 `specweaver/scripts/build_submission.py` 生成） | ✅ 已生成（源码变更后重新运行脚本） |
| 运行说明（依赖、配置、数据初始化、入口、测试命令、已知限制） | [`运行说明.md`](运行说明.md) | ✅ 起草完成 |
| 验证样例（任务、有效规格、初始数据、步骤、预期、重置） | [`验证样例.md`](验证样例.md) | ✅ 起草完成 |
| 代码与测试（改前/改后快照、diff、新增测试、回归、日志） | [`代码与测试.md`](代码与测试.md) + `source/evidence/` | ✅ 起草完成 |
| 技术使用记录（MiniMax / 数据库 / PowerContext） | [`技术使用记录.md`](技术使用记录.md) + `source/evidence/` | ✅ 起草完成（状态复用与规格重导入证据已补） |
| 一页技术说明 | [`一页技术说明.md`](一页技术说明.md) | ✅ 与 `docs/04` 同步 |

## 打包与提交步骤

```powershell
# 从仓库根运行：生成 minimax/source/（源码、部署、模板、脚本、验证样例工程）
.\.venv\Scripts\python .\specweaver\scripts\build_submission.py
# 提交时确保 minimax/ 下内容完整：
git add minimax && git commit -m "chore(submission): package minimax/ deliverable"
```

- `source/` 为生成物，不含 `.env` / 缓存 / `research/` / `demo/openspec-demo` 等本机资料；
- **不提交任何真实凭据**：配置示例全部使用占位值；
- 正式提交仓库是**基于 `oceanbase/powercontext` 的 `2026-competition-ecosystem` 分支导入的私有仓库**；把本目录整体放入该仓库的 `minimax/` 后，在该分支上 commit/push，并在平台按完整 commit hash 提交。

## 快速核对（评审视角）

1. 按 `运行说明.md` 起 seekdb + PowerContext，执行 `doctor`；
2. 按 `验证样例.md` 走一遍：导入 → 取上下文 → 用 MiniMax 改码 → 改前失败/改后通过 + 回归；
3. 重启模块，按 `技术使用记录.md` 的状态复用命令验证读取；
4. 核对 `source/evidence/minimax-dev-20261026-111336/` 与 `source/evidence/official-*` 中的原始记录。
