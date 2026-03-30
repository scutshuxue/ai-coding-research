# 用户指南

## 1. 前置条件

### 环境要求

| 组件 | 要求 |
|------|------|
| VSCode | >= 1.85.0 |
| VSCode Remote SSH | 已安装并连接到 Linux 服务器 |
| Linux 服务器 | 运行 Chromium/Chrome（由 Playwright MCP 管理） |
| Node.js | >= 18（Extension Host 运行时） |

### 确认 Playwright MCP 配置

Playwright MCP 启动 Chromium 时会自动启用 CDP。确认 MCP 配置中 Chromium 使用了 `--remote-debugging-port` 参数。

常见配置位置（Claude Code MCP 配置）：

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@anthropic-ai/playwright-mcp@latest"],
      "env": {
        "DISPLAY": ""
      }
    }
  }
}
```

Playwright MCP 默认以 headless 模式启动 Chromium，并自动开启 CDP 端口（随机分配）。插件会自动发现该端口，无需手动配置。

## 2. 安装

### 方式一：从 .vsix 安装（推荐）

```bash
# 在 Linux 服务器上（通过 VSCode Remote SSH 终端）
code --install-extension remote-browser-viewer-0.1.0.vsix
```

或在 VSCode 中：`Ctrl+Shift+P` → `Extensions: Install from VSIX...` → 选择 `.vsix` 文件。

### 方式二：从源码构建安装

```bash
cd dev_project/vscode-remote-viewer
npm install
npm run build
npm run package
code --install-extension remote-browser-viewer-0.1.0.vsix
```

### 安装验证

安装成功后，VSCode 右下角状态栏应出现：

```
$(globe) Browser: 等待连接...
```

## 3. 日常使用

### 3.1 自动模式（默认）

这是最常用的方式，无需任何手动操作：

1. 在 Claude Code 中正常工作
2. Claude Code 调用 Playwright MCP 打开浏览器页面
3. 插件自动检测到浏览器导航事件
4. WebView 面板自动弹出，显示浏览器实时画面
5. Claude Code 继续操作浏览器，画面实时更新
6. 浏览器关闭后，面板保持打开等待下次操作

```
你: "帮我搜索 baidu.com 的天气"
Claude Code: [调用 Playwright 打开 baidu.com]
              ↓ 自动触发
插件: [WebView 面板弹出，显示百度首页]
Claude Code: [在搜索框输入"天气"]
插件: [实时显示输入过程]
Claude Code: [点击搜索]
插件: [显示搜索结果页面]
```

### 3.2 手动打开

如果自动模式被关闭，或需要在浏览器已运行时手动查看：

- **快捷方式**：点击状态栏的 `$(globe) Browser: ...` 图标
- **命令面板**：`Ctrl+Shift+P` → `Remote Browser: 打开浏览器视图`

### 3.3 双向交互

Viewer 面板不仅能看，还能直接操作远程浏览器。

#### 鼠标操作

| 操作 | 效果 |
|------|------|
| 单击 | 点击链接、按钮等页面元素 |
| 双击 | 双击选中文字等 |
| 拖动（按住鼠标移动） | 选中文本、拖拽滑块 |
| 滚轮 | 页面滚动 |
| 右键 | 触发右键操作 |

鼠标坐标会自动从 WebView 画面映射到远程浏览器视口，支持 `object-fit: contain` 下的 letterbox 偏移计算。

#### 键盘输入

点击画面区域后，直接打字即可输入英文字符。支持的按键包括：

- 所有字母、数字、符号键
- `Backspace`、`Delete`、`Enter`、`Tab`、`Escape`
- 方向键（↑↓←→）、`Home`、`End`、`PageUp`、`PageDown`

> **注意**：`Ctrl/Cmd` 组合键保留给 VSCode 使用，不会发送到远程浏览器。

#### 中文输入

由于 VSCode WebView 的限制，中文输入法不能直接在画面上使用。提供 IME 输入栏方案：

1. `Ctrl+I`（macOS: `Cmd+I`）弹出底部输入栏
2. 在输入栏中使用中文输入法正常打字
3. 按 `Enter` 发送文字到远程浏览器的当前焦点位置
4. 按 `Escape` 或点击 ✕ 关闭输入栏

#### 粘贴

`Ctrl+V`（macOS: `Cmd+V`）：从系统剪贴板粘贴文字到远程浏览器的当前输入位置。

#### 浏览器导航

| 操作 | 方式 |
|------|------|
| 输入 URL 导航 | 在顶部地址栏输入 URL 后按 Enter（自动补全 `https://`） |
| 后退 | 点击 ← 按钮 |
| 前进 | 点击 → 按钮 |
| 刷新页面 | 点击 ↻ 按钮 |

