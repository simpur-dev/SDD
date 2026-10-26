#!/usr/bin/env bash
echo "等待 openapi 可用..."
for i in $(seq 1 40); do
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 3 http://localhost:8000/openapi.json)
  [ "$code" = "200" ] && break
  sleep 3
done
curl -s -m 5 http://localhost:8000/openapi.json -o /tmp/openapi.json
echo "== 全部路径 =="
python3 - <<'PY'
import json
d=json.load(open('/tmp/openapi.json',encoding='utf-8'))
info=d.get("info",{})
print("title:", info.get("title"), "| version:", info.get("version"))
for p in sorted(d.get("paths",{}).keys()):
    methods=",".join(m.upper() for m in d["paths"][p] if m in ("get","post","put","delete","patch"))
    print(f"{methods:22} {p}")
PY
echo INSPECT5_DONE
