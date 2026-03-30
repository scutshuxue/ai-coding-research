# CDP 协议参考

本文档详述 Remote Browser Viewer 使用的 Chrome DevTools Protocol (CDP) 命令和事件。

## 1. 连接方式

### CDP HTTP 端点

Chromium 开启 `--remote-debugging-port=PORT` 后，提供以下 HTTP 端点：

| 端点 | 返回 | 用途 |
|------|------|------|
| `GET /json/version` | 浏览器信息 + `webSocketDebuggerUrl` | 获取浏览器级 WS URL |
| `GET /json/list` | 所有 Target 数组 | 列出页面、Service Worker 等 |

### /json/version 响应示例

```json
{
  "Browser": "HeadlessChrome/120.0.6099.71",
  "Protocol-Version": "1.3",
  "User-Agent": "...",
  "V8-Version": "12.0.267.8",
  "WebKit-Version": "537.36",
  "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/abc123"
}
```

`webSocketDebuggerUrl` 是浏览器级 WS 地址，用于 Target 域命令。

### /json/list 响应示例

```json
[
  {
    "id": "E3B5AF3...",
    "type": "page",
    "title": "百度一下，你就知道",
    "url": "https://www.baidu.com/",
    "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/E3B5AF3..."
  },
  {
    "id": "7C4FA2B...",
    "type": "page",
    "title": "新浪新闻",
    "url": "https://news.sina.com.cn/",
    "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/7C4FA2B..."
  }
]
```

每个 Target 有独立的 `webSocketDebuggerUrl`，用于页面级 WS 连接。

### 双层 WebSocket

```
浏览器级: ws://127.0.0.1:PORT/devtools/browser/BROWSER_ID
    └─ 用于 Target 域（发现/监听所有页面）

页面级:   ws://127.0.0.1:PORT/devtools/page/PAGE_ID
    └─ 用于 Page 域（Screencast + 页面事件）
```

## 2. CDP 命令格式

### 请求

```json
{
  "id": 1,
  "method": "Page.enable",
  "params": {}
}
```

- `id`：递增整数，用于匹配响应
- `method`：`Domain.method` 格式
- `params`：可选参数对象

### 响应

```json
{
  "id": 1,
  "result": {}
}
```

### 事件（服务端推送）

```json
{
  "method": "Page.frameNavigated",
  "params": {
    "frame": { "id": "...", "url": "https://..." }
  }
}
```

事件没有 `id` 字段，由 `method` 字段标识。

## 3. Target 域（浏览器级连接）

### Target.setDiscoverTargets

启用 Target 事件推送。

**发送**（连接建立后立即发送）：

```json
{
  "id": 1,
  "method": "Target.setDiscoverTargets",
  "params": { "discover": true }
}
```

**代码位置**：`page-watcher.ts` `connectBrowserWs()` 第 77 行

启用后，Chromium 会推送以下三个事件。

### Target.targetCreated（事件）

新 Target 创建时触发（包括新标签页、`window.open()` 弹出的页面）。

```json
{
  "method": "Target.targetCreated",
  "params": {
    "targetInfo": {
      "targetId": "E3B5AF3...",
      "type": "page",
      "title": "",
      "url": "about:blank",
      "attached": false,
      "browserContextId": "..."
    }
  }
}
```

**处理逻辑**（`page-watcher.ts` `handleBrowserMessage()` 第 150-163 行）：

```typescript
if (info?.type === 'page') {
    this.tabs.set(info.targetId, { targetId, url, title });
    this.emitTabsChanged();
    if (url !== 'about:blank') {
        this.onBrowserActivated?.(url);  // 触发自动打开
    }
}
```

关键点：
- 只处理 `type === 'page'` 的 Target（忽略 service worker、iframe 等）
- 新页面初始 URL 通常是 `about:blank`，随后通过 `targetInfoChanged` 更新为真实 URL
- 加入 `tabs` Map 并通知 WebView 更新 Tab 栏

### Target.targetInfoChanged（事件）

Target 信息变化时触发（URL 变化、标题变化等）。

```json
{
  "method": "Target.targetInfoChanged",
  "params": {
    "targetInfo": {
      "targetId": "E3B5AF3...",
      "type": "page",
      "title": "百度一下，你就知道",
      "url": "https://www.baidu.com/",
      "attached": true
    }
  }
}
```

**处理逻辑**（`page-watcher.ts` 第 166-180 行）：

