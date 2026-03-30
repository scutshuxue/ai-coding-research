# 远程浏览器实时查看方案设计

## 一、背景与需求

### 1.1 使用场景

```mermaid
graph LR
    subgraph Windows["Windows 本地"]
        VSCode["VSCode IDE"]
        Panel["🖥️ VSCode 内嵌<br/>实时浏览器面板"]
    end

    subgraph Linux["Linux 服务器（无 GUI）"]
        CC["Claude Code"]
        LLM["大模型 Agent"]
        MCP["Playwright MCP"]
        Chromium["Chromium 浏览器"]
    end

    VSCode -->|SSH Remote| CC
    CC --> LLM
    LLM -->|tool_use| MCP
    MCP -->|CDP| Chromium
    Chromium ====>|"实时画面流"| Panel

    style Panel fill:#27ae60,color:#fff,stroke-width:3px
    style Chromium fill:#e74c3c,color:#fff
```

**环境**：Windows VSCode 通过 SSH Remote 连接 Linux 服务器开发。Linux 上运行 Claude Code，大模型通过 Playwright MCP 操作 Chromium。

**核心需求**：

1. 在 VSCode 中**实时**看到 Linux 上浏览器的全部操作过程（不是截图，是连续画面流）
2. Claude Code 调用浏览器 MCP 时**自动打开**查看面板
3. 嵌入 VSCode 内部，不需要切换窗口

### 1.2 约束条件

| 约束 | 说明 |
|------|------|
| Linux 无 GUI | 服务器无 X11/Wayland 桌面环境，需虚拟显示 |
| 网络通道 | SSH 连接，VSCode SSH Remote 自动端口转发 |
| 实时性 | 要求连续画面流，非轮询截图 |
| 易用性 | Claude Code MCP 操作时自动触发，无需手动操作 |

---

## 二、技术方案：noVNC 实时流 + VSCode 插件

### 2.1 整体架构

```mermaid
graph TB
    subgraph Linux["Linux 服务器"]
        direction TB

        subgraph VirtualDisplay["虚拟显示层"]
            Xvfb["Xvfb :99<br/>虚拟帧缓冲 1920x1080x24<br/>模拟物理显示器"]
        end

        subgraph BrowserLayer["浏览器层"]
            PW["Playwright MCP Server"]
            Chrome["Chromium (headed)<br/>DISPLAY=:99<br/>渲染到虚拟显示"]
        end

        subgraph StreamLayer["流媒体层"]
            x11vnc["x11vnc<br/>捕获 X11 帧缓冲<br/>VNC RFB 协议 :5900"]
            websockify["websockify :6080<br/>VNC → WebSocket 协议转换"]
        end

        PW -->|"CDP 操作"| Chrome
        Chrome -->|"像素渲染"| Xvfb
        Xvfb -->|"X11 共享内存<br/>读取帧缓冲"| x11vnc
        x11vnc -->|"RFB 协议<br/>差分帧编码"| websockify
    end

    subgraph SSH["VSCode SSH Remote"]
        PortFwd["自动端口转发<br/>localhost:6080 → linux:6080"]
    end

    subgraph Windows["Windows VSCode"]
        direction TB
        Ext["remote-browser-viewer<br/>VSCode 插件"]
        WV["WebView Panel"]
        noVNCjs["noVNC JS 客户端<br/>(RFB 解码 + Canvas 渲染)"]
        SB["StatusBar 状态指示"]
        Hook["Claude Code Hook<br/>自动触发"]

        Ext --> WV
        WV --> noVNCjs
        Ext --> SB
        Hook -->|"检测 MCP 调用"| Ext
    end

    websockify -->|"WebSocket 帧流"| PortFwd
    PortFwd -->|"ws://localhost:6080"| noVNCjs

    style Xvfb fill:#9b59b6,color:#fff
    style Chrome fill:#e74c3c,color:#fff
    style noVNCjs fill:#27ae60,color:#fff
    style WV fill:#3498db,color:#fff
```

### 2.2 为什么选 noVNC 而非 CDP 截图

