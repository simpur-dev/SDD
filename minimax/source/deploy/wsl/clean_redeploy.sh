#!/usr/bin/env bash
cd /mnt/e/2026ob_projects/SDD/specweaver/deploy || exit 1
echo "== down =="
docker compose -f docker-compose.yml -f docker-compose.run.yml down
echo "== up -d（全本地镜像，离线）=="
docker compose -f docker-compose.yml -f docker-compose.run.yml up -d
echo "等待 powercontext /health/ready ..."
for i in $(seq 1 60); do
  pc=$(curl -s -o /dev/null -w '%{http_code}' -m 3 http://localhost:8000/health/ready)
  sh=$(docker inspect -f '{{.State.Health.Status}}' sw-seekdb 2>/dev/null)
  echo "t=$((i*5))s seekdb=$sh powercontext=$pc"
  [ "$pc" = "200" ] && [ "$sh" = "healthy" ] && break
  sleep 5
done
echo "== ps =="
docker ps --format '{{.Names}} | {{.Image}} | {{.Status}}'
echo "== powercontext 容器实际镜像 =="
docker inspect -f '{{.Image}}' sw-powercontext
echo "== openapi title 与关键路径 =="
curl -s -m 5 http://localhost:8000/openapi.json -o /tmp/o.json
python3 - <<'PY'
import json
d=json.load(open('/tmp/o.json',encoding='utf-8'))
print("title:", d.get("info",{}).get("title"), d.get("info",{}).get("version"))
paths=d.get("paths",{})
for key in ["/health/live","/health/ready","/mcp"]:
    print(key, "->", "EXISTS" if key in paths else "MISSING")
print("总路径数:", len(paths))
PY
echo "== MCP GET（SSE Accept）=="
curl -s -o /dev/null -w '%{http_code}\n' -m 5 -H 'Accept: application/json, text/event-stream' http://localhost:8000/mcp
echo CLEAN_REDEPLOY_DONE