```typescript
if (info?.type === 'page' && this.tabs.has(info.targetId)) {
    this.tabs.set(info.targetId, { targetId, url, title });
    this.emitTabsChanged();
    if (url !== 'about:blank' && url !== this.currentUrl) {
        this.currentUrl = url;
        this.onBrowserActivated?.(url);
    }
}
```

关键点：
- 只更新已在 `tabs` Map 中的 Target
- URL 变化时触发 `onBrowserActivated`，可用于自动打开/更新 Viewer

### Target.targetDestroyed（事件）

Target 被销毁时触发（页面关闭、进程结束等）。

```json
{
  "method": "Target.targetDestroyed",
  "params": {
    "targetId": "E3B5AF3..."
  }
}
```

**处理逻辑**（`page-watcher.ts` 第 183-195 行）：

```typescript
this.tabs.delete(targetId);
this.emitTabsChanged();
if (targetId === this.activeTargetId) {
    this.activeTargetId = undefined;
    const remaining = this.getTabs();
    if (remaining.length > 0) {
        this.switchToTarget(remaining[0].targetId);
    }
}
```

关键点：
- 从 `tabs` Map 中移除
- 如果被销毁的是当前 Screencast 目标，自动切换到下一个可用页面

## 4. Page 域（页面级连接）

### Page.enable

订阅页面域事件。

**发送**（页面 WS 连接建立后）：

```json
{ "id": 2, "method": "Page.enable" }
```

**代码位置**：`page-watcher.ts` `switchToTarget()` 第 128 行

启用后可接收 `Page.frameNavigated`、`Page.loadEventFired` 等事件。

### Page.startScreencast

开始实时帧推送。

**发送**：

```json
{
  "id": 3,
  "method": "Page.startScreencast",
  "params": {
    "format": "jpeg",
    "quality": 80,
    "maxWidth": 1280,
    "maxHeight": 720
  }
}
```

**代码位置**：`page-watcher.ts` `startScreencast()` 第 225-228 行

**参数说明**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `format` | `"jpeg"` \| `"png"` | 帧格式。JPEG 更小，推荐用于网络传输 |
| `quality` | number (1-100) | JPEG 压缩质量。80 是清晰度和大小的良好平衡 |
| `maxWidth` | number | 帧最大宽度（像素）。Chromium 会在此范围内自适应 |
| `maxHeight` | number | 帧最大高度（像素） |

发送后，Chromium 开始推送 `Page.screencastFrame` 事件。

### Page.screencastFrame（事件）

Chromium 推送的每一帧画面。

```json
{
  "method": "Page.screencastFrame",
  "params": {
    "data": "/9j/4AAQSkZJRg...",
    "metadata": {
      "offsetTop": 0,
      "pageScaleFactor": 1,
      "deviceWidth": 1280,
      "deviceHeight": 720,
      "scrollOffsetX": 0,
      "scrollOffsetY": 0,
      "timestamp": 1711766400.123
    },
    "sessionId": 1
  }
}
```

**字段说明**：

| 字段 | 说明 |
|------|------|
| `data` | base64 编码的 JPEG 图片数据 |
| `metadata.deviceWidth/Height` | 实际渲染尺寸 |
| `metadata.pageScaleFactor` | 页面缩放比例 |
| `metadata.scrollOffsetX/Y` | 页面滚动偏移 |
| `metadata.timestamp` | 帧时间戳（秒） |
| `sessionId` | 帧序号，用于 ACK |

**处理逻辑**（`page-watcher.ts` 第 218-222 行）：

```typescript
if (msg.method === 'Page.screencastFrame') {
    const { data, sessionId } = msg.params;
    this.onFrame?.(data, sessionId);                          // 回调传递帧数据
    this.sendPageCommand('Page.screencastFrameAck', { sessionId }); // 立即 ACK
}
```

### Page.screencastFrameAck

确认收到帧，触发 Chromium 发送下一帧。

**发送**（收到 `screencastFrame` 后立即发送）：

```json
{
  "id": 4,
  "method": "Page.screencastFrameAck",
  "params": { "sessionId": 1 }
}
```

**背压机制**：Chromium 在收到当前帧的 ACK 之前不会推送下一帧。这形成了单缓冲模型，自动适配客户端处理速度。

```
时序：
  Chromium                    PageWatcher
     │──── frame(sid=1) ────►│
     │                        │ 处理 + 转发到 WebView
     │◄─── ACK(sid=1) ───────│
     │                        │
     │──── frame(sid=2) ────►│  ← 收到 ACK 后才发
     │                        │
     ...
```