| 维度 | noVNC (VNC 流) | CDP captureScreenshot | CDP startScreencast |
|------|:-:|:-:|:-:|
| 传输方式 | 差分帧编码，仅传变化像素 | 每次完整截图 | 事件驱动帧 |
| 实时性 | 真实时，30-60fps | 轮询，5-10fps | 中等，15-30fps |
| 带宽效率 | 高（ZRLE/Tight 压缩） | 低（每帧 50-150KB） | 中 |
| 静态页面 | 几乎零带宽 | 仍在轮询 | 几乎零带宽 |
| 鼠标光标 | 可见（看到 AI 的操作轨迹） | 不可见 | 不可见 |
| 动画/视频 | 流畅 | 丢帧严重 | 有延迟 |
| 技术成熟度 | 20+ 年，极其成熟 | 需自建服务 | Chrome 实验性 API |

**结论**：noVNC 是唯一能提供"像本地浏览器一样流畅"体验的方案。

---

## 三、技术原理详解

### 3.1 虚拟显示层：Xvfb

```mermaid
graph LR
    subgraph Normal["有 GUI 的 Linux"]
        GPU["GPU"] --> FB["物理帧缓冲<br/>/dev/fb0"]
        FB --> Monitor["显示器"]
    end

    subgraph Headless["无 GUI 的 Linux + Xvfb"]
        XvfbProc["Xvfb 进程"] --> VFB["虚拟帧缓冲<br/>共享内存"]
        VFB --> Reader["x11vnc<br/>读取像素"]
    end

    style VFB fill:#9b59b6,color:#fff
```

**Xvfb (X Virtual Frame Buffer)** 在内存中模拟一个 X11 显示服务器：
- 提供完整的 X11 协议实现，对应用程序完全透明
- Chromium "以为"自己在渲染到物理显示器，实际渲染到内存缓冲区
- 零 GPU 依赖，纯 CPU 软件渲染
- 支持任意分辨率和色深

### 3.2 VNC 协议流：差分帧编码

```mermaid
sequenceDiagram
    participant Chrome as Chromium
    participant Xvfb as Xvfb 帧缓冲
    participant VNC as x11vnc
    participant WS as websockify
    participant Client as noVNC 客户端

    Note over Xvfb: 初始状态：空白页面

    Chrome->>Xvfb: 渲染百度首页
    VNC->>Xvfb: 检测到帧缓冲变化区域
    VNC->>VNC: ZRLE 编码变化矩形<br/>(只编码变化的像素块)
    VNC->>WS: RFB FramebufferUpdate<br/>{x:0, y:0, w:1920, h:1080}
    WS->>Client: WebSocket binary frame
    Client->>Client: Canvas 绘制完整页面

    Note over Chrome: AI 在搜索框输入文字

    Chrome->>Xvfb: 重绘搜索框区域 (200x30px)
    VNC->>Xvfb: 检测到小区域变化
    VNC->>VNC: ZRLE 编码<br/>(仅 200x30 像素)
    VNC->>WS: RFB FramebufferUpdate<br/>{x:500, y:300, w:200, h:30}
    WS->>Client: WebSocket binary (~2KB)
    Client->>Client: Canvas 局部更新

    Note over Chrome: 页面静止，无操作
    Note over VNC: 无变化 → 不发送数据<br/>零带宽消耗
```

**核心优势**：VNC RFB 协议只传输屏幕上**实际变化的矩形区域**，这意味着：
- 页面加载时：全屏更新，带宽较高
- AI 输入文字时：只传几 KB 的小矩形
- 页面静止时：零传输

### 3.3 websockify 协议转换

```mermaid
graph LR
    subgraph TCP["传统 VNC"]
        VNCClient["VNC Viewer<br/>(需安装)"]
        TCPConn["TCP :5900"]
    end

    subgraph WS["WebSocket VNC (noVNC)"]
        Browser["浏览器/WebView<br/>(无需安装)"]
        WSConn["WebSocket :6080"]
    end

    x11vnc["x11vnc :5900<br/>VNC 服务"] --> TCPConn --> VNCClient
    x11vnc --> |"TCP"| websockify["websockify<br/>协议桥接"]
    websockify --> WSConn --> Browser

    style WS fill:#eafaf1,stroke:#27ae60
    style websockify fill:#f39c12,color:#fff
```

websockify 将 VNC 的 TCP RFB 协议封装为 WebSocket 帧，使浏览器/WebView 能直接连接 VNC 服务。

### 3.4 noVNC 客户端渲染

noVNC 是纯 JavaScript 实现的 VNC 客户端，核心流程：

