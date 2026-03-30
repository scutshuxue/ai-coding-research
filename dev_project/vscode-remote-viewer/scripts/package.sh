#!/usr/bin/env bash
# Remote Browser Viewer 打包脚本
# 用法: ./scripts/package.sh [--install]
#   --install  打包后自动安装到当前 VSCode

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

echo "=== 1. 安装依赖 ==="
npm install --silent

echo "=== 2. 编译 TypeScript ==="
npm run build

echo "=== 3. 运行测试 ==="
npm test

echo "=== 4. 打包 VSIX ==="
npx @vscode/vsce package --baseContentUrl . --baseImagesUrl .

# 找到生成的 vsix 文件
VSIX_FILE=$(ls -t "$PROJECT_DIR"/*.vsix 2>/dev/null | head -1)
if [ -z "$VSIX_FILE" ]; then
    echo "错误: 未找到 .vsix 文件"
    exit 1
fi

echo ""
echo "打包成功: $VSIX_FILE"
echo "文件大小: $(du -h "$VSIX_FILE" | cut -f1)"

# 可选: 自动安装
if [ "${1:-}" = "--install" ]; then
    echo ""
    echo "=== 5. 安装插件 ==="
    code --install-extension "$VSIX_FILE" --force
    echo "安装完成，重载 VSCode 窗口生效"
fi
