#!/usr/bin/env bash
# Playwright MCP + Chromium 部署验证脚本
# 用法: bash scripts/verify.sh

set -uo pipefail

CHROMIUM_REVISION="1205"
CHROMIUM_DIR="$HOME/.cache/ms-playwright/chromium-$CHROMIUM_REVISION"
CHROME_BIN="$CHROMIUM_DIR/chrome-linux64/chrome"

PASS=0
FAIL=0
WARN=0

pass() { echo -e "  \033[32m✓\033[0m $*"; PASS=$((PASS+1)); }
fail() { echo -e "  \033[31m✗\033[0m $*"; FAIL=$((FAIL+1)); }
warn() { echo -e "  \033[33m⚠\033[0m $*"; WARN=$((WARN+1)); }

echo "=== Playwright MCP + Chromium 部署验证 ==="
echo ""

# ---- 1. Node.js ----
echo "[1/6] Node.js"
if command -v node &>/dev/null; then
    NODE_VER=$(node -v)
    NODE_MAJOR=$(echo "$NODE_VER" | sed 's/v//' | cut -d. -f1)
    if [ "$NODE_MAJOR" -ge 18 ]; then
        pass "Node.js $NODE_VER"
    else
        fail "Node.js $NODE_VER（需要 >= 18）"
    fi
else
    fail "Node.js 未安装"
fi

# ---- 2. Chromium 文件 ----
echo "[2/6] Chromium 二进制"
if [ -x "$CHROME_BIN" ]; then
    pass "chrome 可执行文件存在: $CHROME_BIN"
else
    fail "chrome 不存在或不可执行: $CHROME_BIN"
fi

# ---- 3. Chromium 启动测试 ----
echo "[3/6] Chromium 启动（headless）"
if [ -x "$CHROME_BIN" ]; then
    # 尝试启动 headless chrome 并获取版本
    CHROME_OUTPUT=$("$CHROME_BIN" --headless --no-sandbox --disable-gpu --dump-dom about:blank 2>&1) && \
        pass "Chromium headless 启动成功" || {
        fail "Chromium 启动失败"
        echo "    输出: $CHROME_OUTPUT" | head -5

        # 检查缺失的共享库
        echo ""
        echo "    检查缺失的共享库..."
        MISSING_LIBS=$(ldd "$CHROME_BIN" 2>/dev/null | grep "not found" || true)
        if [ -n "$MISSING_LIBS" ]; then
            echo "    缺失的库:"
            echo "$MISSING_LIBS" | sed 's/^/      /'
            echo ""
            echo "    请安装对应的系统包，参见 docs/deploy-guide.md"
        else
            echo "    共享库完整，问题可能是其他原因"
        fi
    }
else
    fail "跳过（chrome 不存在）"
fi

# ---- 4. @playwright/mcp ----
echo "[4/6] @playwright/mcp"
if npm list -g @playwright/mcp &>/dev/null; then
    MCP_VER=$(npm list -g @playwright/mcp 2>/dev/null | grep "@playwright/mcp" | sed 's/.*@playwright\/mcp@//')
    pass "@playwright/mcp@$MCP_VER"
else
    fail "@playwright/mcp 未全局安装"
fi

# ---- 5. CDP 端口测试 ----
echo "[5/6] CDP 端口（启动临时 Chrome 测试）"
if [ -x "$CHROME_BIN" ]; then
    # 在随机端口启动 headless chrome
    TEST_PORT=19222
    "$CHROME_BIN" --headless --no-sandbox --disable-gpu \
        --remote-debugging-port=$TEST_PORT \
        --remote-debugging-address=127.0.0.1 \
        about:blank &>/dev/null &
    CHROME_PID=$!

    # 等待启动
    sleep 2

    if kill -0 "$CHROME_PID" 2>/dev/null; then
        # 测试 CDP 端点
        CDP_RESPONSE=$(curl -s --max-time 5 "http://127.0.0.1:$TEST_PORT/json/version" 2>/dev/null || true)
        if echo "$CDP_RESPONSE" | grep -q "webSocketDebuggerUrl"; then
            pass "CDP 端点可达 (port $TEST_PORT)"
            BROWSER_VER=$(echo "$CDP_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('Browser','unknown'))" 2>/dev/null || echo "unknown")
            pass "浏览器版本: $BROWSER_VER"
        else
            fail "CDP 端点不可达"
        fi

        # 清理
        kill "$CHROME_PID" 2>/dev/null
        wait "$CHROME_PID" 2>/dev/null || true
    else
        fail "Chrome 进程启动后立即退出"
    fi
else
    fail "跳过（chrome 不存在）"
fi

# ---- 6. VSCode 插件 ----
echo "[6/6] VSCode 插件"
if command -v code &>/dev/null; then
    if code --list-extensions 2>/dev/null | grep -qi "remote-browser-viewer"; then
        pass "Remote Browser Viewer 已安装"
    else
        warn "Remote Browser Viewer 未安装（可后续安装）"
    fi
else
    warn "code 命令不可用（在 VSCode Remote SSH 终端中重试）"
fi

# ---- 汇总 ----
echo ""
echo "========================================="
echo "  验证结果: $PASS 通过, $FAIL 失败, $WARN 警告"
echo "========================================="

if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "存在失败项，请根据提示修复后重新验证。"
    echo "详细排查指南: docs/deploy-guide.md"
    exit 1
fi
