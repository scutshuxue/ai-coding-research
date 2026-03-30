# 架构设计

## 1. 设计目标

在 VSCode Remote SSH 场景下，让 Windows/macOS 用户实时观察 Linux 服务器上 Playwright MCP 操控的 headless Chromium 浏览器画面。

### 核心约束

- Linux 服务器无图形界面（无 X11、无桌面环境）
- 不引入额外基础设施（无 VNC、无 Xvfb、无 websockify）
- 不需要手动端口转发
- 对 Claude Code / Playwright MCP 零侵入

### 技术选型：CDP Screencast

| 方案 | 帧率 | 复杂度 | 额外依赖 | 选择 |
|------|------|--------|----------|------|
| CDP Screencast | 5-30 fps | 低 | 无 | **采用** |
| 截图轮询 | ~2 fps | 低 | 无 | 太慢 |
| noVNC (Xvfb+x11vnc+websockify) | 30-60 fps | 高 | 3个服务 | 过重 |
| Chrome Remote Debugging UI | 实时 | 中 | 端口转发 | 需要手动配置 |

CDP Screencast 是 Chromium 内置的帧推送机制，事件驱动、自带背压控制、无需额外服务。

## 2. 部署架构

```
┌─────────────────────────────────────────────────────────────┐
│ Windows / macOS                                              │
│                                                              │
│  VSCode IDE                                                  │
│  ├── UI 层                                                   │
│  │   └── WebView Panel (Remote Browser Viewer)               │
│  │       ├── 工具栏：[←][→][↻] + 地址栏 + 刷新CDP按钮       │
│  │       ├── Tab 栏：多页面切换 + 关闭按钮（动态显隐）        │
│  │       ├── 画面区：<img> + 透明叠加层（捕获鼠标/键盘）      │
│  │       ├── IME 输入栏：Ctrl+I 唤出，支持中文输入法          │
│  │       └── 状态栏：连接状态 + Tab数 + FPS                  │
│  │                                                           │
│  └── SSH Remote 通道                                          │
│      └── VSCode IPC (自动复用 SSH 连接)                       │
│                                                              │
└───────────────────────┬──────────────────────────────────────┘
                        │ SSH
┌───────────────────────▼──────────────────────────────────────┐
│ Linux Server                                                  │
│                                                              │
│  VSCode Remote Extension Host                                 │
│  └── remote-browser-viewer 插件                               │
│      ├── extension.ts    （生命周期、命令、面板管理）          │
│      ├── page-watcher.ts （双层 WebSocket CDP 连接）          │
│      ├── cdp-discovery.ts（进程扫描 + HTTP 端点发现）         │
│      └── webview.ts      （WebView HTML 生成）                │
│                                                              │
│  Chromium (headless, CDP enabled)                             │
│  ├── --remote-debugging-port=PORT                             │
│  ├── HTTP: /json/list, /json/version                          │
│  └── WebSocket: ws://127.0.0.1:PORT/devtools/...             │
│                                                              │
│  Playwright MCP Server                                        │
│  └── 接收 Claude Code 指令 → 通过 CDP 操控 Chromium          │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 关键洞察：为什么不需要端口转发

插件运行在 **Linux Extension Host** 中，与 Chromium 在同一台机器上。CDP 连接是 `localhost:PORT` 直连。WebView 的帧数据通过 VSCode 内置的 IPC 通道自动经由 SSH 传输到 Windows 端渲染，无需开发者配置任何网络。

## 3. 双层 WebSocket 架构

v0.1.0 之前采用单一页面级 WS 连接，只能监控一个页面。当前版本改为双层连接：

```
                     ┌─────────────────────────┐
                     │     PageWatcher          │
                     │                          │
  /json/version ────►│  browserWs               │  浏览器级连接
  ws://...browser    │  ├─ Target.setDiscover   │  监听所有 target 创建/销毁/变化
                     │  ├─ Target.targetCreated │
                     │  ├─ Target.targetChanged │
                     │  └─ Target.targetDestroyed│
                     │                          │
  /json/list ───────►│  pageWs                  │  页面级连接（当前活跃 tab）
  ws://...page/ID    │  ├─ Page.enable          │  接收 screencast 帧
                     │  ├─ Page.startScreencast │
                     │  ├─ Page.screencastFrame │
                     │  └─ Page.frameNavigated  │
                     │                          │
                     │  tabs: Map<id, TabInfo>  │  维护所有页面的状态
                     └─────────────────────────┘
