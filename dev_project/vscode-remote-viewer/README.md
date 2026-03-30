# Remote Browser Viewer

在 VSCode WebView 中实时查看远程 Linux 服务器上 Playwright MCP 操控的浏览器画面。

## 解决什么问题

使用 VSCode Remote SSH 连接 Linux 服务器进行 AI Coding 时，Claude Code 通过 Playwright MCP 操控 headless Chromium 浏览器。由于 Linux 服务器没有图形界面，开发者无法看到浏览器中发生了什么。

本插件通过 Chrome DevTools Protocol (CDP) 的 Screencast 能力，将浏览器画面实时串流到 VSCode WebView 中，让开发者在 Windows/macOS 端直接观察 AI 的浏览器操作。

## 核心特性

- **实时画面串流** — 基于 CDP Screencast，5-30 fps 事件驱动帧传输
- **双向交互** — 鼠标点击/拖动/滚动、键盘输入、中文输入法支持
- **浏览器导航** — 地址栏输入 URL、前进/后退/刷新按钮
- **零配置网络** — 插件和 Chromium 同在 Linux 端，localhost 直连，无需端口转发
- **自动触发** — 检测到浏览器导航时自动弹出 Viewer 面板
- **多标签页支持** — 浏览器级 CDP 连接监听所有 Target，Tab 栏切换和关闭
- **弹出页面捕获** — `window.open()` 创建的新页面自动加入 Tab 列表
- **自动重连** — Chrome 重启后 5 秒自动重连并恢复 Screencast
- **连接状态可视化** — 工具栏指示灯（绿/黄/红）、状态栏详情、刷新按钮

## 架构概览

```
Windows/macOS                          Linux Server
┌──────────────────┐                  ┌──────────────────────────────┐
│ VSCode IDE       │                  │ VSCode Extension Host        │
│ ┌──────────────┐ │  VSCode IPC     │ ┌──────────────────────────┐ │
│ │ WebView      │◄├──over SSH──────►├─┤ Remote Browser Viewer    │ │
│ │ (Tab栏+画面) │ │                  │ │ ├─ browserWs (Target域)  │ │
│ └──────────────┘ │                  │ │ └─ pageWs (Page域)       │ │
└──────────────────┘                  │ └────────┬─────────────────┘ │
                                      │          │ localhost:PORT    │
                                      │ ┌────────▼─────────────────┐ │
                                      │ │ Chromium (headless+CDP)  │ │
                                      │ │ ← Playwright MCP 操控    │ │
                                      │ └──────────────────────────┘ │
                                      └──────────────────────────────┘
```

## 快速开始

### 前置条件

- VSCode >= 1.85.0
- VSCode Remote SSH 连接到 Linux 服务器
- Linux 服务器上运行 Playwright MCP（自带 Chromium + CDP）

### 安装

```bash
cd dev_project/vscode-remote-viewer

# 一键打包（安装依赖 → 编译 → 测试 → 生成 .vsix）
npm run package

# 打包并自动安装到 VSCode
bash scripts/package.sh --install
```

也可以分步执行：

```bash
npm install          # 安装依赖
npm run build        # 编译 TypeScript
npm test             # 运行测试
npx @vscode/vsce package --baseContentUrl . --baseImagesUrl .  # 生成 .vsix
```

安装已有的 .vsix 文件：

```bash
code --install-extension remote-browser-viewer-0.1.0.vsix
```

### 使用

1. **自动模式（默认）**：Claude Code 通过 Playwright 打开网页时，Viewer 面板自动弹出
2. **手动打开**：`Ctrl+Shift+P` → 输入 `Remote Browser: 打开浏览器视图`
3. **交互操作**：在画面上直接点击链接、拖动选择文本、滚动页面
4. **键盘输入**：点击画面后直接输入英文；`Ctrl+I` 弹出中文输入栏
5. **导航**：使用地址栏输入 URL，← → ↻ 按钮进行前进/后退/刷新
6. **标签页管理**：点击 Tab 栏切换页面，点击 × 关闭标签页
7. **刷新连接**：`Ctrl+Shift+P` → `Remote Browser: 刷新连接`
8. **查看状态**：`Ctrl+Shift+P` → `Remote Browser: 查看连接状态`

