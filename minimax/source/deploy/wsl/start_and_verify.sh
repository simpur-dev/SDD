#!/usr/bin/env bash
cd /mnt/e/2026ob_projects/SDD/specweaver/deploy || exit 1
echo "== up -d =="
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d
echo "等待服务就绪（seekdb 首次初始化可能 2-6 分钟）..."
pc=000; sd=down
for i in $(seq 1 60); do
  pc=$(curl -s -o /dev/null -w '%{http_code}' -m 3 http://localhost:8000/api/v1/system/health)
  (echo > /dev/tcp/127.0.0.1/2881) 2>/dev/null && sd=up || sd=down
  echo "t=$((i*8))s powercontext=$pc seekdb_sql=$sd"
  [ "$pc" = "200" ] && [ "$sd" = "up" ] && break
  sleep 8
done
echo "== ps =="
docker compose ps
echo "== powercontext /api/v1/system/health =="
curl -s -m 5 http://localhost:8000/api/v1/system/health; echo
echo "START_DONE"