```mermaid
graph TD
    A["WebSocket 收到 binary frame"] --> B["RFB 协议解析"]
    B --> C{"编码类型"}
    C -->|ZRLE| D1["ZRLE 解码<br/>zlib 解压 + run-length"]
    C -->|Tight| D2["Tight 解码<br/>JPEG/zlib 混合"]
    C -->|Raw| D3["Raw 解码<br/>直接像素数据"]
    D1 --> E["写入 Canvas 2D<br/>ImageData"]
    D2 --> E
    D3 --> E
    E --> F["requestAnimationFrame<br/>显示到屏幕"]
```

**嵌入 VSCode WebView 的关键**：noVNC 核心是 `@novnc/novnc` npm 包，可以直接在 WebView 中使用，只需要：
1. 一个 `<canvas>` 元素
2. 一个 WebSocket 连接到 `ws://localhost:6080`
3. 调用 `RFB` 类即可

---

## 四、Linux 端部署详细设计

### 4.1 服务启动流程

```mermaid
flowchart TD
    Start["启动远程浏览器环境"] --> S1

    subgraph S1["步骤1：虚拟显示"]
        Xvfb["Xvfb :99 -screen 0 1920x1080x24 -ac &"]
        ENV["export DISPLAY=:99"]
        Xvfb --> ENV
    end

    S1 --> S2

    subgraph S2["步骤2：VNC 服务"]
        x11vnc_cmd["x11vnc -display :99<br/>-forever -shared<br/>-nopw -rfbport 5900<br/>-noxdamage &"]
    end

    S2 --> S3

    subgraph S3["步骤3：WebSocket 代理"]
        ws_cmd["websockify 6080 localhost:5900 &"]
    end

    S3 --> S4

    subgraph S4["步骤4：Playwright 配置"]
        PW_Config["Playwright MCP 配置<br/>headless: false<br/>DISPLAY=:99"]
    end

    S4 --> Ready["就绪：等待 AI 操作浏览器"]

    style Ready fill:#27ae60,color:#fff
```

### 4.2 一键启动脚本

```bash
#!/bin/bash
# start-browser-env.sh — 在 Linux 服务器上启动远程浏览器环境

set -e

DISPLAY_NUM="${DISPLAY_NUM:-99}"
SCREEN_SIZE="${SCREEN_SIZE:-1920x1080x24}"
VNC_PORT="${VNC_PORT:-5900}"
WS_PORT="${WS_PORT:-6080}"

echo "=== Remote Browser Environment ==="
echo "Display: :${DISPLAY_NUM} (${SCREEN_SIZE})"
echo "VNC:     :${VNC_PORT}"
echo "WS:      :${WS_PORT}"
echo ""

# 清理旧进程
cleanup() {
    echo "Stopping services..."
    pkill -f "Xvfb :${DISPLAY_NUM}" 2>/dev/null || true
    pkill -f "x11vnc.*:${VNC_PORT}" 2>/dev/null || true
    pkill -f "websockify.*${WS_PORT}" 2>/dev/null || true
}
trap cleanup EXIT
cleanup

# 1. 虚拟显示
echo "[1/3] Starting Xvfb..."
Xvfb :${DISPLAY_NUM} -screen 0 ${SCREEN_SIZE} -ac +extension GLX +render -noreset &
sleep 1
export DISPLAY=:${DISPLAY_NUM}

# 验证 Xvfb
if ! xdpyinfo -display :${DISPLAY_NUM} > /dev/null 2>&1; then
    echo "ERROR: Xvfb failed to start"
    exit 1
fi
echo "  Xvfb running on :${DISPLAY_NUM}"

# 2. VNC 服务
echo "[2/3] Starting x11vnc..."
x11vnc \
    -display :${DISPLAY_NUM} \
    -forever \
    -shared \
    -nopw \
    -rfbport ${VNC_PORT} \
    -noxdamage \
    -cursor arrow \
    -xkb \
    -noxrecord \
    -noxfixes \
    -nowf \
    2>/dev/null &
sleep 1
echo "  x11vnc running on :${VNC_PORT}"

# 3. WebSocket 代理
echo "[3/3] Starting websockify..."
websockify ${WS_PORT} localhost:${VNC_PORT} > /dev/null 2>&1 &
sleep 1
echo "  websockify running on :${WS_PORT}"

echo ""
echo "=== Ready ==="
echo "Connect from VSCode plugin → ws://localhost:${WS_PORT}"
echo "Or browser → http://localhost:${WS_PORT}/vnc.html (if using --web)"
echo ""
echo "Press Ctrl+C to stop all services"

# 保持前台运行
wait
```

### 4.3 systemd 服务配置（生产部署）

