# VSCode Remote Browser Viewer 插件实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 开发一个 VSCode 插件，通过 CDP Screencast 在 WebView 中实时显示 Playwright MCP 操控的浏览器画面，自动检测浏览器操作并打开面板。

**Architecture:** 插件运行在 Linux Remote Extension Host，通过 localhost 直连 Chromium CDP（动态端口发现），监听 `Page.frameNavigated` 等事件自动触发 Screencast，帧数据通过 `postMessage` 发送到 WebView，VSCode 自动把 WebView 渲染回 Windows。

**Tech Stack:** TypeScript, VSCode Extension API, WebSocket (`ws`), Chrome DevTools Protocol, esbuild (打包)

---

## 文件结构

```
dev_project/vscode-remote-viewer/
├── package.json                  # VSCode 插件清单 + 依赖
├── tsconfig.json                 # TypeScript 编译配置
├── esbuild.js                    # 打包脚本
├── src/
│   ├── extension.ts              # 插件入口：激活、命令注册、生命周期
│   ├── cdp-discovery.ts          # CDP 端口动态发现（从 Chrome 进程参数提取）
│   ├── page-watcher.ts           # CDP 事件监听：Page.frameNavigated 自动触发
│   ├── screencast.ts             # Screencast 帧流管理：start/stop/ack
│   └── webview.ts                # WebView 面板创建和 HTML 生成
├── src/test/
│   ├── cdp-discovery.test.ts     # 端口发现单元测试
│   └── page-watcher.test.ts      # 事件监听单元测试
└── .vscodeignore                 # 打包排除规则
```

**设计决策：**
- `cdp-discovery.ts` 负责从 Chrome 进程参数动态发现 CDP 端口（Playwright MCP 使用随机端口，无法固定）
- `page-watcher.ts` 和 `screencast.ts` 分离：watcher 只做轻量事件监听（~0% CPU），screencast 仅在需要时启动（~2-5% CPU）
- WebView HTML 内联在 `webview.ts` 中（~30 行），无需额外 webview 资源目录
- 使用 esbuild 打包为单文件，减少插件体积

---

### Task 1: 项目脚手架

**Files:**
- Create: `dev_project/vscode-remote-viewer/package.json`
- Create: `dev_project/vscode-remote-viewer/tsconfig.json`
- Create: `dev_project/vscode-remote-viewer/esbuild.js`
- Create: `dev_project/vscode-remote-viewer/.vscodeignore`

- [ ] **Step 1: 创建 package.json**

```json
{
  "name": "remote-browser-viewer",
  "displayName": "Remote Browser Viewer",
  "description": "在 VSCode WebView 中实时查看 Playwright MCP 操控的浏览器画面",
  "version": "0.1.0",
  "publisher": "polarischen",
  "engines": { "vscode": "^1.85.0" },
  "categories": ["Other"],
  "activationEvents": ["onStartupFinished"],
  "main": "./dist/extension.js",
  "contributes": {
    "commands": [
      {
        "command": "remoteBrowser.open",
        "title": "Remote Browser: 打开浏览器视图"
      },
      {
        "command": "remoteBrowser.stop",
        "title": "Remote Browser: 停止 Screencast"
      }
    ],
    "configuration": {
      "title": "Remote Browser Viewer",
      "properties": {
        "remoteBrowser.autoOpen": {
          "type": "boolean",
          "default": true,
          "description": "检测到浏览器操作时自动打开视图"
        },
        "remoteBrowser.quality": {
          "type": "number",
          "default": 80,
          "minimum": 1,
          "maximum": 100,
          "description": "JPEG 质量 1-100"
        },
        "remoteBrowser.maxWidth": {
          "type": "number",
          "default": 1280,
          "description": "Screencast 最大宽度"
        },
        "remoteBrowser.maxHeight": {
          "type": "number",
          "default": 720,
          "description": "Screencast 最大高度"
        }
      }
    }
  },
  "scripts": {
    "build": "node esbuild.js",
    "watch": "node esbuild.js --watch",
    "test": "node --import tsx --test src/test/*.test.ts",
    "package": "vsce package"
  },
  "dependencies": {
    "ws": "^8.18.0"
  },
  "devDependencies": {
    "@types/vscode": "^1.85.0",
    "@types/ws": "^8.5.0",
    "esbuild": "^0.24.0",
    "tsx": "^4.19.0",
    "typescript": "^5.5.0"
  }
}
```

