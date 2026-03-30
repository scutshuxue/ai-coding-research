# 开发指南

## 1. 环境准备

### 依赖安装

```bash
cd dev_project/vscode-remote-viewer
npm install
```

### 技术栈

| 组件 | 版本 | 用途 |
|------|------|------|
| TypeScript | 5.5+ | 开发语言 |
| esbuild | 0.25+ | 打包（bundle to dist/extension.js） |
| ws | 8.18+ | WebSocket 客户端（CDP 连接） |
| VSCode Extension API | 1.85+ | 插件 API |
| Node.js native test | 18+ | 单元测试框架 |
| tsx | 4.19+ | 测试时 TypeScript 加载器 |

## 2. 项目结构

```
vscode-remote-viewer/
├── src/
│   ├── extension.ts          # 插件入口，activate/deactivate
│   ├── page-watcher.ts       # 双层 CDP WebSocket 管理
│   ├── cdp-discovery.ts      # CDP 端口发现 + Target 查询
│   ├── webview.ts            # WebView HTML 生成
│   └── test/
│       └── cdp-discovery.test.ts  # 单元测试
├── dist/
│   └── extension.js          # esbuild 打包输出
├── docs/
│   ├── architecture.md       # 架构设计
│   ├── user-guide.md         # 用户指南
│   ├── development.md        # 本文件
│   └── cdp-protocol.md       # CDP 协议参考
├── .vscode/
│   └── launch.json           # F5 调试配置
├── package.json              # 插件清单 + npm 配置
├── tsconfig.json             # TypeScript 编译配置
├── esbuild.js                # 构建脚本
└── README.md                 # 项目 README
```

## 3. 构建

### 单次构建

```bash
npm run build
```

执行 `esbuild.js`，将 `src/extension.ts` 及其依赖打包为 `dist/extension.js`（CommonJS 格式，Node.js 18 target）。

### Watch 模式

```bash
npm run watch
```

文件变化时自动重新构建，适合开发时使用。

### 构建配置（esbuild.js）

```javascript
const options = {
    entryPoints: ['src/extension.ts'],
    bundle: true,
    outfile: 'dist/extension.js',
    external: ['vscode'],        // VSCode API 不打包
    format: 'cjs',               // CommonJS
    platform: 'node',
    target: 'node18',
    sourcemap: true,
};
```

关键点：
- `external: ['vscode']`：VSCode API 由运行时提供，不打包
- `format: 'cjs'`：Extension Host 要求 CommonJS
- `sourcemap: true`：生成 source map 便于调试

## 4. 测试

### 运行测试

```bash
npm test
```

使用 Node.js 内置 `test` 模块 + `tsx` TypeScript 加载器：

```bash
node --import tsx --test src/test/*.test.ts
```

### 测试文件

目前测试覆盖 `cdp-discovery.ts` 的纯函数：

```typescript
// src/test/cdp-discovery.test.ts
describe('parseCdpPortFromProcessLine', () => {
  it('should extract port from Chrome process line');
  it('should return null for line without port');
  it('should handle port at end of line');
});
```

### 添加测试

在 `src/test/` 下创建 `*.test.ts` 文件，会被自动发现：

```typescript
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

describe('myModule', () => {
  it('should do something', () => {
    assert.equal(1 + 1, 2);
  });
});
```

### 测试局限性

由于 `vscode` 模块只在 Extension Host 中可用，涉及 VSCode API 的模块（extension.ts, webview.ts）无法在普通 Node.js 环境中进行单元测试。建议：

- 纯逻辑函数抽取到独立模块中测试（如 cdp-discovery.ts）
- VSCode 集成部分通过 F5 调试手动验证
- 未来可引入 `@vscode/test-electron` 进行集成测试

## 5. 调试

### F5 调试

`.vscode/launch.json` 已配置 Extension Development Host：

1. 按 `F5` 启动新的 VSCode 窗口（Extension Development Host）
2. 新窗口中自动加载本插件
3. 在源码中设置断点
4. Debug Console 查看日志输出

### 日志查看

在目标 VSCode 中查看 Extension Host 日志：

```
Ctrl+Shift+P → Developer: Show Logs... → Extension Host
```

### 手动触发

调试时可以手动模拟 CDP 连接：

```bash
# 启动一个带 CDP 的 Chrome（macOS）
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 --headless

# 验证 CDP 可达
curl http://127.0.0.1:9222/json/version
curl http://127.0.0.1:9222/json/list
```

## 6. 打包

### 生成 .vsix

```bash
npm run package
```

使用 `vsce package` 生成 `.vsix` 文件。需要全局安装 vsce：

```bash
npm install -g @vscode/vsce
```

### 安装到远程

```bash
# 方式一：通过命令行
code --install-extension remote-browser-viewer-0.1.0.vsix

# 方式二：通过 VSCode UI
# Ctrl+Shift+P → Extensions: Install from VSIX...
```

注意：此插件设计为运行在 **Remote Extension Host** 上，安装时应在 Remote SSH 连接的 VSCode 中进行。

## 7. 代码规范

### 模块划分原则

| 模块 | 职责边界 | 依赖 |
|------|---------|------|
| cdp-discovery.ts | 纯 CDP 发现逻辑，无 VSCode 依赖 | child_process, fetch |
| page-watcher.ts | CDP 连接管理，无 VSCode 依赖 | ws, cdp-discovery |
| webview.ts | WebView 创建和 HTML 生成 | vscode |
| extension.ts | 胶水层：协调所有模块 | vscode, page-watcher, webview |

设计目标：`cdp-discovery` 和 `page-watcher` 可独立于 VSCode 测试。

### 消息协议

Extension ↔ WebView 通过 `postMessage` 通信，消息类型：

**Extension → WebView**:

| type | 字段 | 说明 |
|------|------|------|
| `frame` | `data: string` | base64 JPEG 帧 |
| `url` | `url: string` | 当前页面 URL |
| `tabs` | `tabs: TabInfo[], activeTargetId: string` | Tab 列表更新 |
| `connectionStatus` | `connected: boolean, pageConnected: boolean` | 连接状态 |
| `status` | `text: string` | 通用状态文本（5秒自动清除） |

**WebView → Extension**:

| type | 字段 | 说明 |
|------|------|------|
| `switchTab` | `targetId: string` | 切换到指定 tab |
| `requestRefresh` | — | 请求刷新连接 |

### 错误处理

- CDP 连接失败：静默重试（5秒间隔），不弹窗打扰用户
- Tab 切换失败：通过 `status` 消息在 WebView 状态栏显示错误
- `refreshTabs()` 失败：静默忽略，不阻塞主流程

## 8. 开发路线图

### 已实现

- [x] CDP Screencast 实时帧传输
- [x] 自动触发（Page.frameNavigated 事件检测）
- [x] 状态栏集成
- [x] 自动重连
- [x] 多标签页支持（Target 域监听 + Tab 栏 UI）
- [x] 弹出页面捕获（Target.targetCreated）
- [x] 连接状态可视化（指示灯 + 状态栏 + 详情弹窗）
- [x] 手动刷新连接

### 待实现

- [ ] 双向交互：点击 WebView 画面映射为浏览器操作
- [ ] 鼠标光标显示：在画面上叠加光标位置
- [ ] 键盘输入转发
- [ ] 面板缩放控制
- [ ] 自动固定 CDP 端口配置
- [ ] `@vscode/test-electron` 集成测试
- [ ] VSIX 发布到 Marketplace
