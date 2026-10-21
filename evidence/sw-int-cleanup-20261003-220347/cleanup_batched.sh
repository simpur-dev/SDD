#!/bin/sh
# Batched cleanup of the leaked integration-test databases (sw_int_<8hex>).
# The unbatched drop storm took down the whole WSL VM, so: small batches,
# a health gate between batches, and stop on first failure.
set -u
MYSQL="docker exec sw-seekdb mysql -h127.0.0.1 -P2881 -uroot"
PATTERN='^sw_int_[0-9a-f]{8}$'

remaining() {
  $MYSQL -N -e "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name REGEXP '$PATTERN'"
}

wait_server() {
  i=0
  while [ $i -lt 30 ]; do
    $MYSQL -N -e "SELECT 1" >/dev/null 2>&1 && return 0
    i=$((i + 1))
    sleep 2
  done
  return 1
}

wait_server || { echo "FATAL: server not answering"; exit 1; }
echo "start remaining=$(remaining)"
batch=0
while :; do
  n=$(remaining)
  [ "$n" -eq 0 ] && break
  $MYSQL -N -e "SELECT CONCAT('DROP DATABASE IF EXISTS ', schema_name, ';') FROM information_schema.schemata WHERE schema_name REGEXP '$PATTERN' ORDER BY schema_name LIMIT 10" > /tmp/sw_drop_batch.sql
  docker exec -i sw-seekdb mysql -h127.0.0.1 -P2881 -uroot < /tmp/sw_drop_batch.sql || {
    echo "FAIL at batch $batch, remaining=$n"
    exit 1
  }
  batch=$((batch + 1))
  sleep 2
  wait_server || { echo "server lost after batch $batch, remaining=$(remaining)"; exit 1; }
  echo "batch $batch done, remaining=$(remaining)"
done
echo "CLEAN: remaining=0"
