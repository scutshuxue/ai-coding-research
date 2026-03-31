#!/bin/bash
# Linux 端代理配置脚本
# 用法: source linux-setup.sh [proxy_port] [user:pass]

PROXY_PORT="${1:-18080}"
PROXY_AUTH="${2:-proxy:proxy123}"
PROXY_URL="http://${PROXY_AUTH}@127.0.0.1:${PROXY_PORT}"

echo "=== 代理配置 ==="
echo "代理地址: $PROXY_URL"
echo ""

# 1. 检查隧道是否通
echo -n "检查隧道连通性... "
if nc -z 127.0.0.1 "$PROXY_PORT" -w 3 2>/dev/null; then
    echo "✓ 端口 $PROXY_PORT 可达"
else
    echo "✗ 端口 $PROXY_PORT 不可达，请先建立 SSH 反向隧道"
    return 1 2>/dev/null || exit 1
fi

# 2. 设置环境变量
export http_proxy="$PROXY_URL"
export https_proxy="$PROXY_URL"
export HTTP_PROXY="$PROXY_URL"
export HTTPS_PROXY="$PROXY_URL"

# 本地地址不走代理
export no_proxy="localhost,127.0.0.1,::1"
export NO_PROXY="$no_proxy"

echo ""
echo "已设置环境变量:"
echo "  http_proxy=$http_proxy"
echo "  https_proxy=$https_proxy"
echo "  no_proxy=$no_proxy"
echo ""
echo "验证: curl -I http://httpbin.org/ip"
echo "取消: unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY"