如果 WebView 处理慢（比如 SSH 带宽不足），ACK 延迟，Chromium 自动降低帧率。

### Page.stopScreencast

停止帧推送。

**发送**：

```json
{ "id": 5, "method": "Page.stopScreencast" }
```

**代码位置**：`page-watcher.ts` `stopScreencast()` 第 232 行

面板关闭或用户手动停止时调用。

### Page.frameNavigated（事件）

页面主帧导航完成时触发。

```json
{
  "method": "Page.frameNavigated",
  "params": {
    "frame": {
      "id": "main",
      "parentId": null,
      "url": "https://www.baidu.com/",
      "securityOrigin": "https://www.baidu.com",
      "mimeType": "text/html"
    }
  }
}
```

**处理逻辑**（`page-watcher.ts` 第 200-215 行）：

```typescript
if (msg.method === 'Page.frameNavigated') {
    const frame = msg.params.frame;
    if (frame.parentId) return;           // 忽略 iframe 导航
    const url = frame.url;
    if (url && url !== 'about:blank' && url !== this.currentUrl) {
        this.currentUrl = url;
        // 更新 tab 信息
        if (this.activeTargetId) {
            const tab = this.tabs.get(this.activeTargetId);
            if (tab) tab.url = url;
        }
        this.onBrowserActivated?.(url);   // 通知 extension
    }
}
```

关键点：
- `frame.parentId` 非空表示 iframe 导航，忽略
- 只响应 URL 实际变化的事件
- 同时更新 `tabs` Map 中对应 tab 的 URL

## 5. Runtime 域

### Runtime.enable

订阅运行时事件。

**发送**（页面 WS 连接建立后）：

```json
{ "id": 3, "method": "Runtime.enable" }
```

**代码位置**：`page-watcher.ts` `switchToTarget()` 第 129 行

当前版本未直接使用 Runtime 事件，但启用后可支持未来的控制台日志监听等功能。

## 6. CDP 端口发现

### 发现流程

```
1. ps aux | grep chrome | grep remote-debugging-port
   → 提取 --remote-debugging-port=PORT 参数值

2. GET http://127.0.0.1:{PORT}/json/version
   → 获取 webSocketDebuggerUrl（浏览器级）

3. GET http://127.0.0.1:{PORT}/json/list
   → 获取所有 Target 列表（页面级）
```

### 端口发现正则

```typescript
const match = line.match(/--remote-debugging-port=(\d+)/);
```

匹配 `ps aux` 输出中的 Chrome 进程参数。

### Playwright MCP 端口行为

Playwright MCP 启动 Chromium 时使用**随机端口**（每次不同）。插件通过进程扫描动态发现，无需固定配置。

如需固定端口，可在 Playwright MCP 配置中指定：

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@anthropic-ai/playwright-mcp@latest"],
      "env": {
        "PLAYWRIGHT_CHROMIUM_ARGS": "--remote-debugging-port=9222"
      }
    }
  }
}
```

## 7. 多客户端并发

CDP 支持多个 WebSocket 客户端同时连接同一个 Target：

```
Playwright MCP ──────► Chromium Page WS ◄────── Viewer (pageWs)
   (读写操作)                                    (只读监控)

                       Chromium Browser WS ◄──── Viewer (browserWs)
                                                 (Target 域监听)
```

注意事项：
- 多个客户端连接同一页面 WS 时，所有客户端都会收到事件
- Viewer 只使用只读命令（Page.enable, Screencast），不会干扰 Playwright 操作
- Screencast 是 Chromium 端的全局状态，如果 Playwright 也调用 `startScreencast`，可能产生冲突（实际场景中 Playwright 不使用 Screencast）

## 8. 性能特征

### 帧大小参考

| 分辨率 | 质量 | 典型帧大小 | 15fps 带宽 |
|--------|------|-----------|-----------|
| 1280x720 | 80 | 50-80 KB | 0.75-1.2 MB/s |
| 1280x720 | 50 | 25-40 KB | 0.38-0.6 MB/s |
| 800x600 | 80 | 30-50 KB | 0.45-0.75 MB/s |
| 1920x1080 | 80 | 100-150 KB | 1.5-2.25 MB/s |

### 延迟分解

| 阶段 | 延迟 |
|------|------|
| Chromium 编码 JPEG | 5-15 ms |
| WS 传输（localhost） | < 1 ms |
| Extension 处理 + postMessage | 1-3 ms |
| SSH IPC 传输 | 10-30 ms |
| WebView 渲染 | 5-10 ms |
| **端到端总计** | **30-50 ms** |
