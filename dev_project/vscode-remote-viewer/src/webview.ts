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

  .nav-btn {
    background: none; border: none;
    color: #aaa; font-size: 14px; padding: 2px 6px;
    cursor: pointer; flex-shrink: 0; border-radius: 3px;
  }
  .nav-btn:hover { background: #3a3a3a; color: #fff; }
  #url-input {
    flex: 1; background: #333; border: 1px solid #444;
    color: #ddd; font-size: 12px; padding: 2px 8px;
    border-radius: 3px; outline: none; min-width: 0;
  }
  #url-input:focus { border-color: #007acc; }
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
    padding: 0 8px 0 12px; height: 28px;
    font-size: 11px; color: #888;
    cursor: pointer; border-right: 1px solid #333;
    max-width: 200px; flex-shrink: 0; gap: 4px;
  }
  .tab-title {
    overflow: hidden; text-overflow: ellipsis;
    white-space: nowrap; flex: 1;
  }
  .tab-close {
    width: 16px; height: 16px; border: none;
    background: none; color: #666; font-size: 12px;
    cursor: pointer; border-radius: 3px;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0; padding: 0;
  }
  .tab-close:hover { background: #555; color: #fff; }
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
  #overlay {
    position: absolute; top: 0; left: 0;
    width: 100%; height: 100%;
    cursor: default; outline: none;
    z-index: 10;
  }
  #ime-bar {
    position: absolute; bottom: 28px; left: 0; right: 0;
    display: flex; align-items: center; gap: 4px;
    background: #2d2d2d; border-top: 1px solid #007acc;
    padding: 4px 8px; z-index: 20;
  }
  #ime-bar input {
    flex: 1; background: #333; border: 1px solid #555;
    color: #ddd; font-size: 13px; padding: 4px 8px;
    border-radius: 3px; outline: none;
  }
  #ime-bar input:focus { border-color: #007acc; }
  #ime-bar button {
    background: #007acc; border: none; color: #fff;
    font-size: 12px; padding: 4px 10px; border-radius: 3px;
    cursor: pointer;
  }
  #ime-bar button:hover { background: #005fa3; }
  #ime-close { background: #555 !important; }
  #ime-close:hover { background: #777 !important; }
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
  #status-left { display: flex; gap: 12px; align-items: center; }
  #status-right { display: flex; gap: 12px; }
  #hints { color: #555; cursor: help; border-left: 1px solid #444; padding-left: 10px; }