```

### 为什么需要两层

| 层级 | 连接目标 | 职责 | 生命周期 |
|------|---------|------|---------|
| browserWs | `/json/version` → browser WS | 监听 Target 域事件（新建/关闭/变化页面） | 随浏览器存活 |
| pageWs | `/json/list` → 指定 page WS | 订阅 Page 域事件 + Screencast 帧流 | 随 tab 切换重建 |

- `browserWs` 是全局的，能感知所有页面的生死和 URL 变化
- `pageWs` 绑定到一个具体页面，切换 tab 时断开旧的、连接新的
- 两层分离使得 Tab 列表维护和 Screencast 流控互不干扰

## 4. 数据流

### 4.1 帧传输路径

```
Chromium 渲染页面
    │
    ▼ CDP WebSocket
Page.screencastFrame { data: "base64...", sessionId: N }
    │
    ▼ page-watcher.ts handlePageMessage()
this.onFrame(data, sessionId)
this.sendPageCommand('Page.screencastFrameAck', { sessionId })  ← 背压控制
    │
    ▼ extension.ts onFrame 回调
panel.webview.postMessage({ type: 'frame', data: base64Data })
    │
    ▼ VSCode IPC over SSH（自动）
    │
    ▼ webview.ts 内嵌 JavaScript
img.src = 'data:image/jpeg;base64,' + msg.data
    │
    ▼ 浏览器渲染引擎解码 JPEG → 显示
```

### 4.2 背压控制机制

CDP Screencast 使用 ACK 单缓冲模型：

```
Chromium ──frame(id=1)──► PageWatcher
                          │ 处理+转发
Chromium ◄──ACK(id=1)────┘
                          │ Chromium 收到 ACK 后才发下一帧
Chromium ──frame(id=2)──► PageWatcher
                          ...
```

这保证了：
- 不会堆积帧队列（内存安全）
- 帧率自动适配显示端处理速度
- Chromium 在 ACK 延迟时自动降低帧率

### 4.3 自动触发流程

```
Claude Code: browser.goto("https://example.com")
    │
    ▼ Playwright MCP → CDP
Chromium: 导航到 example.com
    │
    ▼ CDP 事件（两条路径同时触发）
    │
    ├─► browserWs: Target.targetInfoChanged { url: "https://example.com" }
    │   └─► 更新 tabs Map → emitTabsChanged()
    │
    └─► pageWs: Page.frameNavigated { frame: { url: "https://example.com" } }
        └─► onBrowserActivated("https://example.com")
            │
            ▼ extension.ts
            if (autoOpen && !panel) {
                openViewerWithScreencast(url)  // 自动创建 WebView
            }
```

### 4.4 Tab 切换流程

```
用户点击 WebView Tab 栏
    │
    ▼ webview.ts → postMessage
{ type: 'switchTab', targetId: 'TARGET_ID' }
    │
    ▼ extension.ts handleTabSwitch()
    │
    ├─ pageWatcher.stopScreencast()      // 停止旧帧流
    ├─ screencastActive = false
    ├─ pageWatcher.switchToTarget(id)    // 关闭旧 pageWs，连接新 pageWs
    ├─ startScreencastIfNeeded()          // 新 pageWs 上启动 screencast
    └─ panel.postMessage({ type: 'url', url: tab.url })  // 更新 URL 显示
```

### 4.5 重连流程

```
Chrome 被关闭 / 进程退出
    │
    ▼ browserWs 断开
    │
    ▼ scheduleReconnect()（5秒后重试）
    │
    ▼ connect()
    ├─ discoverCdpPort()           // ps aux 重新发现 Chrome 进程
    ├─ findBrowserWsUrl(port)      // /json/version 获取 browser WS URL
    ├─ connectBrowserWs(wsUrl)     // 建立新的 browserWs
    ├─ refreshTabs()               // 刷新 tab 列表
    └─ switchToTarget(first)       // 连接第一个可用页面
    │
    ▼ onReconnected()
    │
    ▼ extension.ts
    screencastActive = false       // 重置标记
    startScreencastIfNeeded()      // 重新启动 screencast
    panel.postMessage({ type: 'status', text: 'CDP 已重连' })
```

## 5. 模块职责

### extension.ts — 生命周期管理

```
activate()
├── 创建状态栏
├── 初始化 PageWatcher
├── 注册回调
│   ├── onFrame → 转发帧到 WebView
│   ├── onTabsChanged → 更新状态栏 + 转发 tab 列表
│   ├── onReconnected → 重置 screencast + 通知 WebView
│   └── onActivated → 自动打开/更新 WebView
├── 启动 CDP 连接
└── 注册命令
    ├── remoteBrowser.open → openViewerWithScreencast()
    ├── remoteBrowser.stop → stopScreencast()
    ├── remoteBrowser.refresh → 重新 connect()
    └── remoteBrowser.status → 显示状态弹窗

openViewerWithScreencast()
├── 创建或聚焦 WebView Panel
├── 注册 WebView 消息监听（switchTab, requestRefresh）
├── 发送当前 tab 列表和连接状态
└── startScreencastIfNeeded()

