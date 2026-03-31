# 离线部署详细指南

## 1. 概述

在无外网的 HCE Linux 服务器上部署 Playwright MCP + Chromium，使 Claude Code 能通过 MCP 操控 headless 浏览器，并通过 Remote Browser Viewer VSCode 插件实时查看浏览器画面。

### 部署架构

```
macOS 开发机（有外网）          Linux 服务器（仅 npm mirror）
┌──────────────────────┐       ┌──────────────────────────────┐
│ 1. 下载 chromium zip │──scp─►│ 3. 解压到 ~/.cache/ms-playwright/  │
│ 2. 构建 .vsix        │       │ 4. npm install @playwright/mcp     │
│ 3. pack.sh 打包      │──scp─►│ 5. claude mcp add 配置             │
│                      │       │ 6. 安装 VSCode 插件                │
└──────────────────────┘       └──────────────────────────────┘
```

### 版本对应关系

```
@playwright/mcp@0.0.55
  └─ playwright-core@1.58.0-alpha-2026-01-07
       └─ browsers.json → chromium revision 1205
```

查询方法（在有 npm 的机器上）：
```bash
# 查看 @playwright/mcp 依赖的 playwright-core 版本
npm view @playwright/mcp@0.0.55 dependencies

# 查看对应的 chromium revision
npm pack playwright-core@<version> --pack-destination /tmp
tar -xzf /tmp/playwright-core-*.tgz -C /tmp
python3 -c "import json; data=json.load(open('/tmp/package/browsers.json')); \
[print(json.dumps(b,indent=2)) for b in data['browsers'] if b['name']=='chromium']"
```

## 2. macOS 端操作

### 2.1 下载 Chromium

```bash
cd dev_project/playwright-chrome-deploy/packages

# 下载 Linux 版 Chromium 完整版（~176MB）
curl -L -o chrome-linux64.zip \
  "https://cdn.playwright.dev/dbazure/download/playwright/builds/chromium/1205/chromium-linux.zip"

# 下载 Chromium Headless Shell（~113MB）
curl -L -o chrome-headless-shell-linux64.zip \
  "https://cdn.playwright.dev/dbazure/download/playwright/builds/chromium/1205/chromium-headless-shell-linux.zip"

# 验证文件大小
ls -lh chrome-*.zip
```

> **注意**：CDN 下载的文件名为 `chrome-linux64.zip`（不是 `chromium-linux.zip`），这是正确的。

### 2.2 打包部署包

```bash
cd dev_project/playwright-chrome-deploy
bash scripts/pack.sh
# 产出: playwright-chrome-deploy-YYYYMMDD.zip (~276MB)
```

打包脚本自动完成：检查 .vsix（不存在则从 vscode-remote-viewer 构建） → 检查 Chromium zip → 打成一个 zip。

### 2.3 传输到 Linux

```bash
scp playwright-chrome-deploy-*.zip user@linux-server:~/
```

## 3. Linux 端操作

### 3.1 部署 Chromium

```bash
cd ~ && unzip playwright-chrome-deploy-*.zip
cd playwright-chrome-deploy
bash scripts/deploy.sh
```

脚本会：检查 Node.js/npm → 解压 Chromium 到 `~/.cache/ms-playwright/chromium-1205/` → 设置可执行权限。

### 3.2 安装 @playwright/mcp

```bash
# 确保 npm registry 指向内部 mirror（不是 npmjs.org）
npm config get registry
# 如果不对: npm config set registry <内部mirror地址>

# 安装（必须设置此变量跳过浏览器下载）
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm install -g @playwright/mcp@0.0.55

# 验证
npm list -g @playwright/mcp
```

### 3.3 配置 Claude Code MCP

使用 `claude mcp add` 命令配置（`--scope user` = 全局生效，所有项目可用）：

```bash
claude mcp add playwright --scope user \
  -e DISPLAY="" \
  -e PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright \
  -- npx @playwright/mcp@0.0.55 --headless --no-sandbox --caps devtools \
  --ignore-https-errors \
  --executable-path $HOME/.cache/ms-playwright/chromium-1205/chrome-linux64/chrome
```

验证：
```bash
claude mcp list
# 应显示: playwright: ... - ✓ Connected
```

#### 关键参数说明

| 参数 | 作用 | 为什么需要 |
|------|------|-----------|
| `--executable-path` | 指定 Chromium 二进制路径 | `--browser` 只支持 `chrome/firefox/webkit/msedge`，不支持 `chromium`。默认查找 `/opt/google/chrome/chrome`（不存在） |
| `--headless` | headless 模式运行 | Linux 无 GUI |
| `--no-sandbox` | 禁用沙箱 | 非 root 用户需要 |
| `--ignore-https-errors` | 忽略 SSL 证书错误 | 内网自签证书导致页面白屏 |
| `--caps devtools` | 启用 CDP DevTools | Remote Browser Viewer 需要 CDP 连接 |
| `PLAYWRIGHT_BROWSERS_PATH` | Playwright 浏览器目录 | 让 Playwright 找到离线部署的 Chromium |

#### MCP 配置位置

| 作用域 | 配置方式 | 存储位置 | 适用范围 |
|--------|---------|---------|---------|
| user（全局） | `claude mcp add --scope user` | `~/.claude.json` | 所有项目 |
| project | `claude mcp add` 或编辑 `.mcp.json` | `<项目>/.mcp.json` | 仅当前项目 |

> **不要手动编辑 `~/.claude.json`** — 此文件由 Claude Code 管理，包含大量内部状态。用 `claude mcp add/remove` 命令操作。
>
> **`~/.claude/settings.json` 不支持 `mcpServers`** — 这是 Claude Code 设置文件（permissions 等），不是 MCP 配置文件。

### 3.4 安装 VSCode 插件

