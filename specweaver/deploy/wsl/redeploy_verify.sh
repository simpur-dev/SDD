#!/usr/bin/env bash
cd /mnt/e/2026ob_projects/SDD/specweaver/deploy || exit 1
echo "== 用新镜像强制重建 =="
docker compose -f docker-compose.yml -f docker-compose.run.yml up -d --force-recreate
echo "== 完整验证（含等待）=="
bash /mnt/e/2026ob_projects/SDD/specweaver/deploy/wsl/verify2.sh
echo REDEPLOY_DONE
