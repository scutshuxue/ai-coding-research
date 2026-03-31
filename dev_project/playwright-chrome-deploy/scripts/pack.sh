#!/usr/bin/env bash
# 打包脚本：将所有离线部署文件打成一个 zip
# 在 macOS 上执行
# 用法: bash scripts/pack.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PACKAGES_DIR="$PROJECT_DIR/packages"
VSIX_SOURCE="$PROJECT_DIR/../vscode-remote-viewer"

info()  { echo -e "\033[32m[INFO]\033[0m  $*"; }
warn()  { echo -e "\033[33m[WARN]\033[0m  $*"; }
error() { echo -e "\033[31m[ERROR]\033[0m $*"; exit 1; }

# ============================================================
# 1. 构建 VSCode 插件（如果 .vsix 不存在）
# ============================================================
info "=== 1/3: 准备 VSCode 插件 ==="

VSIX_FILE=$(ls "$PACKAGES_DIR"/remote-browser-viewer-*.vsix 2>/dev/null | head -1 || true)

if [ -n "$VSIX_FILE" ]; then
    info "已有 .vsix: $(basename "$VSIX_FILE")，跳过构建"
else
    BUILT_VSIX=$(ls "$VSIX_SOURCE"/remote-browser-viewer-*.vsix 2>/dev/null | head -1 || true)
    if [ -n "$BUILT_VSIX" ]; then
        cp "$BUILT_VSIX" "$PACKAGES_DIR/"
        info "拷贝已构建的 .vsix: $(basename "$BUILT_VSIX")"
    else
        info "未找到 .vsix，开始构建..."
        cd "$VSIX_SOURCE"
        npm install --silent
        npm run package
        BUILT_VSIX=$(ls "$VSIX_SOURCE"/remote-browser-viewer-*.vsix | head -1)
        cp "$BUILT_VSIX" "$PACKAGES_DIR/"
        info "构建完成: $(basename "$BUILT_VSIX")"
        cd "$PROJECT_DIR"
    fi
fi

# ============================================================
# 2. 检查离线包完整性
# ============================================================
info "=== 2/3: 检查离线包 ==="

MISSING=0
for f in chrome-linux64.zip chrome-headless-shell-linux64.zip; do
    if [ -f "$PACKAGES_DIR/$f" ]; then
        info "$f ✓ ($(du -h "$PACKAGES_DIR/$f" | cut -f1))"
    else
        warn "缺少: $f"
        MISSING=$((MISSING+1))
    fi
done

VSIX_FILE=$(ls "$PACKAGES_DIR"/remote-browser-viewer-*.vsix 2>/dev/null | head -1 || true)
if [ -n "$VSIX_FILE" ]; then
    info "$(basename "$VSIX_FILE") ✓ ($(du -h "$VSIX_FILE" | cut -f1))"
else
    warn "缺少 .vsix"
    MISSING=$((MISSING+1))
fi

if [ "$MISSING" -gt 0 ]; then
    error "缺少 $MISSING 个文件，请先下载后放入 packages/ 目录"
fi

# ============================================================
# 3. 打包
# ============================================================
info "=== 3/3: 打包 ==="

TIMESTAMP=$(date +%Y%m%d)
OUTPUT_NAME="playwright-chrome-deploy-${TIMESTAMP}.zip"
OUTPUT_PATH="$PROJECT_DIR/$OUTPUT_NAME"

cd "$PROJECT_DIR/.."
zip -r "$OUTPUT_PATH" \
    playwright-chrome-deploy/README.md \
    playwright-chrome-deploy/packages/chrome-linux64.zip \
    playwright-chrome-deploy/packages/chrome-headless-shell-linux64.zip \
    playwright-chrome-deploy/packages/remote-browser-viewer-*.vsix \
    playwright-chrome-deploy/scripts/deploy.sh \
    playwright-chrome-deploy/scripts/verify.sh \
    playwright-chrome-deploy/scripts/test-server.py \
    playwright-chrome-deploy/docs/deploy-guide.md

echo ""
info "========================================="
info "  打包完成！"
info "========================================="
info "输出: $OUTPUT_PATH"
info "大小: $(du -h "$OUTPUT_PATH" | cut -f1)"
echo ""
info "传输到 Linux："
info "  scp $OUTPUT_PATH user@linux-server:~/"
info "  ssh user@linux-server 'cd ~ && unzip $OUTPUT_NAME && cd playwright-chrome-deploy && bash scripts/deploy.sh'"
