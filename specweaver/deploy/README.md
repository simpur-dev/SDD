# SpecWeaver 依赖环境部署（已在本机 WSL2 验证通过）

两个官方指定后端：**seekdb**（工程资料库 + 混合检索）与 **PowerContext**（记忆 + 上下文 + 任务交接）。

本机采用：**WSL2 Ubuntu-24.04 + Docker Engine**（Docker Desktop 在 Windows 内部版 26200 下有数据盘兼容问题）。



***

## 0. 组件与端口（实测）



| 组件           | 镜像                               | 端口                   | 实测                                      |
| ------------ | -------------------------------- | -------------------- | --------------------------------------- |
| seekdb       | `oceanbase/seekdb:latest`（819MB） | 2881(SQL)/2886(HTTP) | `5.7.25-OceanBase seekdb-v1.4.0.0`      |
| powercontext | 本地构建 `powercontext-server:local` | 8000(HTTP)           | **PowerContext API 1.1.0，97 个路径，含 MCP** |

### 为什么 PowerContext 用 `master` 分支（重要）



* 截至目前，**所有已发布的 release/tag（最新 v1.1.7、PyPI&#x20;**`powercontext`**&#x20;1.1.0）内部仍是旧的 "PowerMem API"**：

  只有 `/api/v1/memories` 等记忆存储接口，**没有 MCP，也没有赛题描述的 Source / Handoff / PreparedContext / Skill 完整原语**。

* 赛题描述的完整 **PowerContext**（Source、Memory revise/retire、Handoff、Skill、Scope、MCP、多 Agent 集成）

  **目前只存在于&#x20;**`master`**&#x20;分支**（有 `uv.lock`，可复现构建；赛题本就按它设计）。

* 因此 `prep_powercontext.sh` 拉取并使用 `master`，构建时以 `POWERCONTEXT_VERSION=1.2.0.dev0` 标识。

### seekdb 镜像 tag 说明

Docker Hub 上 `oceanbase/seekdb:1.4.0`**&#x20;这个 tag 不存在**，请使用 `oceanbase/seekdb:latest`（即 v1.4.0）。

运行 override 已固定为 latest 并禁止拉取。



***

## 1. 一次性安装（脚本在 `deploy/wsl/`，经 `wsl -u root` 以 root 运行，无需密码）



```powershell
cd E:\2026ob_projects\SDD\specweaver\deploy

wsl -d Ubuntu-24.04 -u root -- bash /mnt/e/2026ob_projects/SDD/specweaver/deploy/wsl/setup_docker.sh      # 装 Docker（拉镜像走宿主代理，IP 自适应）
wsl -d Ubuntu-24.04 -u root -- bash /mnt/e/2026ob_projects/SDD/specweaver/deploy/wsl/prep_powercontext.sh # 拉 powercontext master 到 /opt/powercontext
wsl -d Ubuntu-24.04 -u root -- bash /mnt/e/2026ob_projects/SDD/specweaver/deploy/wsl/build.sh            # 用官方 Dockerfile 构建
```

> master 的官方 Dockerfile 为纯 Python（uv 构建），
>
> **不含前端阶段，无需 pnpm/node 修补**
>
> 。
> 早期 v1.0.0 需要的 
>
> `wsl/Dockerfile.pc`
>
> （固定 pnpm9）仅作历史保留，master 构建不使用。



***

## 2. 启动与验证（日常）



```powershell
# 彻底（重新）部署并验证：down → up（全本地镜像、离线）→ 等待 → 核对路由与 MCP
wsl -d Ubuntu-24.04 -u root -- bash /mnt/e/2026ob_projects/SDD/specweaver/deploy/wsl/clean_redeploy.sh

# 仅启动（幂等）
wsl -d Ubuntu-24.04 -u root -- bash /mnt/e/2026ob_projects/SDD/specweaver/deploy/wsl/start2.sh
```

手动等价命令（WSL 内）：

```bash
cd /mnt/e/2026ob_projects/SDD/specweaver/deploy
docker compose -f docker-compose.yml -f docker-compose.run.yml up -d          # 运行（本地镜像，离线）
docker compose -f docker-compose.yml -f docker-compose.build.yml build powercontext  # 重新构建
```



***

## 3. compose 文件分工



| 文件                         | 作用                                                                                 |
| -------------------------- | ---------------------------------------------------------------------------------- |
| `docker-compose.yml`       | 基础编排：seekdb + powercontext（环境 / 健康检查 / 卷）                                          |
| `docker-compose.build.yml` | 构建 override：从 `/opt/powercontext` 用官方 `docker/Dockerfile`，传 `POWERCONTEXT_VERSION` |
| `docker-compose.run.yml`   | 运行 override：两服务都锁定本地镜像（seekdb:latest /powercontext-server:local），**禁止任何拉取 / 构建**   |
| `init/01_schema.sql`       | seekdb 参考建表 DDL（正式由 SpecWeaver 初始化执行）                                              |



