# clone-and-run 验证（HEAD 633d5c3）

方法：`git clone` 到临时目录（克隆内没有 `.env`，因为它被 gitignore），在克隆里用同一解释器执行

- `PYTHONPATH=<clone>/specweaver/src python scripts/gate.py`（离线：ruff + 全量 pytest）
- `PYTHONPATH=<clone>/specweaver/src python -m specweaver.adapters.driving.cli.app doctor --json`（连真实 seekdb + PowerContext）

结果（原始输出见 `gate_offline.txt`）：

- `262 passed`，ruff 全绿，`GATE PASS (2 steps)`；
- doctor 在克隆内两个后端均 OK：seekdb `5.7.25-OceanBase seekdb-v1.4.0.0`、powercontext `status: ready`；
- 探针回显里带 `"access_mode": "disabled"` 等 checks 字段 —— 这就是 `deploy/README.md` 说的"doctor 会把鉴权姿态打印出来"，也是本机单机演示姿态的直接读数；
- `"inference_provider": "none"` 且无 bootstrap 错误：没有 `.env` 时推理后端自动落到规则（Basic）模式而非崩溃，即 S3「缺 .env 可降级」的实测口径；
- 由此同时说明被文档引用的 `specweaver/templates/`、`deploy/`、`tests/` 等文件都已入库：交付面不依赖任何未提交的本地文件。

复现：任选一台已起好两后端的机器，`git clone` 后按上面两条命令执行即可。
