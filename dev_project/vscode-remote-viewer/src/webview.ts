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
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #1e1e1e;
    display: flex; flex-direction: column;
    height: 100vh; overflow: hidden;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    color: #ccc;
  }

  /* 顶部工具栏 */
  #toolbar {
    display: flex; align-items: center;
    background: #252526; border-bottom: 1px solid #333;
    padding: 0 8px; height: 32px; gap: 8px;
    flex-shrink: 0;
  }
  #connection-indicator {
    width: 8px; height: 8px; border-radius: 50%;
    background: #666; flex-shrink: 0;
  }
  #connection-indicator.connected { background: #4ec94e; }
  #connection-indicator.disconnected { background: #e74c3c; }
  #connection-indicator.connecting { background: #f1c40f; animation: blink 1s infinite; }
  @keyframes blink { 50% { opacity: 0.4; } }

  #url {
    color: #aaa; font-size: 12px;
    flex: 1; overflow: hidden;
    white-space: nowrap; text-overflow: ellipsis;
  }
  #refresh-btn {
    background: none; border: 1px solid #555;
    color: #aaa; font-size: 11px; padding: 2px 8px;
    border-radius: 3px; cursor: pointer; flex-shrink: 0;
  }
  #refresh-btn:hover { background: #333; color: #fff; }

  /* Tab 栏 */
  #tab-bar {
    display: none; /* 只有多tab时显示 */
    background: #2d2d2d; border-bottom: 1px solid #333;
    overflow-x: auto; white-space: nowrap;
    flex-shrink: 0; height: 28px;
    scrollbar-width: thin;
  }
  #tab-bar.visible { display: flex; }
  .tab {
    display: inline-flex; align-items: center;
    padding: 0 12px; height: 28px;
    font-size: 11px; color: #888;
    cursor: pointer; border-right: 1px solid #333;
    max-width: 180px; overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap;
    flex-shrink: 0;
  }
  .tab:hover { background: #333; color: #ccc; }
  .tab.active {
    background: #1e1e1e; color: #fff;
    border-bottom: 2px solid #007acc;
  }

  /* 画面区 */
  #screen-container {
    flex: 1; display: flex;
    align-items: center; justify-content: center;
    overflow: hidden; position: relative;
  }
  #screen {
    max-width: 100%; max-height: 100%;
    object-fit: contain;
  }
  #placeholder {
    color: #666; font-size: 14px; text-align: center;
    line-height: 1.8;
  }

  /* 底部状态栏 */
  #status-bar {
    display: flex; align-items: center; justify-content: space-between;
    background: #252526; border-top: 1px solid #333;
    padding: 0 8px; height: 22px; flex-shrink: 0;
    font-size: 11px; color: #666;
  }
  #status-left { display: flex; gap: 12px; }
  #status-right { display: flex; gap: 12px; }
</style>
</head>
<body>
  <!-- 工具栏 -->
  <div id="toolbar">
    <div id="connection-indicator" class="disconnected" title="连接状态"></div>
    <div id="url">等待浏览器连接...</div>
    <button id="refresh-btn" title="刷新连接">↻ 刷新</button>
  </div>

  <!-- Tab 栏 -->
  <div id="tab-bar"></div>

  <!-- 画面 -->
  <div id="screen-container">
    <div id="placeholder">
      等待浏览器连接...<br>
      <span style="font-size:12px; color:#555">Chrome 未运行或 CDP 未就绪</span>
    </div>
    <img id="screen" style="display:none" />
  </div>

  <!-- 状态栏 -->
  <div id="status-bar">
    <div id="status-left">
      <span id="conn-status">未连接</span>
      <span id="tab-count"></span>
    </div>
    <div id="status-right">
      <span id="fps-counter"></span>
      <span id="extra-status"></span>
    </div>
  </div>

  <script>
    const vscode = acquireVsCodeApi();
    const img = document.getElementById('screen');
    const placeholder = document.getElementById('placeholder');
    const urlEl = document.getElementById('url');
    const indicator = document.getElementById('connection-indicator');
    const tabBar = document.getElementById('tab-bar');
    const connStatus = document.getElementById('conn-status');
    const tabCountEl = document.getElementById('tab-count');
    const fpsCounter = document.getElementById('fps-counter');
    const extraStatus = document.getElementById('extra-status');
    const refreshBtn = document.getElementById('refresh-btn');

    let frameCount = 0;
    let lastFpsTime = Date.now();
    let hasReceivedFrame = false;

    // 刷新按钮
    refreshBtn.addEventListener('click', () => {
      vscode.postMessage({ type: 'requestRefresh' });
      indicator.className = 'connecting';
      connStatus.textContent = '重新连接...';
    });

    window.addEventListener('message', e => {
      const msg = e.data;

      // 帧数据
      if (msg.type === 'frame') {
        if (!hasReceivedFrame) {
          hasReceivedFrame = true;
          img.style.display = 'block';
          placeholder.style.display = 'none';
        }
        img.src = 'data:image/jpeg;base64,' + msg.data;
        frameCount++;
        const now = Date.now();
        if (now - lastFpsTime >= 1000) {
          fpsCounter.textContent = frameCount + ' fps';
          frameCount = 0;
          lastFpsTime = now;
        }
      }

      // URL 更新
      if (msg.type === 'url') {
        urlEl.textContent = msg.url;
      }

      // Tab 列表更新
      if (msg.type === 'tabs') {
        renderTabs(msg.tabs, msg.activeTargetId);
      }

      // 连接状态
      if (msg.type === 'connectionStatus') {
        updateConnectionStatus(msg.connected, msg.pageConnected);
      }

      // 通用状态
      if (msg.type === 'status') {
        extraStatus.textContent = msg.text;
        setTimeout(() => { extraStatus.textContent = ''; }, 5000);
      }
    });

    function renderTabs(tabs, activeTargetId) {
      tabBar.innerHTML = '';
      if (tabs.length <= 1) {
        tabBar.classList.remove('visible');
        tabCountEl.textContent = '';
        return;
      }
      tabBar.classList.add('visible');
      tabCountEl.textContent = tabs.length + ' tabs';

      tabs.forEach(tab => {
        const el = document.createElement('div');
        el.className = 'tab' + (tab.targetId === activeTargetId ? ' active' : '');
        const label = tab.title || shortenUrl(tab.url) || tab.targetId.slice(0, 8);
        el.textContent = label;
        el.title = tab.url;
        el.addEventListener('click', () => {
          vscode.postMessage({ type: 'switchTab', targetId: tab.targetId });
        });
        tabBar.appendChild(el);
      });
    }

    function updateConnectionStatus(connected, pageConnected) {
      if (connected && pageConnected) {
        indicator.className = 'connected';
        connStatus.textContent = '已连接';
        placeholder.innerHTML = '已连接，等待画面...';
      } else if (connected) {
        indicator.className = 'connecting';
        connStatus.textContent = '浏览器已连接，页面未就绪';
      } else {
        indicator.className = 'disconnected';
        connStatus.textContent = '未连接';
        if (!hasReceivedFrame) {
          placeholder.innerHTML = '等待浏览器连接...<br><span style="font-size:12px; color:#555">Chrome 未运行或 CDP 未就绪</span>';
        }
      }
    }

    function shortenUrl(url) {
      try { return new URL(url).hostname; }
      catch { return url ? url.slice(0, 30) : ''; }
    }
  </script>
</body>
</html>`;
}
