# Playwright MCP + Chromium 离线部署包

在无外网的 Linux 服务器上部署 Claude Code 的 Playwright MCP 插件和 Chromium headless 浏览器。

## 目标环境

| 项目 | 值 |
|------|-----|
| OS | HCE Linux x86_64 (kernel 5.10) |
| 网络 | 仅 npm 内部 mirror 可用，其他外网不通 |
| Node.js | >= 18 |
| 用途 | Claude Code → Playwright MCP → Chromium headless + CDP |

## 版本矩阵

| 组件 | 版本 | 来源 |
|------|------|------|
| @playwright/mcp | 0.0.55 | npm mirror |
| playwright-core | 1.58.0-alpha-2026-01-07 | npm mirror（自动依赖） |
| Chromium | revision 1205 | 离线下载 |
| Remote Browser Viewer | 0.1.0 | 本地构建 .vsix |

## 目录结构

```
playwright-chrome-deploy/
├── README.md                       # 本文件
├── packages/                       # 离线安装包（需手动下载放入）
│   ├── chrome-linux64.zip          # ~176MB, Chromium 完整版
│   ├── chrome-headless-shell-linux64.zip  # ~113MB, Headless Shell
│   └── remote-browser-viewer-0.1.0.vsix  # VSCode 插件
├── scripts/
│   ├── pack.sh                     # macOS 端打包脚本
│   ├── deploy.sh                   # Linux 端部署脚本
│   ├── verify.sh                   # 部署验证脚本
│   └── test-server.py              # 功能验证测试页面
└── docs/
    └── deploy-guide.md             # 详细部署文档 + 故障排查
```

## 快速开始

### 1. 下载离线包（在有网络的机器上）

将以下文件下载后放入 `packages/` 目录：

**Chromium (revision 1205)**：
```
https://cdn.playwright.dev/dbazure/download/playwright/builds/chromium/1205/chromium-linux.zip
```

**Chromium Headless Shell (revision 1205)**：
```
https://cdn.playwright.dev/dbazure/download/playwright/builds/chromium/1205/chromium-headless-shell-linux.zip
```

> 下载后文件名为 `chrome-linux64.zip` 和 `chrome-headless-shell-linux64.zip`。

### 2. macOS 打包

```bash
cd dev_project/playwright-chrome-deploy
bash scripts/pack.sh
# 产出: playwright-chrome-deploy-YYYYMMDD.zip (~276MB)
```

打包脚本自动完成：构建 .vsix → 检查离线包 → 生成部署 zip。

### 3. 传输到 Linux 并部署 Chromium

```bash
scp playwright-chrome-deploy-*.zip user@linux-server:~/
ssh user@linux-server
cd ~ && unzip playwright-chrome-deploy-*.zip
cd playwright-chrome-deploy && bash scripts/deploy.sh
```

### 4. 安装 @playwright/mcp

```bash
# 确保 npm registry 指向内部 mirror
npm config get registry
# 如果是 npmjs.org，需要配置: npm config set registry <内部mirror地址>

# 安装（跳过浏览器下载）
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm install -g @playwright/mcp@0.0.55
```

### 5. 配置 Claude Code MCP（关键步骤）

使用 `claude mcp add` 命令配置（全局生效）：

```bash
claude mcp add playwright --scope user \
  -e DISPLAY="" \
  -e PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright \
  -- npx @playwright/mcp@0.0.55 --headless --no-sandbox --caps devtools \
  --ignore-https-errors \
  --executable-path $HOME/.cache/ms-playwright/chromium-1205/chrome-linux64/chrome
```

验证配置：
```bash
claude mcp list
# 应显示: playwright: ... - ✓ Connected
```

> **踩坑总结**：
> - `--executable-path` 是关键参数。`@playwright/mcp` 的 `--browser` 参数只支持 `chrome/firefox/webkit/msedge`，不支持 `chromium`。默认会去找 `/opt/google/chrome/chrome`（系统 Chrome），离线环境不存在。
> - `--ignore-https-errors` 解决内网自签证书导致页面白屏的问题。
> - MCP 全局配置存储在 `~/.claude.json`（由 `claude mcp add --scope user` 管理），不要手动编辑此文件。
> - `~/.claude/settings.json` 是 Claude Code 设置文件，不能放 `mcpServers`。

### 6. 安装 VSCode 插件

```bash
code --install-extension packages/remote-browser-viewer-0.1.0.vsix
```

### 7. 验证

```bash
# 自动验证 Chromium 部署
bash scripts/verify.sh

# 功能验证：启动测试页面
python3 scripts/test-server.py &
# 在 Claude Code 中: "用 playwright 打开 http://localhost:8765"
# 在 VSCode 中: Remote Browser Viewer 面板应显示测试页面
```

## 详细文档

遇到问题或需要手动部署，参见 [详细部署文档](docs/deploy-guide.md)。
