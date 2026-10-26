# SpecWeaver 依赖环境部署（seekdb + PowerContext）

两个指定后端：**seekdb**（工程资料库 + 混合检索）与 **PowerContext**（记忆 + 上下文 + 任务交接）。

本文档以**干净环境可复现**为目标：只需要 Docker（Linux、WSL2 或 Docker Desktop 均可），
PowerContext 由仓库内 `Dockerfile.powercontext` 从**固定公开 commit** 构建，不依赖开发机上的源码 checkout。

## 0. 组件与端口

| 组件 | 镜像 | 端口 | 版本（实测） |
| --- | --- | --- | --- |
| seekdb | `oceanbase/seekdb:latest`（Docker Hub，v1.4.0） | 2881(SQL) / 2886(HTTP) | `5.7.25-OceanBase seekdb-v1.4.0.0` |
| powercontext | `powercontext-server:local`（由本仓库 Dockerfile 构建） | 8000(HTTP) | PowerContext API 1.1.0（含 Source / Memory / Handoff / MCP） |

## 1. 干净环境快速启动（推荐）

```bash
cd specweaver/deploy

# 构建 PowerContext（固定 commit 2e163b4…；首次需拉取 uv 依赖，约 5–10 分钟）
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build

# 查看状态（两个容器都应 healthy）
docker compose -f docker-compose.yml -f docker-compose.build.yml ps
curl -s http://127.0.0.1:8000/health/ready
```

- 需要代理的环境：构建前导出 `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY`（compose 会作为 build args 传给 Dockerfile）；
- 若 2881/8000 被其他服务占用，可改宿主端口：
  `SEEKDB_SQL_PORT=12881 SEEKDB_HTTP_PORT=12886 PC_PORT=18000 docker compose ... up -d --build`，
  并同步设置 SpecWeaver 的 `SEEKDB__PORT` / `POWERCONTEXT__BASE_URL`；
- **已有本地镜像时（离线复跑）**：
  `docker compose -f docker-compose.yml -f docker-compose.run.yml up -d`（不构建、不拉取）；
- 重置数据：`docker compose ... down -v`（会删除 seekdb catalog 与 PowerContext 状态卷）。

启动完成后回到项目根执行 `specweaver doctor`（或 `python -m specweaver.adapters.driving.cli.app doctor`），
应看到 seekdb / PowerContext / inference 三行 OK。

> 首次启动请等两个容器都 `healthy`、再等几秒后执行 `specweaver ingest`：PowerContext 刚启动时
> `/v1/memory/*` 可能短暂 502。WSL2 下还需保持一个 WSL 会话（`wsl bash -lc "sleep 3600"`），
> 否则 VM 自动回收会让容器重启。

## 2. 为什么需要自建 PowerContext 镜像

- 上游的 release / PyPI `powercontext 1.0.0` 仍只有旧的 "PowerMem API"，**没有** 本题需要的
  Source / Handoff / PreparedContext / Skill 完整原语，也没有 MCP；
- 这些原语目前位于 `oceanbase/powercontext` 的 `master` 分支（含 `uv.lock`，可复现构建）；
- 因此本仓库的 `Dockerfile.powercontext` 直接固定 **commit `2e163b4338f5fe596dd8bcf752cad6940807f459`**
  （2026-09-25，纯 Python uv 构建），按上游 `docker/Dockerfile` 的多阶段方式构建，避免"开发机 checkout"这一不可复现依赖。
- seekdb 使用 Docker Hub 的 `oceanbase/seekdb:latest`（即 v1.4.0；`1.4.0` 这个 tag 不存在）。

## 3. 验证与访问

- PowerContext Swagger：`http://localhost:8000/docs`；健康：`/health/live`、`/health/ready`；
  MCP 端点：`http://localhost:8000/mcp`（GET 会被 307 到 `/mcp/`，未握手时 JSON-RPC 400 `Missing session ID` 属正常）；
