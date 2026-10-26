#!/usr/bin/env bash
echo "等待容器就绪（含 WSL 冷启动）..."
for i in $(seq 1 70); do
  sh=$(docker inspect -f '{{.State.Health.Status}}' sw-seekdb 2>/dev/null)
  pc=$(curl -s -o /dev/null -w '%{http_code}' -m 3 http://localhost:8000/health/ready)
  echo "t=$((i*5))s seekdb_health=$sh powercontext=$pc"
  [ "$sh" = "healthy" ] && [ "$pc" = "200" ] && break
  sleep 5
done

echo "== seekdb: version / databases =="
docker exec sw-seekdb mysql -h127.0.0.1 -P2881 -uroot -e "SELECT version(); SHOW DATABASES;" 2>&1 | head -20

echo "== seekdb: 建/查/删 冒烟 =="
docker exec sw-seekdb mysql -h127.0.0.1 -P2881 -uroot -e "CREATE DATABASE IF NOT EXISTS sw_smoke; USE sw_smoke; CREATE TABLE t(id INT); INSERT INTO t VALUES (1),(2); SELECT COUNT(*) AS n FROM t; DROP DATABASE sw_smoke;" 2>&1 | head

echo "== powercontext REST 端点 =="
for p in /health/live /health/ready /docs /openapi.json; do
  echo "$p -> $(curl -s -o /dev/null -w '%{http_code}' -m 5 http://localhost:8000$p)"
done

echo "== MCP /mcp（带 SSE Accept；非 404 即端点存在）=="
curl -s -o /dev/null -w 'GET /mcp -> %{http_code}\n' -m 5 -H 'Accept: application/json, text/event-stream' http://localhost:8000/mcp
echo VERIFY2_DONE
