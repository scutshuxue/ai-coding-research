# Remote Browser Viewer 双向交互设计

## 目标

在现有 Screencast 只读查看基础上，增加完整双向交互能力：鼠标点击/悬停/滚动/右键、键盘输入、地址栏导航（含前进/后退/刷新按钮），让用户在 Windows VSCode WebView 中像使用真实浏览器一样操作 Linux 端的 Chromium。

## 架构

```
WebView (Windows)                      Extension (Linux)                Chrome (Linux)
┌────────────────────────┐            ┌────────────────────┐          ┌──────────┐
│ [←][→][↻] [  URL输入  ]│──navigate──→│                    │─Page.navigate→│          │
│ ┌────────────────────┐ │            │                    │          │          │
│ │ 透明叠加层 (事件捕获)│ │─click/key─→│   extension.ts     │──Input.*────→│   CDP    │
│ ├────────────────────┤ │            │   (坐标转换+派发)   │          │          │
│ │ <img> Screencast帧  │ │←──frame────│   page-watcher.ts  │←screencast─│          │
│ └────────────────────┘ │            │                    │          │          │
│              fps status │            └────────────────────┘          └──────────┘
└────────────────────────┘
```

**核心原理**：在 `<img>` 上方覆盖一个透明 `<div>`，捕获所有鼠标和键盘事件，通过 `vscode.postMessage` 发送到 Extension 端，Extension 将坐标转换后通过 CDP `Input.*` 命令派发到 Chromium。

## 交互事件映射

### 鼠标事件

| WebView 事件 | CDP 命令 | 参数 | 说明 |
|---|---|---|---|
| click | `Input.dispatchMouseEvent` | type: mousePressed → mouseReleased, button: left | 左键点击 |
| dblclick | `Input.dispatchMouseEvent` | clickCount: 2 | 双击 |
| mousemove | `Input.dispatchMouseEvent` | type: mouseMoved | 节流 50ms，实现 hover 效果 |
| wheel | `Input.dispatchMouseEvent` | type: mouseWheel, deltaX, deltaY | 页面滚动 |
| contextmenu | `Input.dispatchMouseEvent` | button: right | 右键 |

### 键盘事件

| WebView 事件 | CDP 命令 | 参数 | 说明 |
|---|---|---|---|
| keydown | `Input.dispatchKeyEvent` | type: keyDown, key, code, modifiers | 按键按下 |
| keypress (可打印字符) | `Input.dispatchKeyEvent` | type: char, text | 字符输入 |
| keyup | `Input.dispatchKeyEvent` | type: keyUp, key, code | 按键释放 |

**modifiers 映射**：Alt=1, Ctrl=2, Meta(Cmd)=4, Shift=8，按位或组合。

### 导航事件

| 操作 | CDP 命令 | 说明 |
|---|---|---|
| 地址栏回车 | `Page.navigate({url})` | 导航到输入的 URL |
| 后退按钮 | `Page.navigateToHistoryEntry` | 需先 `Page.getNavigationHistory` 获取 entries |
| 前进按钮 | `Page.navigateToHistoryEntry` | 同上 |
| 刷新按钮 | `Page.reload` | 重新加载当前页面 |

## 坐标转换

Screencast 帧 metadata 包含 `deviceWidth`、`deviceHeight`、`pageScaleFactor`。WebView 中 `<img>` 使用 `object-fit: contain` 自动缩放，存在 letterbox 区域。

### 转换算法

```
// img 的自然尺寸 = screencast 捕获的尺寸（受 maxWidth/maxHeight 限制）
// metadata.deviceWidth/Height = 浏览器实际视口尺寸

imgRect = img.getBoundingClientRect()

// object-fit:contain 的实际渲染区域
imgAspect = img.naturalWidth / img.naturalHeight
containerAspect = imgRect.width / imgRect.height

if (imgAspect > containerAspect):
    // 图片更宽，上下有 letterbox
    renderWidth = imgRect.width
    renderHeight = imgRect.width / imgAspect
else:
    // 图片更高，左右有 letterbox
    renderHeight = imgRect.height
    renderWidth = imgRect.height * imgAspect

offsetX = (imgRect.width - renderWidth) / 2
offsetY = (imgRect.height - renderHeight) / 2

// 鼠标坐标（相对于 overlay div）→ 页面坐标
pageX = (mouseX - offsetX) / renderWidth * metadata.deviceWidth
pageY = (mouseY - offsetY) / renderHeight * metadata.deviceHeight
```

如果点击落在 letterbox 区域（pageX/pageY 超出范围），忽略该事件。

## metadata 传递

当前 `onFrame` 回调只传 base64 数据，不传 metadata。需要修改：

- `page-watcher.ts`：`onFrame` 回调增加 metadata 参数
- `extension.ts`：将 metadata 随帧数据一起 postMessage 到 WebView
- `webview.ts`：存储最新的 metadata，坐标转换时使用

## WebView UI 改动

### 地址栏 + 工具按钮

将现有只读 `<div id="url">` 替换为：

```html
<div id="toolbar">
  <button id="back" title="后退">←</button>
  <button id="forward" title="前进">→</button>
  <button id="refresh" title="刷新">↻</button>
  <input id="urlInput" type="text" placeholder="输入 URL..." />
</div>
```

- 回车键触发导航
- Page.frameNavigated 事件更新地址栏内容（非焦点状态时）

### 透明叠加层

```html
<div id="overlay" tabindex="0"
     style="position:absolute; top:0; left:0; width:100%; height:100%;
            cursor:default; outline:none;">
</div>
```

- `tabindex="0"` 使其可聚焦，接收键盘事件
- 点击 overlay 时自动聚焦
- 鼠标事件：click, dblclick, mousemove(节流50ms), wheel, contextmenu
- 键盘事件：keydown, keyup（聚焦在 overlay 上时）
- 当焦点在地址栏 `<input>` 时，键盘事件不转发到 Chrome

### mousemove 节流

mousemove 事件频率极高（60Hz+），需要节流到 50ms 间隔（20Hz），否则会大量占用 postMessage 通道。

## 文件改动范围

| 文件 | 改动内容 |
|---|---|
| `src/webview.ts` | 地址栏改为 input + 导航按钮；添加透明叠加层；事件捕获+坐标转换+postMessage |
| `src/extension.ts` | 监听 `panel.webview.onDidReceiveMessage`，根据 type 派发 CDP 命令；帧数据增加 metadata |
| `src/page-watcher.ts` | onFrame 回调增加 metadata；新增 `navigate(url)`、`goBack()`、`goForward()`、`reload()` 方法；goBack/goForward 内部管理 navigation history |

不新增文件，改动集中在现有 3 个文件中。

## 与 Playwright MCP 的关系

不做互斥处理。用户手动操作和 Playwright MCP 操作可以同时进行。实际场景中用户通常在 AI 停下后才手动操作，冲突概率极低。

## 不在范围内

- 文件上传/下载
- 拖拽操作
- 多 Tab 切换
- 触摸事件
