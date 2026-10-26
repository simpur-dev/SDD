#!/usr/bin/env bash
HOSTIP=$(ip route show default | awk '/default/{print $3; exit}')
PX="http://${HOSTIP}:10090"
export http_proxy=$PX https_proxy=$PX HTTP_PROXY=$PX HTTPS_PROXY=$PX
cd /mnt/e/2026ob_projects/SDD/specweaver/deploy || exit 1
echo "== build powercontext =="
docker compose -f docker-compose.yml -f docker-compose.build.yml build powercontext 2>&1 | tail -50
echo "BUILD_EXIT=${PIPESTATUS[0]}"