- seekdb：SQL `localhost:2881`（root 无密码），HTTP `http://localhost:2886`；
- 两者数据卷：`seekdb-data`（容器内 `/var/lib/seekdb`，v1.4.0 的实际数据目录）、`seekdb-meta`
  （`/var/lib/oceanbase`，镜像管理面目录）、`pc-data`（`/data`）。

## 4. 鉴权姿态（重要）

本目录 compose 以**单机演示姿态**运行：PowerContext `access_mode=disabled`，seekdb root 空密码，
SpecWeaver 的 `/mcp` 与 `GET /metrics` 自身不带鉴权。放到共享机器/局域网时：

- PowerContext：`POWERCONTEXT_SERVER_ACCESS_MODE=enforced` + `POWERCONTEXT_SERVER_AUTH_TOKEN=<强随机>`，
  SpecWeaver 侧在 `.env` 填 `POWERCONTEXT__TOKEN=<同一 token>`；
- seekdb：设置 `ROOT_PASSWORD` 并同步 `SEEKDB__PASSWORD`；
- SpecWeaver HTTP 默认只绑 `127.0.0.1`，对外暴露请置于反向代理之后，并保护 `/metrics`。

## 5. 开发机补充（WSL2）

本机开发环境使用 Windows 11 + WSL2 Ubuntu-24.04 + Docker Engine。相关脚本在 `deploy/wsl/`：

- `setup_docker.sh`：安装 Docker Engine（拉镜像走宿主代理，IP 自适应）；
- 可选旧流程：`prep_powercontext.sh` 把 `oceanbase/powercontext` 拉到 `/opt/powercontext`，
  `build.sh` 用官方 Dockerfile 构建本地镜像——**干净环境不需要这一步**，直接用 §1 的 build override；
- WSL 空闲约 60s 会自动回收 VM，容器随之停止。需要长时间跑评测时保持一个 WSL 会话：
  `wsl bash -lc "sleep 7200"`，或用 `deploy/wsl/wait_ready.sh` 等待就绪；
- 冷启动瞬间访问 `localhost:2881/8000` 可能失败，等 healthy 后再跑 `doctor`。

## 6. 故障排查

| 现象 | 处理 |
| --- | --- |
| `failed to bind host port 2881/8000` | 本机有其他服务占用；用 §1 的 `SEEKDB_SQL_PORT`/`SEEKDB_HTTP_PORT`/`PC_PORT` 改端口，并同步 SpecWeaver 配置 |
| seekdb 容器反复重启（日志 `Segmentation fault` / `Starting seekdb...` 循环） | 多为容器可写层数据损坏；`docker compose ... down` 后重新 `up`（会重建容器，catalog 由重新 ingest 恢复）；持久化已改到 `/var/lib/seekdb` 卷，重建容器不再清数据 |
| PowerContext 构建失败且日志是网络错误 | 导出 `HTTP_PROXY/HTTPS_PROXY` 后重试 §1 的构建命令 |
| PowerContext 健康检查 404 | 确认使用的是本仓库构建的 `powercontext-server:local`（API 1.1.0），而不是旧发行版镜像 |
| PowerContext 刚启动时 `/v1/memory/*` 返回 502 | 等两个容器 `healthy` 后等几秒再跑 `ingest`；WSL2 下保持会话避免 VM 回收重启容器 |
| 数据想从零开始 | `docker compose ... down -v`，并使用新的 `project_id`（seekdb 记录键/ PowerContext scope 都按 project 隔离） |

## 7. 实测与证据

- seekdb：`SELECT version()` → `5.7.25-OceanBase seekdb-v1.4.0.0`；建库/建表/混合检索均实测；
- PowerContext：API 1.1.0、97 个路径、`/health/ready` 200、`/mcp` 在线；
- 仓库根 `evidence/` 保留了真实容器上的全链路、接口、检索质量与评测证据；
- 干净环境构建/启动/`doctor`/数据持久化的复核记录见 `evidence/official-clean-env-*`（由部署修复时产生）。
