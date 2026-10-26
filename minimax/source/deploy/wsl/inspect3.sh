#!/usr/bin/env bash
echo "== ps =="
docker ps --format '{{.Names}} | {{.Image}} | {{.Status}}'
echo "== 容器使用的镜像ID vs 最新构建 =="
docker inspect -f 'container image: {{.Image}}' sw-powercontext
docker images --no-trunc powercontext-server:local --format 'built image: {{.ID}}'
echo "== openapi 实际注册路径 =="
curl -s -m 5 http://localhost:8000/openapi.json | python3 -c "import sys,json; d=json.load(sys.stdin); [print(p) for p in sorted(d.get('paths',{}).keys())]" 2>&1 | head -80
echo "== 启动日志（尾40行）=="
docker logs --tail 40 sw-powercontext 2>&1
echo INSPECT3_DONE