- [ ] **Step 2: 创建 tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "commonjs",
    "lib": ["ES2022"],
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "declaration": true,
    "sourceMap": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist", "src/test"]
}
```

- [ ] **Step 3: 创建 esbuild.js**

```javascript
const esbuild = require('esbuild');

const watch = process.argv.includes('--watch');

/** @type {import('esbuild').BuildOptions} */
const options = {
  entryPoints: ['src/extension.ts'],
  bundle: true,
  outfile: 'dist/extension.js',
  external: ['vscode'],
  format: 'cjs',
  platform: 'node',
  target: 'node18',
  sourcemap: true,
};

if (watch) {
  esbuild.context(options).then(ctx => {
    ctx.watch();
    console.log('Watching for changes...');
  });
} else {
  esbuild.build(options).then(() => console.log('Build complete'));
}
```

- [ ] **Step 4: 创建 .vscodeignore**

```
src/**
node_modules/**
tsconfig.json
esbuild.js
.gitignore
```

- [ ] **Step 5: 安装依赖并验证构建环境**

Run: `cd dev_project/vscode-remote-viewer && npm install`
Expected: 成功安装，无报错

- [ ] **Step 6: Commit**

```bash
git add dev_project/vscode-remote-viewer/package.json dev_project/vscode-remote-viewer/tsconfig.json dev_project/vscode-remote-viewer/esbuild.js dev_project/vscode-remote-viewer/.vscodeignore dev_project/vscode-remote-viewer/package-lock.json
git commit -m "feat(viewer): 初始化 VSCode Remote Browser Viewer 插件项目脚手架"
```

---

### Task 2: CDP 端口动态发现

**Files:**
- Create: `dev_project/vscode-remote-viewer/src/cdp-discovery.ts`
- Create: `dev_project/vscode-remote-viewer/src/test/cdp-discovery.test.ts`

- [ ] **Step 1: 编写 cdp-discovery.test.ts 测试**

```typescript
import { describe, it } from 'node:test';
import assert from 'node:assert';
import { parseCdpPortFromProcessLine, findCdpTargets } from '../cdp-discovery';

describe('parseCdpPortFromProcessLine', () => {
  it('should extract port from Chrome process line', () => {
    const line = 'user 12345 0.5 /Applications/Google Chrome.app --remote-debugging-port=59471 --headless';
    assert.strictEqual(parseCdpPortFromProcessLine(line), 59471);
  });

  it('should return null for line without port', () => {
    const line = 'user 12345 0.5 /usr/bin/node server.js';
    assert.strictEqual(parseCdpPortFromProcessLine(line), null);
  });

  it('should handle port at end of line', () => {
    const line = 'chrome --remote-debugging-port=9222';
    assert.strictEqual(parseCdpPortFromProcessLine(line), 9222);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd dev_project/vscode-remote-viewer && npx tsx --test src/test/cdp-discovery.test.ts`
Expected: FAIL — `parseCdpPortFromProcessLine` 不存在

- [ ] **Step 3: 实现 cdp-discovery.ts**

```typescript
import { execSync } from 'child_process';

export function parseCdpPortFromProcessLine(line: string): number | null {
  const match = line.match(/--remote-debugging-port=(\d+)/);
  return match ? parseInt(match[1], 10) : null;
}

export async function discoverCdpPort(): Promise<number> {
  try {
    const output = execSync(
      'ps aux | grep -i "[c]hrome\\|[c]hromium" | grep "remote-debugging-port"',
      { encoding: 'utf-8', timeout: 5000 }
    );
    for (const line of output.trim().split('\n')) {
      const port = parseCdpPortFromProcessLine(line);
      if (port) return port;
    }
  } catch {
    // ps 命令无结果或超时
  }
  throw new Error('未发现运行中的 Chrome/Chromium CDP 端口');
}

export interface CdpTarget {
  id: string;
  type: string;
  title: string;
  url: string;
  webSocketDebuggerUrl: string;
}

export async function findCdpTargets(port: number): Promise<CdpTarget[]> {
  const resp = await fetch(`http://127.0.0.1:${port}/json/list`);
  if (!resp.ok) throw new Error(`CDP HTTP ${resp.status}`);
  return resp.json();
}

export async function findPageTarget(port: number): Promise<CdpTarget> {
  const targets = await findCdpTargets(port);
  const page = targets.find(t => t.type === 'page');
  if (!page) throw new Error('未找到页面 target');
  return page;
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd dev_project/vscode-remote-viewer && npx tsx --test src/test/cdp-discovery.test.ts`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add dev_project/vscode-remote-viewer/src/cdp-discovery.ts dev_project/vscode-remote-viewer/src/test/cdp-discovery.test.ts
git commit -m "feat(viewer): 实现 CDP 端口动态发现（从 Chrome 进程参数提取）"
```

---

### Task 3: PageWatcher — CDP 事件监听

**Files:**
- Create: `dev_project/vscode-remote-viewer/src/page-watcher.ts`

- [ ] **Step 1: 实现 page-watcher.ts**

```typescript
import WebSocket from 'ws';
import { discoverCdpPort, findPageTarget } from './cdp-discovery';

export type BrowserActivatedCallback = (url: string) => void;
export type FrameCallback = (base64Data: string, sessionId: number) => void;

export class PageWatcher {
  private ws: WebSocket | undefined;
  private currentUrl = 'about:blank';
  private cmdId = 0;
  private onBrowserActivated: BrowserActivatedCallback | null = null;
  private onFrame: FrameCallback | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  private disposed = false;

  setOnActivated(cb: BrowserActivatedCallback) {
    this.onBrowserActivated = cb;
  }

  setOnFrame(cb: FrameCallback) {
    this.onFrame = cb;
  }

  async connect(): Promise<void> {
    this.closeWs();
    const port = await discoverCdpPort();
    const target = await findPageTarget(port);

    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(target.webSocketDebuggerUrl);

      this.ws.on('open', () => {
        this.sendCommand('Page.enable');
        this.sendCommand('Runtime.enable');
        resolve();
      });

      this.ws.on('message', (raw: Buffer) => {
        const msg = JSON.parse(raw.toString());
        this.handleMessage(msg);
      });

      this.ws.on('close', () => {
        if (!this.disposed) this.scheduleReconnect();
      });

      this.ws.on('error', (err) => {
        reject(err);
      });
    });
  }

  private handleMessage(msg: any) {
    if (msg.method === 'Page.frameNavigated') {
      const frame = msg.params.frame;
      if (frame.parentId) return; // 忽略 iframe
      const url = frame.url;
      if (url && url !== 'about:blank' && url !== this.currentUrl) {
        this.currentUrl = url;
        this.onBrowserActivated?.(url);
      }
    }

    if (msg.method === 'Page.screencastFrame') {
      const { data, sessionId } = msg.params;
      this.onFrame?.(data, sessionId);
      this.sendCommand('Page.screencastFrameAck', { sessionId });
    }
  }

  startScreencast(quality: number, maxWidth: number, maxHeight: number) {
    this.sendCommand('Page.startScreencast', {
      format: 'jpeg', quality, maxWidth, maxHeight,
    });
  }

  stopScreencast() {
    this.sendCommand('Page.stopScreencast');
  }

  sendCommand(method: string, params?: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ id: ++this.cmdId, method, params }));
    }
  }

  private scheduleReconnect() {
    if (this.disposed) return;
    this.reconnectTimer = setTimeout(() => {
      this.connect().catch(() => {
        this.scheduleReconnect();
      });
    }, 5000);
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  private closeWs() {
    if (this.ws) {
      this.ws.removeAllListeners();
      this.ws.close();
      this.ws = undefined;
    }
  }

  dispose() {
    this.disposed = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.closeWs();
  }
}
```

- [ ] **Step 2: 验证编译**

Run: `cd dev_project/vscode-remote-viewer && npx tsc --noEmit`
Expected: 无错误（或仅 vscode 模块 import 警告，因为还没写 extension.ts）

- [ ] **Step 3: Commit**

```bash
git add dev_project/vscode-remote-viewer/src/page-watcher.ts
git commit -m "feat(viewer): 实现 PageWatcher — CDP 事件监听和自动重连"
```

---

### Task 4: WebView 面板

**Files:**
- Create: `dev_project/vscode-remote-viewer/src/webview.ts`

- [ ] **Step 1: 实现 webview.ts**

```typescript
import * as vscode from 'vscode';

export function createViewerPanel(initialUrl?: string): vscode.WebviewPanel {
  let title = 'Remote Browser';
  if (initialUrl) {
    try { title = `Browser: ${new URL(initialUrl).hostname}`; }
    catch { title = `Browser: ${initialUrl.slice(0, 30)}`; }
  }

  const panel = vscode.window.createWebviewPanel(
    'remoteBrowserView',
    title,
    vscode.ViewColumn.Beside,
    { enableScripts: true, retainContextWhenHidden: true }
  );
  panel.webview.html = getHtml();
  return panel;
}

export function updatePanelTitle(panel: vscode.WebviewPanel, url: string) {
  try { panel.title = `Browser: ${new URL(url).hostname}`; }
  catch { panel.title = `Browser: ${url.slice(0, 30)}`; }
}

function getHtml(): string {
  return `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body {
    margin: 0; background: #1e1e1e;
    display: flex; flex-direction: column;
    align-items: center; height: 100vh;
    overflow: hidden; font-family: sans-serif;
  }
  #url {
    color: #888; font-size: 12px;
    padding: 6px 12px; width: 100%;
    text-align: center; background: #252526;
    border-bottom: 1px solid #333;
    white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis;
  }
  #screen {
    max-width: 100%; max-height: calc(100vh - 32px);
    object-fit: contain;
  }
  #status {
    color: #666; font-size: 11px; padding: 4px;
    position: absolute; bottom: 4px; right: 8px;
  }
</style>
</head>
<body>
  <div id="url">等待浏览器连接...</div>
  <img id="screen" />
  <div id="status"></div>
  <script>
    const vscode = acquireVsCodeApi();
    const img = document.getElementById('screen');
    const urlEl = document.getElementById('url');
    const statusEl = document.getElementById('status');
    let frameCount = 0;
    let lastFpsTime = Date.now();

    window.addEventListener('message', e => {
      const msg = e.data;
      if (msg.type === 'frame') {
        img.src = 'data:image/jpeg;base64,' + msg.data;
        frameCount++;
        const now = Date.now();
        if (now - lastFpsTime >= 1000) {
          statusEl.textContent = frameCount + ' fps';
          frameCount = 0;
          lastFpsTime = now;
        }
      }
      if (msg.type === 'url') {
        urlEl.textContent = msg.url;
      }
      if (msg.type === 'status') {
        statusEl.textContent = msg.text;
      }
    });
  </script>
</body>
</html>`;
}
```

- [ ] **Step 2: Commit**

```bash
git add dev_project/vscode-remote-viewer/src/webview.ts
git commit -m "feat(viewer): 实现 WebView 面板（URL 栏 + 帧渲染 + FPS 显示）"
```

---

### Task 5: 插件入口 — 整合所有模块

**Files:**
- Create: `dev_project/vscode-remote-viewer/src/extension.ts`

- [ ] **Step 1: 实现 extension.ts**

```typescript
import * as vscode from 'vscode';
import { PageWatcher } from './page-watcher';
import { createViewerPanel, updatePanelTitle } from './webview';

let pageWatcher: PageWatcher;
let panel: vscode.WebviewPanel | undefined;
let screencastActive = false;
let statusBarItem: vscode.StatusBarItem;

export function activate(ctx: vscode.ExtensionContext) {
  const config = vscode.workspace.getConfiguration('remoteBrowser');
  const autoOpen = config.get<boolean>('autoOpen', true);

  // 状态栏
  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBarItem.text = '$(globe) Browser: 未连接';
  statusBarItem.command = 'remoteBrowser.open';
  statusBarItem.show();
  ctx.subscriptions.push(statusBarItem);

  // PageWatcher
  pageWatcher = new PageWatcher();

  pageWatcher.setOnFrame((base64Data) => {
    panel?.webview.postMessage({ type: 'frame', data: base64Data });
  });

  if (autoOpen) {
    pageWatcher.setOnActivated((url) => {
      statusBarItem.text = `$(globe) Browser: ${shortenUrl(url)}`;
      if (panel) {
        updatePanelTitle(panel, url);
        panel.webview.postMessage({ type: 'url', url });
        if (!panel.visible) panel.reveal(vscode.ViewColumn.Beside);
      } else {
        openViewerWithScreencast(url);
      }
    });
  }

  // 启动 CDP 监听
  pageWatcher.connect().then(() => {
    statusBarItem.text = '$(globe) Browser: 已连接';
    vscode.window.showInformationMessage('Remote Browser Viewer: CDP 已连接');
  }).catch(() => {
    statusBarItem.text = '$(globe) Browser: 等待连接...';
  });

  // 命令注册
  ctx.subscriptions.push(
    vscode.commands.registerCommand('remoteBrowser.open', () => {
      openViewerWithScreencast();
    }),
    vscode.commands.registerCommand('remoteBrowser.stop', () => {
      if (screencastActive) {
        pageWatcher.stopScreencast();
        screencastActive = false;
        panel?.webview.postMessage({ type: 'status', text: 'Screencast 已停止' });
      }
    })
  );

  ctx.subscriptions.push({ dispose: () => pageWatcher.dispose() });
}

function openViewerWithScreencast(initialUrl?: string) {
  if (panel) {
    panel.reveal(vscode.ViewColumn.Beside);
  } else {
    panel = createViewerPanel(initialUrl);
    panel.onDidDispose(() => {
      panel = undefined;
      if (screencastActive) {
        pageWatcher.stopScreencast();
        screencastActive = false;
      }
    });
  }

  if (initialUrl) {
    panel.webview.postMessage({ type: 'url', url: initialUrl });
  }

  if (!screencastActive && pageWatcher.isConnected()) {
    const config = vscode.workspace.getConfiguration('remoteBrowser');
    const quality = config.get<number>('quality', 80);
    const maxWidth = config.get<number>('maxWidth', 1280);
    const maxHeight = config.get<number>('maxHeight', 720);
    pageWatcher.startScreencast(quality, maxWidth, maxHeight);
    screencastActive = true;
  }
}

function shortenUrl(url: string): string {
  try { return new URL(url).hostname; }
  catch { return url.slice(0, 20); }
}

export function deactivate() {
  pageWatcher?.dispose();
}
```

- [ ] **Step 2: 构建插件**

Run: `cd dev_project/vscode-remote-viewer && npm run build`
Expected: `Build complete`，生成 `dist/extension.js`

- [ ] **Step 3: Commit**

```bash
git add dev_project/vscode-remote-viewer/src/extension.ts
git commit -m "feat(viewer): 实现插件入口 — 整合 CDP 发现、事件监听、Screencast 和 WebView"
```

---

### Task 6: 端到端验证

**Files:**
- 无新建文件，验证已有代码

- [ ] **Step 1: 确认构建无错误**

Run: `cd dev_project/vscode-remote-viewer && npm run build`
Expected: `Build complete`，无 error

- [ ] **Step 2: 确认 TypeScript 类型检查通过**

Run: `cd dev_project/vscode-remote-viewer && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 3: 运行单元测试**

Run: `cd dev_project/vscode-remote-viewer && npm test`
Expected: 所有测试通过

- [ ] **Step 4: 验证插件能加载到 VSCode**

手动步骤：
1. 在 VSCode 中打开 `dev_project/vscode-remote-viewer` 目录
2. 按 `F5` 启动 Extension Development Host
3. 在新窗口中按 `Ctrl+Shift+P` 输入 `Remote Browser: 打开浏览器视图`
4. 如果 Playwright 已启动 Chrome，应看到 WebView 面板出现并显示画面
5. 检查状态栏是否显示 `Browser: 已连接` 或 `Browser: 等待连接...`

- [ ] **Step 5: 验证自动触发**

手动步骤：
1. 保持 Viewer 插件运行
2. 在另一个 VSCode 窗口中用 Claude Code 调用 Playwright `browser_navigate` 打开网页
3. 观察 Viewer 插件是否自动弹出 WebView 并显示实时画面

- [ ] **Step 6: 最终 Commit**

```bash
git add dev_project/vscode-remote-viewer/
git commit -m "feat(viewer): Remote Browser Viewer MVP 完成 — CDP 发现 + 事件监听 + Screencast + WebView"
```

---

## 后续迭代（不在 MVP 范围内）

- **双向交互**：在 WebView 中点击/输入，通过 `Input.dispatchMouseEvent` 反向控制浏览器
- **多 Tab 支持**：监听 `Target.targetCreated`，支持切换 Tab
- **VSIX 打包发布**：`vsce package` 生成安装包
