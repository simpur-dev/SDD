#!/usr/bin/env bash
# WSL 网络 / 宿主代理连通性诊断
set +e

echo "== default route =="
ip route show default

echo "== resolv.conf =="
cat /etc/resolv.conf 2>/dev/null

HOSTIP=$(ip route show default | awk '/default/ {print $3}' | head -1)
echo "HOSTIP(default via)=$HOSTIP"

echo "== 测试候选宿主代理 127.0.0.1:10090 / host:10090 =="
CANDIDATES="$HOSTIP 10.255.255.254"
for ip in $CANDIDATES; do
  [ -z "$ip" ] && continue
  echo "-- proxy http://$ip:10090 -> google --"
  out=$(curl -x "http://$ip:10090" -sI -m 8 https://www.google.com 2>&1 | head -1)
  echo "   $out"
done

echo "== 直连(无代理)测试 =="
curl -sI -m 8 https://www.google.com 2>&1 | head -1

echo "== TCP 端口连通(nc/bash) =="
for ip in $HOSTIP 10.255.255.254; do
  [ -z "$ip" ] && continue
  timeout 5 bash -c "echo > /dev/tcp/$ip/10090" 2>/dev/null && echo "  $ip:10090 TCP OPEN" || echo "  $ip:10090 TCP CLOSED/FILTERED"
done
echo DONE
