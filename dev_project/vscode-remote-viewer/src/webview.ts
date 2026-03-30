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
