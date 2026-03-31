#!/usr/bin/env bash
# Playwright MCP + Chromium 离线部署脚本
# 在 Linux 服务器上执行
# 用法: bash scripts/deploy.sh

set -euo pipefail

# ============================================================
# 配置
# ============================================================
CHROMIUM_REVISION="1205"
PLAYWRIGHT_MCP_VERSION="0.0.55"
PLAYWRIGHT_BROWSERS_DIR="$HOME/.cache/ms-playwright"
CHROMIUM_DIR="$PLAYWRIGHT_BROWSERS_DIR/chromium-$CHROMIUM_REVISION"
HEADLESS_SHELL_DIR="$PLAYWRIGHT_BROWSERS_DIR/chromium-headless-shell-$CHROMIUM_REVISION"
CHROME_BIN="$CHROMIUM_DIR/chrome-linux64/chrome"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PACKAGES_DIR="$PROJECT_DIR/packages"

# ============================================================
# 辅助函数
# ============================================================
info()  { echo -e "\033[32m[INFO]\033[0m  $*"; }
warn()  { echo -e "\033[33m[WARN]\033[0m  $*"; }
error() { echo -e "\033[31m[ERROR]\033[0m $*"; exit 1; }

check_file() {
    if [ ! -f "$1" ]; then
        error "缺少文件: $1\n请参考 README.md 下载后放入 packages/ 目录"
    fi
}

# ============================================================
# 步骤 1: 检查前置条件
# ============================================================
info "=== 步骤 1/2: 检查前置条件 ==="

# 检查 Node.js
if ! command -v node &>/dev/null; then
    error "未找到 Node.js，请先安装 Node.js >= 18"
fi
NODE_VERSION=$(node -v | sed 's/v//' | cut -d. -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    error "Node.js 版本过低: $(node -v)，需要 >= 18"
fi
info "Node.js: $(node -v) ✓"

# 检查 npm
if ! command -v npm &>/dev/null; then
    error "未找到 npm"
fi
info "npm: $(npm -v) ✓"

# 检查 npm registry（提醒配置内部 mirror）
NPM_REGISTRY=$(npm config get registry 2>/dev/null || echo "unknown")
if echo "$NPM_REGISTRY" | grep -q "registry.npmjs.org"; then
    warn "npm registry 指向官方源: $NPM_REGISTRY"
    warn "离线环境需配置内部 mirror: npm config set registry <内部mirror地址>"
else
    info "npm registry: $NPM_REGISTRY ✓"
fi

# 检查离线包
check_file "$PACKAGES_DIR/chrome-linux64.zip"
info "chrome-linux64.zip ✓ ($(du -h "$PACKAGES_DIR/chrome-linux64.zip" | cut -f1))"

check_file "$PACKAGES_DIR/chrome-headless-shell-linux64.zip"
info "chrome-headless-shell-linux64.zip ✓ ($(du -h "$PACKAGES_DIR/chrome-headless-shell-linux64.zip" | cut -f1))"

# ============================================================
# 步骤 2: 部署 Chromium
# ============================================================
info "=== 步骤 2/2: 部署 Chromium (revision $CHROMIUM_REVISION) ==="

if [ -d "$CHROMIUM_DIR/chrome-linux64" ] && [ -x "$CHROME_BIN" ]; then
    warn "Chromium 已存在: $CHROMIUM_DIR，跳过"
else
    mkdir -p "$CHROMIUM_DIR"
    info "解压 chrome-linux64.zip → $CHROMIUM_DIR/"
    unzip -q "$PACKAGES_DIR/chrome-linux64.zip" -d "$CHROMIUM_DIR/"

    if [ ! -f "$CHROME_BIN" ]; then
        error "解压后未找到 chrome-linux64/chrome，zip 包结构可能不正确"
    fi

    chmod +x "$CHROME_BIN"
    info "Chromium 部署完成 ✓"
    info "路径: $CHROME_BIN"
fi

# Headless Shell
if [ -d "$HEADLESS_SHELL_DIR/chrome-headless-shell-linux64" ] && [ -x "$HEADLESS_SHELL_DIR/chrome-headless-shell-linux64/chrome-headless-shell" ]; then
    warn "Chromium Headless Shell 已存在: $HEADLESS_SHELL_DIR，跳过"
else
    mkdir -p "$HEADLESS_SHELL_DIR"
    info "解压 chrome-headless-shell-linux64.zip → $HEADLESS_SHELL_DIR/"
    unzip -q "$PACKAGES_DIR/chrome-headless-shell-linux64.zip" -d "$HEADLESS_SHELL_DIR/"

    if [ ! -f "$HEADLESS_SHELL_DIR/chrome-headless-shell-linux64/chrome-headless-shell" ]; then
        error "解压后未找到 chrome-headless-shell-linux64/chrome-headless-shell，zip 包结构可能不正确"
    fi

    chmod +x "$HEADLESS_SHELL_DIR/chrome-headless-shell-linux64/chrome-headless-shell"
    info "Chromium Headless Shell 部署完成 ✓"
fi

# ============================================================
# 完成
# ============================================================
echo ""
info "========================================="
info "  Chromium 部署完成！"
info "========================================="
echo ""
info "Chromium: $CHROME_BIN"
echo ""
info "后续步骤："
info "  1. 验证: bash scripts/verify.sh"
info ""
info "  2. 安装 @playwright/mcp:"
info "     PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm install -g @playwright/mcp@$PLAYWRIGHT_MCP_VERSION"
info ""
info "  3. 配置 Claude Code MCP（全局生效）:"
info "     claude mcp add playwright --scope user \\"
info "       -e DISPLAY=\"\" \\"
info "       -e PLAYWRIGHT_BROWSERS_PATH=$PLAYWRIGHT_BROWSERS_DIR \\"
info "       -- npx @playwright/mcp@$PLAYWRIGHT_MCP_VERSION --headless --no-sandbox --caps devtools \\"
info "       --ignore-https-errors \\"
info "       --executable-path $CHROME_BIN"
info ""
info "  4. 验证 MCP: claude mcp list"
info ""
info "  5. 安装 VSCode 插件: code --install-extension packages/remote-browser-viewer-*.vsix"
info ""
info "  6. 功能验证: python3 scripts/test-server.py"
info "     然后在 Claude Code 中: 用 playwright 打开 http://localhost:8765"