</style>
</head>
<body>
  <!-- 工具栏 -->
  <div id="toolbar">
    <div id="connection-indicator" class="disconnected" title="连接状态"></div>
    <button class="nav-btn" id="back-btn" title="后退">←</button>
    <button class="nav-btn" id="forward-btn" title="前进">→</button>
    <button class="nav-btn" id="reload-btn" title="刷新页面">↻</button>
    <input id="url-input" type="text" placeholder="输入 URL 后回车..." />
    <button id="refresh-btn" title="刷新 CDP 连接">⟳</button>
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
    <div id="overlay" tabindex="0"></div>
    <div id="ime-bar" style="display:none;">
      <input id="ime-input" type="text" placeholder="输入文字后按回车发送..." />
      <button id="ime-send">发送</button>
      <button id="ime-close">✕</button>
    </div>
  </div>

  <!-- 状态栏 -->
  <div id="status-bar">
    <div id="status-left">
      <span id="conn-status">未连接</span>
      <span id="tab-count"></span>
      <span id="hints" title="点击=操作页面 | Ctrl+I=中文输入 | Ctrl+V=粘贴 | 地址栏回车=导航">点击操作 | Ctrl+I 中文 | Ctrl+V 粘贴</span>
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
    const urlInput = document.getElementById('url-input');
    const indicator = document.getElementById('connection-indicator');
    const tabBar = document.getElementById('tab-bar');
    const connStatus = document.getElementById('conn-status');
    const tabCountEl = document.getElementById('tab-count');
    const fpsCounter = document.getElementById('fps-counter');
    const extraStatus = document.getElementById('extra-status');
    const refreshBtn = document.getElementById('refresh-btn');
    const overlay = document.getElementById('overlay');
    const backBtn = document.getElementById('back-btn');
    const forwardBtn = document.getElementById('forward-btn');
    const reloadBtn = document.getElementById('reload-btn');

    let frameCount = 0;
    let lastFpsTime = Date.now();
    let hasReceivedFrame = false;
    let lastMetadata = null; // screencast metadata for coordinate mapping

    // ===== 导航按钮 =====
    backBtn.addEventListener('click', () => vscode.postMessage({ type: 'goBack' }));
    forwardBtn.addEventListener('click', () => vscode.postMessage({ type: 'goForward' }));
    reloadBtn.addEventListener('click', () => vscode.postMessage({ type: 'reload' }));
    refreshBtn.addEventListener('click', () => {
      vscode.postMessage({ type: 'requestRefresh' });
      indicator.className = 'connecting';
      connStatus.textContent = '重新连接...';
    });

    // 地址栏回车导航
    urlInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        let url = urlInput.value.trim();
        if (url && !url.match(/^https?:\\/\\//)) url = 'https://' + url;
        if (url) vscode.postMessage({ type: 'navigate', url });
      }
    });

    // ===== 坐标转换 =====
    function mapToPage(clientX, clientY) {
      if (!lastMetadata) return null;
      const rect = img.getBoundingClientRect();
      const imgAspect = img.naturalWidth / img.naturalHeight;
      const containerAspect = rect.width / rect.height;
      let renderW, renderH, offX, offY;
      if (imgAspect > containerAspect) {
        renderW = rect.width;
        renderH = rect.width / imgAspect;
      } else {
        renderH = rect.height;
        renderW = rect.height * imgAspect;
      }
      offX = (rect.width - renderW) / 2;
      offY = (rect.height - renderH) / 2;
      const relX = clientX - rect.left - offX;
      const relY = clientY - rect.top - offY;
      if (relX < 0 || relY < 0 || relX > renderW || relY > renderH) return null;
      return {
        x: Math.round(relX / renderW * lastMetadata.deviceWidth),
        y: Math.round(relY / renderH * lastMetadata.deviceHeight),
      };
    }

    // ===== 鼠标事件（支持拖动） =====
    let isDragging = false;
    let dragButton = 'left';
    let lastMoveTime = 0;

    overlay.addEventListener('mousedown', (e) => {
      overlay.focus();
      const pt = mapToPage(e.clientX, e.clientY);
      if (!pt) return;
      isDragging = true;
      dragButton = e.button === 2 ? 'right' : 'left';
      vscode.postMessage({ type: 'mouseEvent', action: 'mousePressed', x: pt.x, y: pt.y, button: dragButton, clickCount: 1 });
    });

    overlay.addEventListener('mousemove', (e) => {
      const now = Date.now();
      if (now - lastMoveTime < 50) return;
      lastMoveTime = now;
      const pt = mapToPage(e.clientX, e.clientY);
      if (!pt) return;
      // 拖动中发 mouseMoved，否则只是 hover
      vscode.postMessage({ type: 'mouseEvent', action: 'move', x: pt.x, y: pt.y, button: isDragging ? dragButton : 'none' });
    });

    overlay.addEventListener('mouseup', (e) => {
      const pt = mapToPage(e.clientX, e.clientY);
      if (!pt) return;
      const btn = e.button === 2 ? 'right' : 'left';
      vscode.postMessage({ type: 'mouseEvent', action: 'mouseReleased', x: pt.x, y: pt.y, button: btn, clickCount: 1 });
      isDragging = false;
    });

    overlay.addEventListener('dblclick', (e) => {
      const pt = mapToPage(e.clientX, e.clientY);
      if (!pt) return;
      vscode.postMessage({ type: 'mouseEvent', action: 'dblclick', x: pt.x, y: pt.y, button: 'left', clickCount: 2 });
    });

    overlay.addEventListener('contextmenu', (e) => {
      e.preventDefault();
    });

    // scroll
    overlay.addEventListener('wheel', (e) => {
      e.preventDefault();
      const pt = mapToPage(e.clientX, e.clientY);
      if (!pt) return;
      vscode.postMessage({ type: 'mouseEvent', action: 'wheel', x: pt.x, y: pt.y, deltaX: e.deltaX, deltaY: e.deltaY });
    }, { passive: false });

    // ===== 键盘事件（overlay 直接处理） =====
    const imeBar = document.getElementById('ime-bar');
    const imeInput = document.getElementById('ime-input');
    const imeSend = document.getElementById('ime-send');
    const imeClose = document.getElementById('ime-close');

    function getModifiers(e) {
      return (e.altKey ? 1 : 0) | (e.ctrlKey ? 2 : 0) | (e.metaKey ? 4 : 0) | (e.shiftKey ? 8 : 0);
    }

    overlay.addEventListener('keydown', (e) => {
      // Ctrl+V / Cmd+V: 粘贴
      if ((e.ctrlKey || e.metaKey) && e.key === 'v') {
        e.preventDefault();
        navigator.clipboard.readText().then(text => {
          if (text) vscode.postMessage({ type: 'imeCommit', text });
        }).catch(() => {});
        return;
      }
      // Ctrl+I / Cmd+I: 打开 IME 输入栏（中文输入）
      if ((e.ctrlKey || e.metaKey) && e.key === 'i') {
        e.preventDefault();
        imeBar.style.display = 'flex';
        imeInput.focus();
        return;
      }
      // 其他 Ctrl/Cmd 组合键交给 VSCode
      if (e.ctrlKey || e.metaKey) return;

      e.preventDefault();
      vscode.postMessage({ type: 'keyEvent', action: 'keyDown', key: e.key, code: e.code, modifiers: getModifiers(e) });
      // 可打印字符额外发 char 事件
      if (e.key.length === 1) {
        vscode.postMessage({ type: 'keyEvent', action: 'char', key: e.key, code: e.code, text: e.key, modifiers: getModifiers(e) });
      }
    });

    overlay.addEventListener('keyup', (e) => {
      if (e.ctrlKey || e.metaKey) return;
      e.preventDefault();
      vscode.postMessage({ type: 'keyEvent', action: 'keyUp', key: e.key, code: e.code, modifiers: getModifiers(e) });
    });

    // ===== IME 输入栏（中文/粘贴，Ctrl+I 唤出） =====
    function sendImeText() {
      const text = imeInput.value.trim();
      if (text) {
        vscode.postMessage({ type: 'imeCommit', text });
        imeInput.value = '';
      }
      imeBar.style.display = 'none';
      overlay.focus();
    }

    imeSend.addEventListener('click', sendImeText);
    imeClose.addEventListener('click', () => {
      imeInput.value = '';
      imeBar.style.display = 'none';
      overlay.focus();
    });
    imeInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); sendImeText(); }
      if (e.key === 'Escape') { imeBar.style.display = 'none'; overlay.focus(); }
    });

    // ===== 消息处理 =====
    window.addEventListener('message', e => {
      const msg = e.data;

      // 帧数据（含 metadata）
      if (msg.type === 'frame') {
        if (!hasReceivedFrame) {
          hasReceivedFrame = true;
          img.style.display = 'block';
          placeholder.style.display = 'none';
        }
        img.src = 'data:image/jpeg;base64,' + msg.data;
        if (msg.metadata) lastMetadata = msg.metadata;
        frameCount++;
        const now = Date.now();
        if (now - lastFpsTime >= 1000) {
          fpsCounter.textContent = frameCount + ' fps';
          frameCount = 0;
          lastFpsTime = now;
        }
      }

      // URL 更新（仅在地址栏未聚焦时更新）
      if (msg.type === 'url') {
        if (document.activeElement !== urlInput) {
          urlInput.value = msg.url;
        }
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
        el.title = tab.url;

        const titleSpan = document.createElement('span');
        titleSpan.className = 'tab-title';
        titleSpan.textContent = tab.title || shortenUrl(tab.url) || tab.targetId.slice(0, 8);
        titleSpan.addEventListener('click', () => {
          vscode.postMessage({ type: 'switchTab', targetId: tab.targetId });
        });
        el.appendChild(titleSpan);

        const closeBtn = document.createElement('button');
        closeBtn.className = 'tab-close';
        closeBtn.textContent = '×';
        closeBtn.title = '关闭标签页';
        closeBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          vscode.postMessage({ type: 'closeTab', targetId: tab.targetId });
        });
        el.appendChild(closeBtn);

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