### 3.4 多标签页使用

当浏览器打开多个页面时（包括 `window.open()` 弹出的页面）：

1. WebView 自动显示 **Tab 栏**（仅多页面时可见）
2. 当前正在串流的标签页有蓝色下划线标记
3. 点击标签页标题即可切换画面
4. 点击标签页右侧 **×** 按钮可关闭该标签页
5. 新标签页会自动出现在 Tab 栏中
6. 标签页关闭后自动从 Tab 栏移除
7. 如果当前查看的标签页被关闭，自动切换到下一个可用标签页

### 3.4 连接状态监控

#### 工具栏指示灯

| 颜色 | 含义 |
|------|------|
| 🟢 绿色（常亮） | 已连接，正常工作 |
| 🟡 黄色（闪烁） | 浏览器已连接，页面连接未就绪 / 正在重连 |
| 🔴 红色（常亮） | 未连接，Chrome 未运行或 CDP 不可达 |

#### 状态栏信息

底部状态栏显示：
- 左侧：连接状态文字 + Tab 数量（如 `已连接  3 tabs`）
- 右侧：实时帧率（如 `15 fps`）

#### 详细状态

`Ctrl+Shift+P` → `Remote Browser: 查看连接状态`，弹窗显示：

```
浏览器连接: ✅ 已连接
页面连接: ✅ 已连接
标签页数: 3
Screencast: ▶ 运行中

👉 百度一下，你就知道
   新浪新闻
   搜索结果
```

#### VSCode 状态栏

右下角显示：`$(globe) baidu.com [3]`

鼠标悬停显示 tooltip：

```
点击打开 Remote Browser Viewer
状态: 已连接
标签页: 3
  ▶ 百度一下，你就知道
  • 新浪新闻
  • 搜索结果
```

### 3.5 刷新连接

当连接异常时：

- **WebView 内**：点击工具栏右侧 `↻ 刷新` 按钮
- **命令面板**：`Ctrl+Shift+P` → `Remote Browser: 刷新连接`

刷新会断开所有现有连接，重新发现 Chrome 进程并建立连接。

## 4. 配置

在 VSCode 设置中搜索 `remoteBrowser`：

### remoteBrowser.autoOpen

- **默认**：`true`
- **作用**：检测到浏览器导航时自动弹出 WebView 面板
- **关闭场景**：如果你不希望 Viewer 自动弹出干扰编码，设为 `false`，需要时手动打开

### remoteBrowser.quality

- **默认**：`80`
- **范围**：1-100
- **作用**：JPEG 压缩质量，影响画面清晰度和带宽
- **调优建议**：
  - 网络慢时降到 50-60，减少带宽消耗
  - 需要看清文字时提高到 90-100

### remoteBrowser.maxWidth / remoteBrowser.maxHeight

- **默认**：1280 x 720
- **作用**：Screencast 帧的最大分辨率
- **调优建议**：
  - WebView 面板较小时降低（如 800x600），减少不必要的像素传输
  - 需要高分辨率查看时提高（如 1920x1080），但会增加带宽

### 配置示例

```json
// settings.json
{
  "remoteBrowser.autoOpen": true,
  "remoteBrowser.quality": 80,
  "remoteBrowser.maxWidth": 1280,
  "remoteBrowser.maxHeight": 720
}
```