在 VSCode Remote SSH 终端中执行：
```bash
code --install-extension packages/remote-browser-viewer-0.1.0.vsix
```

## 4. 验证

### 4.1 Chromium 部署验证

```bash
bash scripts/verify.sh
```

### 4.2 手动验证 Chromium + CDP

```bash
# 启动 headless Chrome 并验证 CDP
~/.cache/ms-playwright/chromium-1205/chrome-linux64/chrome \
  --headless --no-sandbox --disable-gpu \
  --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 \
  "data:text/html,<h1>Hello CDP</h1>"

# 另一个终端验证 CDP
curl http://127.0.0.1:9222/json/version
curl http://127.0.0.1:9222/json/list

# 清理
pkill -f chrome-linux64
```

> 启动时出现 dbus 错误（`Failed to connect to the bus`）是正常的，Linux 无桌面环境导致，不影响功能。

### 4.3 功能验证（Playwright MCP + Remote Browser Viewer）

```bash
# 启动测试 Web 服务器
python3 scripts/test-server.py &
```

然后在 Claude Code 中：
```
用 playwright 打开 http://localhost:8765
```

测试页面包含：输入框、按钮计数器、下拉框、复选框、页面跳转、新窗口打开 — 覆盖点击/输入/导航/多 Tab 等场景。

在 VSCode 中通过 `Ctrl+Shift+P` → `Remote Browser: 打开浏览器视图` 查看画面。

## 5. 故障排查

### 5.1 `Chromium distribution 'chrome' is not found at /opt/google/chrome/chrome`

**原因**：`@playwright/mcp` 默认使用系统 Google Chrome（`chrome` 通道），不是 Playwright 管理的 Chromium。

**解决**：必须使用 `--executable-path` 直接指定 Chromium 路径。`--browser` 参数不支持 `chromium` 值（只支持 `chrome/firefox/webkit/msedge`），`--config` 中的 `browserName: "chromium"` 也无法覆盖。

```bash
claude mcp remove playwright
claude mcp add playwright --scope user \
  -e DISPLAY="" \
  -e PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright \
  -- npx @playwright/mcp@0.0.55 --headless --no-sandbox --caps devtools \
  --ignore-https-errors \
  --executable-path $HOME/.cache/ms-playwright/chromium-1205/chrome-linux64/chrome
```

### 5.2 Remote Browser Viewer 白屏

**原因**：页面未加载成功（通常是 SSL 证书错误）。

**验证**：用本地页面测试排除插件问题：
```bash
~/.cache/ms-playwright/chromium-1205/chrome-linux64/chrome \
  --headless --no-sandbox --disable-gpu \
  --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 \
  "data:text/html,<h1>Hello CDP</h1><p>Test</p>"
```

如果本地页面能显示，说明插件正常，白屏是目标页面的问题。

**解决**：MCP 配置中添加 `--ignore-https-errors`。

### 5.3 npm install 超时 / ETIMEDOUT

**原因**：npm registry 指向 `registry.npmjs.org`（外网不可达）。

**解决**：
```bash
npm config get registry  # 检查当前源
npm config set registry <公司内部npm mirror地址>
```

### 5.4 Chromium 启动失败：缺少共享库

```bash
ldd ~/.cache/ms-playwright/chromium-1205/chrome-linux64/chrome | grep "not found"
```

常见缺失库与对应 yum 包：

| 缺失库 | yum 包 |
|--------|--------|
| libnss3.so | nss |
| libatk-1.0.so | atk |
| libatk-bridge-2.0.so | at-spi2-atk |
| libcups.so | cups-libs |
| libXcomposite.so | libXcomposite |
| libXdamage.so | libXdamage |
| libXrandr.so | libXrandr |
| libgbm.so | mesa-libgbm |
| libasound.so | alsa-lib |
| libdrm.so | libdrm |
| libpango-1.0.so | pango |
| libxkbcommon.so | libxkbcommon |

### 5.5 PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD 无效

确保在 `npm install` **之前**设置环境变量：

```bash
# 正确
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm install -g @playwright/mcp@0.0.55

# 错误（变量未传递给 postinstall 脚本）
npm install -g @playwright/mcp@0.0.55  # 会尝试下载并失败
```

### 5.6 dbus 错误信息

启动 Chromium 时出现 `Failed to connect to the bus` 等 dbus 错误是**正常的**，因为 Linux 服务器没有桌面环境。这些错误不影响 headless 浏览器功能。

## 6. 升级指南

升级 @playwright/mcp 版本时，需要同步更新 Chromium。

> **重要**：并非所有 playwright-core 版本的 Chromium 都在 CDN 上发布。alpha 版本的 Chromium 可能返回 404/400。需要在下载前验证 CDN 可用性。

```bash
# 1. 查看新版本依赖的 playwright-core 版本
npm view @playwright/mcp@<new-version> dependencies

# 2. 查看对应的 chromium revision
npm pack playwright-core@<version> --pack-destination /tmp
tar -xzf /tmp/playwright-core-*.tgz -C /tmp
python3 -c "import json; data=json.load(open('/tmp/package/browsers.json')); \
[print(json.dumps(b,indent=2)) for b in data['browsers'] if b['name']=='chromium']"

# 3. 验证 CDN 可用性（必须返回 200）
curl -sI -L "https://cdn.playwright.dev/dbazure/download/playwright/builds/chromium/<revision>/chromium-linux.zip" | head -1

# 4. 如果返回 400/404，说明该 revision 未发布，需要换一个 @playwright/mcp 版本
# 5. 下载对应 revision 的 chromium zip
# 6. 修改 deploy.sh 中的 CHROMIUM_REVISION 和 PLAYWRIGHT_MCP_VERSION
# 7. 重新执行 deploy.sh + claude mcp add
```
