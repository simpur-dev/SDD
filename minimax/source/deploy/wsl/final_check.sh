#!/usr/bin/env bash
echo "等待容器就绪..."
for i in $(seq 1 40); do
  pc=$(curl -s -o /dev/null -w '%{http_code}' -m 3 http://localhost:8000/health/ready)
  [ "$pc" = "200" ] && { echo "ready"; break; }
  sleep 3
done
echo "== openapi 原语分组 =="
curl -s -m 5 http://localhost:8000/openapi.json -o /tmp/o.json
python3 - <<'PY'
import json
d=json.load(open('/tmp/o.json',encoding='utf-8'))
paths=list(d.get("paths",{}).keys())
print("title:", d.get("info",{}).get("title"), d.get("info",{}).get("version"), "| 路径数:", len(paths))
for g in ["sources","memories","topics","handoffs","skills","contexts","profiles","scopes","experiences","agents"]:
    hits=[p for p in paths if g in p]
    print(f"{g:12} {len(hits):2}  e.g. {hits[:3]}")
PY
echo "== /mcp 跟随重定向 =="
curl -sL -o /dev/null -w 'final=%{http_code} effective=%{url_effective}\n' -m 8 -H 'Accept: application/json, text/event-stream' http://localhost:8000/mcp
echo "== /mcp/ SSE 响应（前若干行）=="
curl -s -N -m 6 -D - -o /tmp/sse.body -H 'Accept: application/json, text/event-stream' http://localhost:8000/mcp/ | head -8
echo "-- body --"; head -5 /tmp/sse.body
echo FINAL_DONE