## 5. 故障排查

### 5.1 状态栏一直显示"等待连接..."

**原因**：Chrome/Chromium 未运行或未开启 CDP。

**排查步骤**：

```bash
# 1. 检查 Chrome 进程是否存在
ps aux | grep -i chrome | grep remote-debugging-port

# 2. 如果没有输出，说明 Playwright 还没启动浏览器
# → 在 Claude Code 中执行一个浏览器操作触发启动

# 3. 如果有输出，提取端口号检查 CDP 是否可达
curl http://127.0.0.1:<PORT>/json/version
```

### 5.2 面板打开但没有画面

**原因**：Screencast 未启动或帧未送达。

**排查步骤**：

1. 检查连接指示灯颜色
2. 如果是黄色：页面级连接未就绪，点击刷新
3. 如果是绿色但无画面：执行 `Remote Browser: 刷新连接`
4. 检查 Extension Host 输出日志：`Ctrl+Shift+P` → `Developer: Show Logs...` → `Extension Host`

### 5.3 Chrome 关闭后重开没有画面

**预期行为**：Chrome 关闭后插件自动进入重连循环（5秒间隔），Chrome 重启后自动连接并恢复 Screencast。

**如果没有自动恢复**：
1. 手动执行 `Remote Browser: 刷新连接`
2. 检查新的 Chrome 进程是否使用了 CDP 端口

### 5.4 看不到新打开的标签页

**预期行为**：`window.open()` 或新标签页操作会触发 `Target.targetCreated` 事件，自动加入 Tab 栏。

**如果没有出现**：
1. 点击刷新按钮，触发 `refreshTabs()` 重新获取 `/json/list`
2. 确认新页面不是 `about:blank` 或 `chrome://` 内部页面

### 5.5 帧率很低 / 画面卡顿

**可能原因**：

| 原因 | 解决方案 |
|------|---------|
| JPEG 质量过高 | 降低 `remoteBrowser.quality` 到 50-60 |
| 分辨率过高 | 降低 `remoteBrowser.maxWidth/maxHeight` |
| SSH 带宽不足 | 检查 SSH 连接质量，考虑压缩 |
| Extension Host 负载高 | 检查其他插件是否消耗过多资源 |

### 5.6 提示"未发现运行中的 Chrome/Chromium CDP 端口"

**原因**：`ps aux` 命令未找到带 `--remote-debugging-port` 参数的 Chrome 进程。

**排查**：

```bash
# 检查所有 Chrome 进程
ps aux | grep -i chrome

# Playwright 启动的 Chromium 可能名称不同
ps aux | grep -i chromium
```

如果 Playwright 使用非标准进程名，插件可能无法自动发现。此时需要确认 Playwright MCP 的 Chromium 启动参数。

## 6. 常用操作速查

| 操作 | 方式 |
|------|------|
| 打开 Viewer | 点击状态栏图标 / `Ctrl+Shift+P` → `Remote Browser: 打开浏览器视图` |
| 关闭 Viewer | 关闭 WebView 面板（Screencast 自动停止） |
| 点击/拖动 | 直接在画面上鼠标操作 |
| 英文输入 | 点击画面后直接打字 |
| 中文输入 | `Ctrl+I` 弹出输入栏 → 打字 → 回车发送 |
| 粘贴文字 | `Ctrl+V` |
| URL 导航 | 地址栏输入 URL → 回车 |
| 后退/前进/刷新 | 工具栏 ← → ↻ 按钮 |
| 切换标签页 | 点击 Tab 栏中的标签页标题 |
| 关闭标签页 | 点击 Tab 栏中的 × 按钮 |
| 刷新 CDP 连接 | 工具栏 ⟳ 按钮 / `Ctrl+Shift+P` → `Remote Browser: 刷新连接` |
| 查看状态 | `Ctrl+Shift+P` → `Remote Browser: 查看连接状态` |
| 停止串流 | `Ctrl+Shift+P` → `Remote Browser: 停止 Screencast`（保持连接） |
