import * as vscode from 'vscode';
import { PageWatcher, type TabInfo } from './page-watcher';
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
  statusBarItem.tooltip = '点击打开 Remote Browser Viewer';
  statusBarItem.show();
  ctx.subscriptions.push(statusBarItem);

  // PageWatcher
  pageWatcher = new PageWatcher();

  // 帧回调（含 metadata 用于坐标转换）
  pageWatcher.setOnFrame((base64Data, _sessionId, metadata) => {
    panel?.webview.postMessage({ type: 'frame', data: base64Data, metadata });
  });

  // Tab 变化回调
  pageWatcher.setOnTabsChanged((tabs) => {
    updateStatusBar(tabs);
    panel?.webview.postMessage({
      type: 'tabs',
      tabs,
      activeTargetId: pageWatcher.getActiveTargetId(),
    });
  });

  // 重连回调 — 解决问题1
  pageWatcher.setOnReconnected(() => {
    statusBarItem.text = '$(globe) Browser: 已重连';
    // 重置 screencast 状态，重新启动
    screencastActive = false;
    if (panel) {
      startScreencastIfNeeded();
      panel.webview.postMessage({ type: 'status', text: 'CDP 已重连' });
    }
  });

  // 浏览器激活回调
  if (autoOpen) {
    pageWatcher.setOnActivated((url) => {
      statusBarItem.text = `$(globe) Browser: ${shortenUrl(url)}`;
      if (panel) {
        updatePanelTitle(panel, url);
        panel.webview.postMessage({ type: 'url', url });
        if (!panel.visible) panel.reveal(vscode.ViewColumn.Beside);
        startScreencastIfNeeded();
      } else {
        openViewerWithScreencast(url);
      }
    });
  }

  // 启动 CDP 监听（失败则自动轮询重试）
  pageWatcher.connect().then(() => {
    const tabs = pageWatcher.getTabs();
    updateStatusBar(tabs);
    vscode.window.showInformationMessage(`Remote Browser Viewer: CDP 已连接 (${tabs.length} 个标签页)`);
  }).catch(() => {
    statusBarItem.text = '$(globe) Browser: 等待连接...';
    // Chrome 未运行时启动后台轮询，每 3 秒重试
    pageWatcher.startPolling();
  });

  // 命令注册
  ctx.subscriptions.push(
    // 打开 Viewer
    vscode.commands.registerCommand('remoteBrowser.open', () => {
      openViewerWithScreencast();
    }),
    // 停止 Screencast
    vscode.commands.registerCommand('remoteBrowser.stop', () => {
      if (screencastActive) {
        pageWatcher.stopScreencast();
        screencastActive = false;
        panel?.webview.postMessage({ type: 'status', text: 'Screencast 已停止' });
      }
    }),
    // 刷新连接
    vscode.commands.registerCommand('remoteBrowser.refresh', async () => {
      statusBarItem.text = '$(sync~spin) Browser: 重新连接...';
      try {
        await pageWatcher.connect();
        const tabs = pageWatcher.getTabs();
        updateStatusBar(tabs);
        screencastActive = false;
        if (panel) startScreencastIfNeeded();
        vscode.window.showInformationMessage(`Remote Browser Viewer: 刷新成功 (${tabs.length} 个标签页)`);
      } catch {
        statusBarItem.text = '$(globe) Browser: 连接失败';
        vscode.window.showWarningMessage('Remote Browser Viewer: 无法连接到 Chrome CDP');
      }
    }),
    // 显示状态 — 解决问题2
    vscode.commands.registerCommand('remoteBrowser.status', async () => {
      const connected = pageWatcher.isConnected();
      const pageConnected = pageWatcher.isPageConnected();
      const tabs = pageWatcher.getTabs();
      const activeId = pageWatcher.getActiveTargetId();

      const items: string[] = [
        `浏览器连接: ${connected ? '✅ 已连接' : '❌ 未连接'}`,
        `页面连接: ${pageConnected ? '✅ 已连接' : '❌ 未连接'}`,
        `标签页数: ${tabs.length}`,
        `Screencast: ${screencastActive ? '▶ 运行中' : '⏹ 已停止'}`,
        '',
        ...tabs.map(t => `${t.targetId === activeId ? '👉 ' : '   '}${t.title || t.url}`),
      ];

      vscode.window.showInformationMessage(items.join('\n'), { modal: true });
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
    // 注册 webview 消息监听
    panel.webview.onDidReceiveMessage((msg) => {
      if (msg.type === 'switchTab') {
        handleTabSwitch(msg.targetId);
      }
      if (msg.type === 'requestRefresh') {
        vscode.commands.executeCommand('remoteBrowser.refresh');
      }
      if (msg.type === 'closeTab') {
        pageWatcher.closeTarget(msg.targetId);
      }
      // 导航
      if (msg.type === 'navigate') {
        pageWatcher.navigate(msg.url);
      }
      if (msg.type === 'goBack') {
        pageWatcher.goBack();
      }
      if (msg.type === 'goForward') {
        pageWatcher.goForward();
      }
      if (msg.type === 'reload') {
        pageWatcher.reload();
      }
      // 鼠标事件
      if (msg.type === 'mouseEvent') {
        handleMouseEvent(msg);
      }
      // 键盘事件
      if (msg.type === 'keyEvent') {
        handleKeyEvent(msg);
      }
      // IME 中文输入
      if (msg.type === 'imeCommit') {
        pageWatcher.insertText(msg.text);
      }
    });
    // 发送当前 tab 列表
    const tabs = pageWatcher.getTabs();
    panel.webview.postMessage({
      type: 'tabs',
      tabs,
      activeTargetId: pageWatcher.getActiveTargetId(),
    });
    // 发送连接状态
    panel.webview.postMessage({
      type: 'connectionStatus',
      connected: pageWatcher.isConnected(),
      pageConnected: pageWatcher.isPageConnected(),
    });
  }

  if (initialUrl) {
    panel.webview.postMessage({ type: 'url', url: initialUrl });
  }

  startScreencastIfNeeded();
}

async function handleTabSwitch(targetId: string) {
  try {
    screencastActive = false;
    pageWatcher.stopScreencast();
    await pageWatcher.switchToTarget(targetId);
    startScreencastIfNeeded();
    const tabs = pageWatcher.getTabs();
    const tab = tabs.find(t => t.targetId === targetId);
    if (tab && panel) {
      updatePanelTitle(panel, tab.url);
      panel.webview.postMessage({ type: 'url', url: tab.url });
    }
  } catch (err: any) {
    panel?.webview.postMessage({ type: 'status', text: `切换失败: ${err.message}` });
  }
}

function startScreencastIfNeeded() {
  if (!screencastActive && pageWatcher.isPageConnected()) {
    const config = vscode.workspace.getConfiguration('remoteBrowser');
    const quality = config.get<number>('quality', 80);
    const maxWidth = config.get<number>('maxWidth', 1280);
    const maxHeight = config.get<number>('maxHeight', 720);
    pageWatcher.startScreencast(quality, maxWidth, maxHeight);
    screencastActive = true;
  }
}

function updateStatusBar(tabs: TabInfo[]) {
  const connected = pageWatcher.isConnected();
  if (!connected) {
    statusBarItem.text = '$(globe) Browser: 未连接';
    statusBarItem.tooltip = '点击打开 Remote Browser Viewer\n状态: 未连接';
    return;
  }
  const count = tabs.length;
  const activeTab = tabs.find(t => t.targetId === pageWatcher.getActiveTargetId());
  const host = activeTab ? shortenUrl(activeTab.url) : '已连接';
  statusBarItem.text = `$(globe) ${host} [${count}]`;
  statusBarItem.tooltip = [
    '点击打开 Remote Browser Viewer',
    `状态: 已连接`,
    `标签页: ${count}`,
    ...tabs.map(t => `  ${t.targetId === pageWatcher.getActiveTargetId() ? '▶' : '•'} ${t.title || t.url}`),
  ].join('\n');
}

function handleMouseEvent(msg: any) {
  const { action, x, y, button, clickCount, deltaX, deltaY } = msg;
  switch (action) {
    case 'mousePressed':
      pageWatcher.dispatchMouseEvent('mousePressed', x, y, button, clickCount || 1);
      break;
    case 'mouseReleased':
      pageWatcher.dispatchMouseEvent('mouseReleased', x, y, button, clickCount || 1);
      break;
    case 'dblclick':
      pageWatcher.dispatchMouseEvent('mousePressed', x, y, button, 2);
      pageWatcher.dispatchMouseEvent('mouseReleased', x, y, button, 2);
      break;
    case 'move':
      pageWatcher.dispatchMouseEvent('mouseMoved', x, y, button || 'none');
      break;
    case 'wheel':
      pageWatcher.dispatchMouseEvent('mouseWheel', x, y, 'none', 0, deltaX, deltaY);
      break;
  }
}

function handleKeyEvent(msg: any) {
  const { action, key, code, text, modifiers } = msg;
  switch (action) {
    case 'keyDown':
      pageWatcher.dispatchKeyEvent('keyDown', key, code, undefined, modifiers);
      break;
    case 'char':
      pageWatcher.dispatchKeyEvent('char', key, code, text, modifiers);
      break;
    case 'keyUp':
      pageWatcher.dispatchKeyEvent('keyUp', key, code, undefined, modifiers);
      break;
  }
}

function shortenUrl(url: string): string {
  try { return new URL(url).hostname; }
  catch { return url.slice(0, 20); }
}

export function deactivate() {
  pageWatcher?.dispose();
}