***

## 4. 访问方式



* PowerContext Swagger：`http://localhost:8000/docs`；OpenAPI：`http://localhost:8000/openapi.json`

* 健康检查：`http://localhost:8000/health/live`、`http://localhost:8000/health/ready`

* **MCP 端点**：`http://localhost:8000/mcp`


  * 浏览器 / GET 直接访问会 **307 重定向到&#x20;**`/mcp/`；

  * 未完成 MCP 握手时返回 JSON-RPC `400 Missing session ID`（并下发 `mcp-session-id`）——**这是正常现象**。

  * 标准用法是 MCP 客户端先 `initialize` → `notifications/initialized` 建立会话，再调用工具。

* seekdb：SQL 连 `localhost:2881`（root 无密码），HTTP/Dashboard `http://localhost:2886`。

已实测的 PowerContext 原语分组（97 路径中）：`/v1/sources/*`、`/v1/scopes/*`(21)、

`/v1/work/handoffs/*`、`/v1/external-skills/*` 等。



***

## 5. 重要行为说明



* **WSL 空闲约 60s 自动关闭 VM**（`vmIdleTimeout` 默认 60000ms）：一次性命令结束并空闲后，VM 与容器一起停止。
  若"长时间等待"期间没有任何 WSL 进程，等待结束时容器其实已被关停、Windows 连 `localhost` 被拒（`wsl ... uptime` 显示 `up 0 min`）。
  **开发时保持 VM**：后台运行 `wsl -d Ubuntu-24.04 -u root -- sleep infinity`；或调大 `%UserProfile%\.wslconfig` 的 `vmIdleTimeout`。
  等容器健康统一用 `deploy/wsl/wait_ready.sh`（在单条命令内轮询，不被空闲回收打断）；冷启动瞬间立即 curl 会得到 000。

* **Windows 侧访问**：WSL2 默认端口转发，Windows 浏览器直接用 `localhost` 即可。

* **鉴权姿态（重要，交付前请看）**：本目录的 compose 以**单机演示姿态**运行——PowerContext 的 `access_mode` 实测为 `disabled`（`specweaver doctor` 会把这一项打印出来），seekdb 用 `root` 空密码，SpecWeaver 的 `/mcp` 与 `GET /metrics` 自身不带鉴权。若要放到共享机器或局域网：
  * PowerContext 侧启用官方鉴权：`POWERCONTEXT_SERVER_ACCESS_MODE=enforced` + `POWERCONTEXT_SERVER_AUTH_TOKEN=<强随机>`（官方 docker/README 与 configure-server-environment 文档口径），SpecWeaver 侧在 `specweaver/.env` 填 `POWERCONTEXT__TOKEN=<同一 token>`（`PowerContextClient` 会带 `Authorization: Bearer`）；
  * seekdb 侧设置 `ROOT_PASSWORD` 并同步 `SEEKDB__PASSWORD`；
  * SpecWeaver 的 HTTP 服务默认只绑 `127.0.0.1`（`SERVER__HOST`），对外暴露请置于反代之后并对 `/metrics` 做访问控制（指标含项目名与构件规模，属敏感信息）。

* **代理**：脚本动态读取宿主 IP（`ip route` default via），代理端口固定 10090；daemon 与构建均已配置。



***

## 6. 停止与清理



```
docker compose -f docker-compose.yml -f docker-compose.run.yml down      # 删容器，保留数据

docker compose -f docker-compose.yml -f docker-compose.run.yml down -v   # 连数据卷删除（谨慎）

wsl --shutdown
```



***

## 7. 实测验证证据



* seekdb：`SELECT version()` → `5.7.25-OceanBase seekdb-v1.4.0.0`；`SHOW DATABASES` 正常；

  建库 / 建表 / 插入 2 行 / 计数 `n=2`/ 删除，全部成功。

* powercontext：两容器 `healthy`；openapi title **PowerContext API 1.1.0、97 路径**；

  `/health/ready` 200；`/mcp` 307→`/mcp/`，返回标准 JSON-RPC 会话响应（MCP 在线）。



***

## 8. 备选：Docker Desktop（受支持的 Windows 版本）



```
Copy-Item .env.example .env

docker compose up -d
```

PowerContext 无官方镜像（Docker Hub 404），需叠加 `docker-compose.build.yml` 本地构建 master。