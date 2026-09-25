#!/usr/bin/env bash
cd /mnt/e/2026ob_projects/SDD/specweaver/deploy || exit 1
echo "== up -d（离线，使用本地镜像）=="
docker compose -f docker-compose.yml -f docker-compose.run.yml up -d
echo "等待就绪（seekdb 冷启动可能较慢）..."
for i in $(seq 1 60); do
  pc=$(curl -s -o /dev/null -w '%{http_code}' -m 3 http://localhost:8000/health/ready)
  (echo > /dev/tcp/127.0.0.1/2881) 2>/dev/null && sd=up || sd=down
  echo "t=$((i*8))s powercontext=$pc seekdb_sql=$sd"
  [ "$pc" = "200" ] && [ "$sd" = "up" ] && break
  sleep 8
done
docker compose ps
echo "-- powercontext /health/ready --"; curl -s -m5 http://localhost:8000/health/ready; echo
echo START2_DONE
