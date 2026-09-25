#!/usr/bin/env bash
set +e
echo "== WSL uptime =="
uptime
echo "== free / mem =="
free -h | head -3
echo "== docker server =="
docker version --format 'server {{.Server.Version}}'
echo "== container inspect =="
for c in sw-seekdb sw-powercontext; do
  echo "--- $c ---"
  docker inspect "$c" --format 'RestartCount={{.RestartCount}} Status={{.State.Status}} ExitCode={{.State.ExitCode}} OOMKilled={{.State.OOMKilled}} StartedAt={{.State.StartedAt}} Error={{.State.Error}}'
done
echo "== seekdb logs tail =="
docker logs --tail 25 sw-seekdb 2>&1
echo "== powercontext logs tail =="
docker logs --tail 25 sw-powercontext 2>&1
