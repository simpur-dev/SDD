#!/usr/bin/env bash
set +e
cd /mnt/e/2026ob_projects/SDD/specweaver/deploy || exit 1
docker compose -f docker-compose.yml -f docker-compose.run.yml up -d

wait_for() {
  name=$1; n=$2
  for i in $(seq 1 "$n"); do
    st=$(docker inspect -f '{{.State.Health.Status}}' "$name" 2>/dev/null)
    echo "[$i] $name health=$st"
    if [ "$st" = "healthy" ]; then return 0; fi
    sleep 5
  done
  return 1
}

wait_for sw-powercontext 30
wait_for sw-seekdb 40
echo "== final =="
docker ps --format '{{.Names}} | {{.Status}}'
