#!/usr/bin/env bash
# 构建 powercontext 并启动 seekdb + powercontext（WSL Docker Engine）
HOSTIP=$(ip route show default | awk '/default/{print $3; exit}')
PX="http://${HOSTIP}:10090"
# 同时导出大小写：daemon 拉基础镜像用 daemon 代理；BuildKit 的 RUN(uv sync) 用本 shell 代理
export http_proxy=$PX https_proxy=$PX HTTP_PROXY=$PX HTTPS_PROXY=$PX
export no_proxy="localhost,127.0.0.1,::1" NO_PROXY="localhost,127.0.0.1,::1"

cd /mnt/e/2026ob_projects/SDD/specweaver/deploy || exit 1
echo "== up --build =="
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
echo "== ps =="
docker compose ps
echo "UP_DONE"