handleTabSwitch()
├── 停止旧 screencast
├── switchToTarget(targetId)
├── 启动新 screencast
└── 更新 URL 显示
```

### page-watcher.ts — CDP 连接管理

```
PageWatcher
├── 状态
│   ├── browserWs: WebSocket       // 浏览器级连接
│   ├── pageWs: WebSocket          // 页面级连接
│   ├── tabs: Map<string, TabInfo> // 所有页面状态
│   ├── activeTargetId: string     // 当前 screencast 的目标
│   └── cdpPort: number            // 当前 CDP 端口
│
├── 连接
│   ├── connect() → 完整建连流程
│   ├── connectBrowserWs() → 浏览器级 WS
│   ├── switchToTarget() → 页面级 WS
│   └── scheduleReconnect() → 5s 重试
│
├── 事件处理
│   ├── handleBrowserMessage()
│   │   ├── Target.targetCreated → 新增 tab
│   │   ├── Target.targetInfoChanged → 更新 tab
│   │   └── Target.targetDestroyed → 删除 tab + 自动切换
│   └── handlePageMessage()
│       ├── Page.frameNavigated → URL 变化通知
│       └── Page.screencastFrame → 帧回调 + ACK
│
├── 控制
│   ├── startScreencast(quality, maxWidth, maxHeight)
│   ├── stopScreencast()
│   └── refreshTabs()
│
└── 查询
    ├── getTabs() → 过滤后的 tab 列表
    ├── getActiveTargetId()
    ├── isConnected() → browserWs 状态
    └── isPageConnected() → pageWs 状态
```

### cdp-discovery.ts — CDP 发现

```
parseCdpPortFromProcessLine(line) → number | null
    正则提取 --remote-debugging-port=PORT

discoverCdpPort() → number
    ps aux | grep chrome | grep remote-debugging-port

findCdpTargets(port) → CdpTarget[]
    GET http://127.0.0.1:{port}/json/list

findPageTarget(port) → CdpTarget
    过滤 type=page，优先非内部页面

findAllPageTargets(port) → CdpTarget[]
    所有 type=page 的 target

findBrowserWsUrl(port) → string
    GET http://127.0.0.1:{port}/json/version → webSocketDebuggerUrl
```

### webview.ts — WebView 面板

```
createViewerPanel(initialUrl?) → WebviewPanel
    创建面板，注入 HTML

updatePanelTitle(panel, url)
    从 URL 提取 hostname 更新标题

getHtml() → string
    完整 HTML 文档：
    ├── 工具栏（指示灯 + URL + 刷新按钮）
    ├── Tab 栏（动态渲染，多页面时自动显示）
    ├── 画面区（img + placeholder）
    ├── 状态栏（连接状态 + tab数 + FPS）
    └── JavaScript
        ├── 帧处理：img.src = data:image/jpeg;base64,...
        ├── Tab 渲染：renderTabs(tabs, activeTargetId)
        ├── 状态更新：updateConnectionStatus(connected, pageConnected)
        ├── FPS 计算：每秒统计帧数
        └── 消息发送：switchTab, requestRefresh
```

## 6. 多客户端 CDP 安全

Playwright MCP 和 Viewer 同时连接到同一个 Chromium 实例：

| 客户端 | 连接目标 | 操作类型 | 安全性 |
|--------|---------|---------|--------|
| Playwright MCP | 页面 WS | 读写（导航、点击、填写等） | 主控方 |
| Viewer (browserWs) | 浏览器 WS | 只读（Target.setDiscoverTargets） | 安全 |
| Viewer (pageWs) | 页面 WS | 只读（Page.enable + Screencast） | 安全 |

Viewer 只使用只读命令，不会干扰 Playwright 的操作。CDP 支持多客户端同时连接同一个 target。

## 7. 状态机

### 连接状态

```
          ┌─────────┐    connect()    ┌──────────┐
  ────────► 未连接   ├───────────────►│ 已连接    │
          │         │◄───────────────┤          │
          └────┬────┘   WS 断开      └─────┬────┘
               │                           │
               │   scheduleReconnect()     │ switchToTarget()
               │   (5s)                    │
               ▼                           ▼
          ┌─────────┐              ┌──────────────┐
          │ 重连中   │              │ 页面已连接    │
          │         │              │ (screencast)  │
          └─────────┘              └──────────────┘
```

### Screencast 状态

```
          ┌──────────┐   startScreencast()  ┌──────────┐
          │ 已停止    ├────────────────────►│ 运行中    │
          │          │◄────────────────────┤          │
          └──────────┘   stopScreencast()   └──────────┘
                         panel.dispose()
                         WS 断开
```
