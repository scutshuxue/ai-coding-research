#!/bin/bash
# WSS 隧道方案 — Linux 端代理配置脚本
# 用法: source setup_linux.sh [proxy_port]

PROXY_PORT="${1:-18080}"
PROXY_URL="http://127.0.0.1:${PROXY_PORT}"

echo "=== WSS 隧道代理配置 ==="
echo "代理地址: $PROXY_URL"
echo ""

# 1. 检查代理是否可达
echo -n "检查 Local Proxy... "
if nc -z 127.0.0.1 "$PROXY_PORT" -w 3 2>/dev/null; then
    echo "✓ 端口 $PROXY_PORT 可达"
else
    echo "✗ 端口 $PROXY_PORT 不可达，请先启动 tunnel_server.py"
    return 1 2>/dev/null || exit 1
fi

# 2. 设置环境变量
export http_proxy="$PROXY_URL"
export https_proxy="$PROXY_URL"
export HTTP_PROXY="$PROXY_URL"
export HTTPS_PROXY="$PROXY_URL"
export no_proxy="localhost,127.0.0.1,::1"
export NO_PROXY="$no_proxy"

echo ""
echo "已设置环境变量:"
echo "  http_proxy=$http_proxy"
echo "  https_proxy=$https_proxy"
echo "  no_proxy=$no_proxy"
echo ""
echo "验证: curl http://httpbin.org/ip"
echo "取消: unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY"
