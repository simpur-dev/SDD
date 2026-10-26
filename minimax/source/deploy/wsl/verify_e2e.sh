#!/usr/bin/env bash
echo "== seekdb 容器内 SQL 客户端 =="
CLI=$(docker exec sw-seekdb bash -lc "which obclient 2>/dev/null || which mysql 2>/dev/null" | tr -d '\r' | head -1)
echo "client=$CLI"
echo "== version / databases =="
docker exec sw-seekdb $CLI -h127.0.0.1 -P2881 -uroot -e "SELECT version(); SHOW DATABASES;" 2>&1 | head -20
echo "== 建/查/删 测试表 =="
docker exec sw-seekdb $CLI -h127.0.0.1 -P2881 -uroot -e "CREATE DATABASE IF NOT EXISTS sw_smoke; USE sw_smoke; CREATE TABLE t(id INT); INSERT INTO t VALUES (1),(2); SELECT COUNT(*) FROM t; DROP DATABASE sw_smoke;" 2>&1 | head
echo "== powercontext 端点 =="
for p in /api/v1/system/health /docs /mcp /openapi.json /api/v1/system/info; do
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 5 "http://localhost:8000$p")
  echo "$p -> $code"
done
echo E2E_DONE
