#!/usr/bin/env bash
# ============================================================================
# SpecWeaver · 在 WSL2 Ubuntu 内安装 Docker Engine（以 root 运行）
# 自动：动态宿主代理 -> apt 仓库 -> 安装 -> docker 拉镜像代理(自适应) -> 验证
# ============================================================================
PROXY_PORT=10090
HOSTIP=$(ip route show default | awk '/default/{print $3; exit}')
echo "[1/8] 宿主IP: $HOSTIP"
export http_proxy="http://${HOSTIP}:${PROXY_PORT}"
export https_proxy="http://${HOSTIP}:${PROXY_PORT}"
export no_proxy="localhost,127.0.0.1,::1"
export DEBIAN_FRONTEND=noninteractive

echo "[2/8] 验证代理连通 ..."
curl -sI -m 10 https://www.google.com | head -1 || { echo "代理不通，终止"; exit 1; }

echo "[3/8] 安装依赖并添加 Docker 官方仓库 ..."
apt-get update -y
apt-get install -y ca-certificates curl gnupg lsb-release
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list

echo "[4/8] 安装 Docker Engine + 插件 ..."
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "[5/8] 配置 docker daemon 拉镜像代理（宿主IP自适应）..."
# 5a. 动态生成代理 EnvironmentFile 的脚本
cat > /usr/local/sbin/sw-docker-proxy <<'EOS'
#!/usr/bin/env bash
H=$(ip route show default | awk '/default/{print $3; exit}')
[ -z "$H" ] && exit 0
mkdir -p /etc/docker
cat > /etc/docker/proxy.env <<EOF
HTTP_PROXY=http://${H}:10090
HTTPS_PROXY=http://${H}:10090
NO_PROXY=localhost,127.0.0.1,::1
http_proxy=http://${H}:10090
https_proxy=http://${H}:10090
no_proxy=localhost,127.0.0.1,::1
EOF
EOS
chmod +x /usr/local/sbin/sw-docker-proxy
# 5b. oneshot：docker 启动前刷新代理
cat > /etc/systemd/system/sw-docker-proxy.service <<'EOS'
[Unit]
Before=docker.service
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/sw-docker-proxy
[Install]
WantedBy=multi-user.target
EOS
mkdir -p /etc/systemd/system/docker.service.d
cat > /etc/systemd/system/docker.service.d/http-proxy.conf <<'EOS'
[Service]
EnvironmentFile=/etc/docker/proxy.env
EOS
/usr/local/sbin/sw-docker-proxy
systemctl daemon-reload
systemctl enable sw-docker-proxy.service >/dev/null 2>&1

echo "[6/8] 启动 docker ..."
systemctl enable docker >/dev/null 2>&1
systemctl restart docker
sleep 3

echo "[7/8] 用户 shell 代理 + 将 simpur 加入 docker 组 ..."
cat > /etc/profile.d/specweaver-proxy.sh <<'EOS'
_h=$(ip route show default 2>/dev/null | awk '/default/{print $3; exit}')
if [ -n "$_h" ]; then
  export http_proxy="http://${_h}:10090" https_proxy="http://${_h}:10090" no_proxy="localhost,127.0.0.1,::1"
fi
EOS
usermod -aG docker simpur 2>/dev/null || true

echo "[8/8] 验证 ..."
docker info 2>/dev/null | grep -E "Server Version|Storage Driver"
docker compose version
echo "-- 拉取 hello-world 验证全链路（含代理）--"
docker run --rm hello-world 2>&1 | grep -E "Hello|working" | head -2
echo "ALL_DONE"