```ini
# /etc/systemd/system/browser-env.service
[Unit]
Description=Remote Browser Environment (Xvfb + VNC + WebSocket)
After=network.target

[Service]
Type=forking
Environment=DISPLAY_NUM=99
Environment=SCREEN_SIZE=1920x1080x24
ExecStart=/opt/browser-env/start-browser-env.sh
ExecStop=/bin/bash -c 'pkill -f "Xvfb :99"; pkill -f "x11vnc"; pkill -f "websockify"'
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 4.4 Docker 方案（可选）

```dockerfile
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    xvfb x11vnc websockify \
    fonts-wqy-zenhei fonts-noto-cjk \
    libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libgbm1 \
    && rm -rf /var/lib/apt/lists/*

# Playwright 浏览器由挂载的项目自行安装

COPY start-browser-env.sh /opt/
RUN chmod +x /opt/start-browser-env.sh

EXPOSE 6080

CMD ["/opt/start-browser-env.sh"]
```

```bash
docker run -d \
    --name browser-env \
    -p 6080:6080 \
    --shm-size=2g \
    browser-env
```

### 4.5 Playwright MCP 配置

关键：Playwright 必须以 **headed 模式** 运行，浏览器窗口渲染到 Xvfb：

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@anthropic-ai/mcp-playwright"],
      "env": {
        "DISPLAY": ":99",
        "PLAYWRIGHT_HEADLESS": "false"
      }
    }
  }
}
```

如果 Playwright MCP 不支持 `PLAYWRIGHT_HEADLESS` 环境变量，需要查看具体 MCP 实现的配置方式。大部分 Playwright MCP 实现支持 `headless` 参数：

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@anthropic-ai/mcp-playwright", "--headless", "false"],
      "env": {
        "DISPLAY": ":99"
      }
    }
  }
}
```

---

## 五、VSCode 插件详细设计

### 5.1 插件架构

```mermaid
graph TB
    subgraph Extension["remote-browser-viewer 插件"]
        direction TB

        Activate["activate()"] --> Register["注册命令 + StatusBar"]
        Register --> Watcher["启动 AutoOpenWatcher"]

        subgraph Commands["命令"]
            CmdOpen["remoteBrowser.open<br/>打开查看面板"]
            CmdClose["remoteBrowser.close<br/>关闭查看面板"]
            CmdToggle["remoteBrowser.toggle<br/>切换面板"]
        end

        subgraph Panel["BrowserPanel (核心)"]
            WV["WebView Panel<br/>viewType: remoteBrowser"]
            HTML["WebView HTML"]
            noVNC["noVNC JS 库<br/>@novnc/novnc"]
            Canvas["Canvas 渲染"]

            WV --> HTML
            HTML --> noVNC
            noVNC --> Canvas
        end

        subgraph Auto["自动触发"]
            FileWatch["FileSystemWatcher<br/>监听 /tmp/.browser-signal"]
            PortWatch["端口检测<br/>定期检查 6080 是否可用"]
        end

        subgraph Status["状态栏"]
            SBItem["$(globe) Remote Browser<br/>点击打开/关闭"]
            SBStatus["连接状态指示<br/>🟢 Connected / 🔴 Disconnected"]
        end
    end

    CmdOpen --> Panel
    Auto -->|"信号触发"| CmdOpen
    Panel -->|"状态变更"| Status

    style Panel fill:#3498db,color:#fff
    style Auto fill:#e67e22,color:#fff
```

### 5.2 WebView 中嵌入 noVNC 的核心实现

```mermaid
sequenceDiagram
    participant Ext as 插件 Extension
    participant WV as WebView Panel
    participant noVNC as noVNC RFB
    participant WS as websockify :6080

    Ext->>WV: createWebviewPanel('remoteBrowser')
    Ext->>WV: setHtml(含 noVNC 库 + 连接逻辑)

    WV->>noVNC: new RFB(canvas, wsUrl)
    noVNC->>WS: WebSocket 连接<br/>ws://localhost:6080

    Note over WS: VNC 握手
    WS-->>noVNC: RFB 协议版本协商
    noVNC->>WS: 安全类型选择 (None)
    WS-->>noVNC: 服务器初始化<br/>{width: 1920, height: 1080, name: ":99"}

    loop 实时帧更新
        WS-->>noVNC: FramebufferUpdate<br/>(差分矩形，ZRLE 编码)
        noVNC->>noVNC: 解码 → Canvas 绘制
    end

    noVNC-->>Ext: postMessage('connected')
    Ext->>Ext: StatusBar 更新为 🟢

    Note over WS: 连接断开
    noVNC-->>Ext: postMessage('disconnected')
    Ext->>Ext: StatusBar 更新为 🔴
    noVNC->>noVNC: 3秒后自动重连
```

### 5.3 WebView HTML 结构

```mermaid
graph TB
    subgraph WebViewHTML["WebView HTML"]
        direction TB

        Head["&lt;head&gt;<br/>noVNC CSS + 自适应样式"]

        subgraph Body["&lt;body&gt;"]
            Toolbar["#toolbar<br/>状态灯 | URL | 缩放控制 | 全屏按钮"]
            Container["#vnc-container<br/>flex: 1, overflow: hidden"]
            CanvasEl["&lt;canvas&gt; #vnc-canvas<br/>noVNC 渲染目标"]
            Overlay["#overlay<br/>连接中... / 等待浏览器启动..."]
        end

        Script["&lt;script&gt;<br/>noVNC RFB 初始化<br/>自动重连逻辑<br/>缩放适配<br/>postMessage 通信"]
    end

    Container --> CanvasEl
    Container --> Overlay

    style CanvasEl fill:#27ae60,color:#fff
```

核心 JS 逻辑伪代码：

```javascript
// WebView 内部脚本
import RFB from '@novnc/novnc/core/rfb.js';

const vscode = acquireVsCodeApi();
let rfb = null;

function connect() {
    const url = 'ws://localhost:${port}';
    rfb = new RFB(document.getElementById('vnc-canvas'), url, {
        scaleViewport: true,     // 自动缩放适配面板大小
        clipViewport: false,
        resizeSession: false,
        showDotCursor: true,     // 显示远程光标
        qualityLevel: 6,         // 0-9 质量级别
        compressionLevel: 2      // 0-9 压缩级别
    });

    rfb.addEventListener('connect', () => {
        document.getElementById('overlay').style.display = 'none';
        vscode.postMessage({ type: 'status', connected: true });
    });

    rfb.addEventListener('disconnect', (e) => {
        document.getElementById('overlay').style.display = 'flex';
        vscode.postMessage({ type: 'status', connected: false });
        // 自动重连
        setTimeout(connect, 3000);
    });

    rfb.addEventListener('desktopname', (e) => {
        vscode.postMessage({ type: 'name', name: e.detail.name });
    });
}

connect();

// 监听插件消息（缩放、全屏等控制）
window.addEventListener('message', (e) => {
    if (e.data.type === 'scale') rfb.scaleViewport = e.data.value;
    if (e.data.type === 'quality') rfb.qualityLevel = e.data.value;
});
```

### 5.4 插件配置项

| 配置键 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `remoteBrowser.wsPort` | number | 6080 | websockify WebSocket 端口 |
| `remoteBrowser.autoOpen` | boolean | true | 检测到浏览器 MCP 操作时自动打开面板 |
| `remoteBrowser.scaleViewport` | boolean | true | 自动缩放适配面板大小 |
| `remoteBrowser.quality` | number | 6 | VNC 画质 (0-9，越高越清晰) |
| `remoteBrowser.compression` | number | 2 | VNC 压缩级别 (0-9，越高越省带宽) |
| `remoteBrowser.reconnectInterval` | number | 3000 | 断线重连间隔 (ms) |
| `remoteBrowser.panelPosition` | string | "beside" | 面板位置：beside / bottom / active |

### 5.5 命令与快捷键

| 命令 ID | 标题 | 快捷键 | 说明 |
|---------|------|--------|------|
| `remoteBrowser.open` | Remote Browser: Open | `Ctrl+Shift+B` | 打开实时浏览器面板 |
| `remoteBrowser.close` | Remote Browser: Close | - | 关闭面板 |
| `remoteBrowser.toggle` | Remote Browser: Toggle | `Ctrl+Shift+V` | 切换面板显示/隐藏 |
| `remoteBrowser.reconnect` | Remote Browser: Reconnect | - | 强制重连 |
| `remoteBrowser.screenshot` | Remote Browser: Screenshot | - | 保存当前画面截图 |

### 5.6 noVNC 库打包策略

```mermaid
graph LR
    subgraph Build["构建时"]
        NPM["npm install @novnc/novnc"]
        Bundle["esbuild / webpack 打包"]
        VSIX["打包为 .vsix"]
    end

    subgraph Runtime["运行时"]
        ExtLoad["插件加载"]
        WVCreate["创建 WebView"]
        Script["注入打包后的<br/>noVNC bundle.js"]
    end

    NPM --> Bundle --> VSIX
    VSIX --> ExtLoad --> WVCreate --> Script

    style Bundle fill:#f39c12,color:#fff
```

noVNC 核心文件 (`@novnc/novnc/core/rfb.js`) 约 200KB，打包后可压缩到 ~80KB，对 VSCode 插件体积影响极小。

---

## 六、自动触发机制

### 6.1 完整流程

```mermaid
sequenceDiagram
    participant User as 用户
    participant CC as Claude Code (Linux)
    participant Hook as PostToolUse Hook
    participant Signal as /tmp/.browser-signal
    participant Ext as VSCode 插件
    participant Panel as 浏览器面板
    participant VNC as noVNC → websockify

    User->>CC: "帮我登录 xxx 网站"
    CC->>CC: 大模型决定操作浏览器
    CC->>CC: tool_use: mcp__playwright__browser_navigate

    rect rgb(255, 243, 224)
        Note over Hook: Claude Code Hook 触发
        CC->>Hook: PostToolUse 事件
        Hook->>Hook: matcher 匹配 "mcp__playwright"
        Hook->>Signal: touch /tmp/.browser-signal
    end

    rect rgb(232, 245, 233)
        Note over Ext: VSCode 插件检测到信号
        Ext->>Ext: FileSystemWatcher 检测到文件变更
        Ext->>Ext: 检查面板是否已打开？
        alt 面板未打开
            Ext->>Panel: 创建 WebView Panel
            Panel->>VNC: 建立 WebSocket 连接
            VNC-->>Panel: VNC 实时画面流开始
        else 面板已打开
            Note over Panel: 无需操作，画面已在实时显示
        end
    end

    CC->>CC: tool_use: mcp__playwright__browser_fill
    Note over Panel: 用户在 VSCode 面板中<br/>实时看到 AI 在输入文字

    CC->>CC: tool_use: mcp__playwright__browser_click
    Note over Panel: 用户实时看到 AI 点击按钮

    CC-->>User: "已成功登录 xxx 网站"
```

### 6.2 Claude Code Hook 配置

```json
// ~/.claude/settings.json 或项目 .claude/settings.json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "mcp__playwright",
        "command": "touch /tmp/.browser-signal && echo 'browser-signal-sent'"
      }
    ]
  }
}
```

### 6.3 插件端信号监听

```mermaid
graph TD
    A["插件 activate()"] --> B["创建 FileSystemWatcher"]
    B --> C["监听 /tmp/.browser-signal"]
    C --> D{"文件变更事件"}
    D --> E{"面板已打开？"}
    E -->|是| F["无需操作"]
    E -->|否| G{"6080 端口可连？"}
    G -->|是| H["自动打开面板"]
    G -->|否| I["StatusBar 显示<br/>'浏览器环境未启动'"]

    H --> J["连接 noVNC"]
    J --> K["实时画面显示"]

    style H fill:#27ae60,color:#fff
    style K fill:#3498db,color:#fff
```

### 6.4 备选触发方式：VSCode 命令转发

如果 Claude Code 支持直接调用 VSCode 命令，可以更简洁：

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "mcp__playwright",
        "command": "code --command remoteBrowser.open"
      }
    ]
  }
}
```

---

## 七、数据流与网络

### 7.1 端口映射

```mermaid
graph LR
    subgraph Linux["Linux 端口"]
        P99["Xvfb :99<br/>(X11 UNIX socket)"]
        P5900["x11vnc :5900<br/>(VNC TCP)"]
        P6080["websockify :6080<br/>(WebSocket)"]
    end

    subgraph SSH["SSH Remote 自动转发"]
        FW["localhost:6080 ↔ linux:6080<br/>(VSCode 自动检测并转发)"]
    end

    subgraph Windows["Windows"]
        WS["ws://localhost:6080<br/>(WebView 连接)"]
    end

    P99 -.->|"X11 本地"| P5900
    P5900 -.->|"TCP 本地"| P6080
    P6080 -->|"SSH 隧道"| FW
    FW --> WS

    style FW fill:#f39c12,color:#fff
```

**VSCode SSH Remote 自动端口转发**：当 Linux 上有进程监听 6080 端口时，VSCode 会自动检测并转发到 Windows 的 `localhost:6080`。无需手动配置。

如果自动转发未生效，可手动配置 `.vscode/settings.json`：

```json
{
  "remote.SSH.defaultForwardedPorts": [
    { "localPort": 6080, "remotePort": 6080, "name": "noVNC" }
  ]
}
```

### 7.2 带宽估算

| 场景 | 带宽消耗 | 说明 |
|------|---------|------|
| 页面静止 | ~0 KB/s | VNC 差分编码，无变化不传输 |
| AI 输入文字 | ~5-20 KB/s | 只更新文本框区域 |
| 页面导航/加载 | ~200-500 KB/s | 全屏重绘，持续 1-3 秒 |
| 滚动页面 | ~100-300 KB/s | 大面积矩形更新 |
| 页面含动画 | ~50-150 KB/s | 持续小区域更新 |

通过 SSH 隧道，这些带宽完全可控。

---

## 八、安装依赖与环境准备

### 8.1 Linux 依赖安装

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y \
    xvfb          \  # 虚拟帧缓冲
    x11vnc        \  # X11 VNC 服务
    websockify    \  # VNC → WebSocket 代理
    x11-utils     \  # xdpyinfo 等工具（验证用）
    fonts-wqy-zenhei fonts-noto-cjk  # 中文字体（关键！）

# CentOS/RHEL
sudo yum install -y xorg-x11-server-Xvfb x11vnc python3-websockify \
    wqy-zenhei-fonts google-noto-sans-cjk-ttc-fonts
```

### 8.2 中文字体（重要）

如果浏览器打开中文网页，必须安装中文字体，否则显示为方块：

```bash
# 验证中文字体
fc-list :lang=zh

# 如果为空，安装：
sudo apt-get install -y fonts-wqy-zenhei fonts-wqy-microhei fonts-noto-cjk
sudo fc-cache -fv
```

### 8.3 Playwright 浏览器安装

```bash
# 安装 Playwright 和 Chromium
npx playwright install chromium
npx playwright install-deps chromium  # 安装系统依赖

# 验证
DISPLAY=:99 npx playwright launch --browser chromium
```

---

## 九、项目文件结构

```
remote-browser-viewer/
├── linux/                          # Linux 端
│   ├── start-browser-env.sh        # 一键启动脚本
│   ├── stop-browser-env.sh         # 停止脚本
│   ├── browser-env.service         # systemd 服务文件
│   └── Dockerfile                  # Docker 方案（可选）
│
├── vscode-extension/               # VSCode 插件
│   ├── package.json                # 插件清单（命令、配置、激活事件）
│   ├── tsconfig.json
│   ├── esbuild.config.js           # 打包配置
│   ├── src/
│   │   ├── extension.ts            # 入口：命令注册、StatusBar、Watcher
│   │   ├── browser-panel.ts        # WebView Panel 管理
│   │   ├── auto-open.ts            # 自动触发逻辑
│   │   ├── port-checker.ts         # 端口可用性检测
│   │   └── webview/
│   │       ├── index.html           # WebView HTML 模板
│   │       └── vnc-client.js        # noVNC 初始化 + 重连 + 通信
│   ├── vendor/
│   │   └── novnc/                   # @novnc/novnc 打包后的 bundle
│   └── resources/
│       └── icon.png                 # 插件图标
│
├── claude-hooks/                    # Claude Code Hook 配置
│   └── settings.json.example        # Hook 配置示例
│
└── README.md                        # 使用文档
```

---

## 十、关键技术决策

### 10.1 为什么 noVNC 而不是自研流协议

```mermaid
graph TB
    subgraph Option1["自研 CDP 截图流"]
        A1["需要开发 browser-mirror 服务"]
        A2["轮询截图，非真实时"]
        A3["看不到鼠标光标移动"]
        A4["每帧完整 JPEG 传输"]
    end

    subgraph Option2["noVNC (选定方案)"]
        B1["零开发：现成组件"]
        B2["VNC 差分帧，真实时"]
        B3["完整鼠标光标轨迹"]
        B4["仅传输变化像素"]
    end

    style Option2 fill:#eafaf1,stroke:#27ae60
    style Option1 fill:#fdedec,stroke:#e74c3c
```

### 10.2 headed vs headless + screencast

| 方面 | headed + Xvfb (选定) | headless + CDP screencast |
|------|:-:|:-:|
| 渲染真实度 | 100% 真实 Chromium 渲染 | 受 headless 限制 |
| 字体渲染 | 完整 CJK 字体支持 | 可能有差异 |
| 弹窗/对话框 | 原生显示 | 可能不显示 |
| 光标可见 | 是 | 否 |
| 依赖 | Xvfb + x11vnc + websockify | 仅 Node.js |
| 稳定性 | 极其成熟 | Chrome 实验性 API |

选择 headed + Xvfb：**所见即所得，AI 操作的就是真实的浏览器界面**。

### 10.3 VSCode WebView 安全限制

VSCode WebView 默认有严格的 CSP (Content Security Policy)：

```
default-src 'none';
style-src ${webview.cspSource} 'unsafe-inline';
script-src 'nonce-xxx';
connect-src ws://localhost:* wss://localhost:*;
```

关键点：
- `connect-src ws://localhost:*` — 允许 WebSocket 连接到 localhost（通过 SSH 转发的端口）
- noVNC JS 需要以 `nonce` 方式加载
- Canvas 操作不受 CSP 限制

---

## 十一、开发路线图

```mermaid
gantt
    title 开发计划
    dateFormat YYYY-MM-DD
    axisFormat %m/%d

    section Phase 1：环境验证（1天）
    Linux 安装 Xvfb+VNC+websockify        :p1a, 2026-03-29, 1d
    Playwright headed 模式验证             :p1b, after p1a, 1d
    SSH 端口转发 + 浏览器访问 noVNC        :p1c, after p1a, 1d

    section Phase 2：VSCode 插件基础（2天）
    插件脚手架 + WebView Panel             :p2a, after p1c, 1d
    嵌入 noVNC 库 + 连接 VNC              :p2b, after p2a, 1d
    StatusBar + 命令注册                   :p2c, after p2b, 1d

    section Phase 3：自动触发（1天）
    Claude Code Hook 配置                  :p3a, after p2c, 1d
    FileWatcher 自动打开面板               :p3b, after p3a, 1d
    端口检测 + 优雅降级                    :p3c, after p3a, 1d

    section Phase 4：打磨体验（1天）
    自适应缩放 + 画质调节                  :p4a, after p3c, 1d
    断线重连 + 状态提示                    :p4b, after p3c, 1d
    打包 vsix + 安装测试                   :p4c, after p4b, 1d
```

### Phase 1 快速验证步骤

```bash
# === 在 Linux 服务器上执行 ===

# 1. 安装依赖
sudo apt install -y xvfb x11vnc websockify x11-utils

# 2. 启动虚拟显示
Xvfb :99 -screen 0 1920x1080x24 -ac &
export DISPLAY=:99

# 3. 验证显示
xdpyinfo -display :99 | head -5
# 应看到: name of display: :99, version number: 11.0

# 4. 启动 VNC + WebSocket
x11vnc -display :99 -forever -shared -nopw -rfbport 5900 &
websockify --web /usr/share/novnc/ 6080 localhost:5900 &

# 5. 启动一个测试浏览器
npx playwright install chromium
DISPLAY=:99 npx playwright open https://www.baidu.com

# === 在 Windows 上验证 ===

# 6. VSCode SSH Remote 连接后
#    端口面板检查 6080 是否已转发
#    浏览器打开 http://localhost:6080/vnc.html
#    应看到 Linux 上的 Chromium 浏览器实时画面
```

---

## 十二、hello-halo 参考借鉴

hello-halo 项目中的以下设计可借鉴于本方案：

| hello-halo 特性 | 本方案借鉴 |
|------|------|
| 27 个浏览器工具通过 MCP 暴露 | Playwright MCP 已实现类似工具集 |
| Accessibility Tree + UID 快照 | Playwright MCP 的 `browser_snapshot` 同样基于 AX Tree |
| 反检测 (stealth) | 可选：在 Chromium 启动参数中加入反检测 flag |
| offscreen 隐藏窗口 | 本方案用 Xvfb 替代，对应用完全透明 |
| 内置 HTTP+WS 远程访问 | 本方案用 noVNC + SSH 端口转发替代 |
| View Live 实时预览 | 本方案的 WebView Panel 即为 View Live |
| Session partition 共享 | Chromium 本身支持 `--user-data-dir` 实现 session 持久化 |

hello-halo 基于 Electron 的浏览器操作方式（CDP 直连 WebContents）无法在无头 Linux 上使用，但其 **MCP 工具设计模式** 和 **实时预览交互设计** 是本方案 VSCode 插件的直接参考。