## 命令

| 命令 | 说明 |
|------|------|
| `Remote Browser: 打开浏览器视图` | 手动打开/聚焦 Viewer 面板 |
| `Remote Browser: 停止 Screencast` | 停止帧传输（保持 CDP 连接） |
| `Remote Browser: 刷新连接` | 断开并重新连接 CDP |
| `Remote Browser: 查看连接状态` | 显示详细连接状态和标签页列表 |

## 配置

| 设置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `remoteBrowser.autoOpen` | boolean | `true` | 检测到浏览器操作时自动打开视图 |
| `remoteBrowser.quality` | number | `80` | JPEG 压缩质量 1-100 |
| `remoteBrowser.maxWidth` | number | `1280` | Screencast 最大宽度（像素） |
| `remoteBrowser.maxHeight` | number | `720` | Screencast 最大高度（像素） |

## WebView 界面说明

```
┌─[●]─[←][→][↻]─[ https://www.baidu.com        ]─[⟳]─┐  ← 工具栏（导航+地址栏+刷新）
├─[ 百度一下 ×]─[ 新闻页面 ×]─[ 搜索结果 ×]───────────┤  ← Tab栏（可切换+关闭）
│                                                       │
│              浏览器实时画面（可点击/拖动/滚动）          │  ← 交互画面区
│                                                       │
│  ┌──────────────────────────────────────────────┐     │
│  │ 输入文字后按回车发送... [发送] [✕]            │     │  ← IME输入栏（Ctrl+I唤出）
│  └──────────────────────────────────────────────┘     │
├─[ 已连接 ]─[ 3 tabs ]──────[ 15 fps ]────────────────┤  ← 状态栏
└───────────────────────────────────────────────────────┘
```

- **导航按钮**：← 后退 / → 前进 / ↻ 刷新页面
- **地址栏**：可输入 URL 后回车导航，自动补全 `https://`
- **连接指示灯**：🟢 已连接 / 🟡 连接中 / 🔴 未连接
- **Tab 栏**：多页面时自动出现，点击切换，× 关闭标签页
- **交互区**：鼠标点击/拖动/滚动直接操作远程浏览器
- **IME 输入栏**：`Ctrl+I` 弹出，支持中文输入法，回车发送
- **状态栏**：左侧连接状态和 Tab 数量，右侧实时帧率

## 项目结构

```
src/
├── extension.ts       # 插件入口，生命周期管理，命令注册
├── page-watcher.ts    # 双层 CDP 连接，Target/Page 事件处理
├── cdp-discovery.ts   # CDP 端口发现和 Target 查询
├── webview.ts         # WebView 面板创建和 HTML/JS 生成
└── test/
    └── cdp-discovery.test.ts  # 单元测试
```

## 技术栈

- **语言**：TypeScript
- **构建**：esbuild（bundled to dist/extension.js）
- **运行时**：Node.js 18+（VSCode Extension Host）
- **协议**：Chrome DevTools Protocol over WebSocket
- **依赖**：`ws`（WebSocket 客户端）

## 性能参考

| 指标 | 典型值 |
|------|--------|
| 单帧大小 | 50-80 KB（1280x720 @ 80% JPEG） |
| 帧率 | 5-15 fps（ACK 背压控制） |
| 带宽消耗 | 0.75-1.2 MB/s（15fps） |
| 端到端延迟 | 30-50 ms |
| 插件内存 | ~5 MB（空闲时） |

## 详细文档

- [架构设计](docs/architecture.md) — 双层 WebSocket 架构、数据流、模块职责
- [用户指南](docs/user-guide.md) — 安装部署、日常使用、故障排查
- [开发指南](docs/development.md) — 本地开发、调试、测试、打包
- [CDP 协议参考](docs/cdp-protocol.md) — 使用的 CDP 命令和事件详解

## License

MIT
