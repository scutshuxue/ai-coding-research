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
