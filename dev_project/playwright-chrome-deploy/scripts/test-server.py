#!/usr/bin/env python3
"""简单测试 Web 服务器，用于验证 Playwright MCP + Remote Browser Viewer"""

from http.server import HTTPServer, SimpleHTTPRequestHandler
import json

HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>Playwright MCP 测试页</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: system-ui, sans-serif; padding: 40px; background: #f5f5f5; }
  h1 { color: #333; margin-bottom: 20px; }
  .card { background: white; border-radius: 8px; padding: 24px; margin-bottom: 16px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
  input, textarea { width: 100%; padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; margin: 8px 0; }
  button { padding: 8px 20px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; margin: 4px; }
  .btn-blue { background: #4a90d9; color: white; }
  .btn-green { background: #67c23a; color: white; }
  .btn-red { background: #f56c6c; color: white; }
  button:hover { opacity: 0.85; }
  #log { background: #1e1e1e; color: #0f0; padding: 12px; border-radius: 4px; font-family: monospace; font-size: 13px; height: 150px; overflow-y: auto; white-space: pre-wrap; }
  .counter { font-size: 48px; font-weight: bold; color: #4a90d9; text-align: center; padding: 20px; }
  a { color: #4a90d9; }
  select { padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 600px) { .grid { grid-template-columns: 1fr; } }
</style>
</head>
<body>

<h1>🧪 Playwright MCP 功能验证</h1>

<div class="grid">
  <div class="card">
    <h3>📝 输入测试</h3>
    <input type="text" id="textInput" placeholder="在此输入文字...">
    <textarea id="textArea" rows="3" placeholder="多行文本..."></textarea>
    <p>输入内容: <span id="inputEcho" style="color:#4a90d9">-</span></p>
  </div>

  <div class="card">
    <h3>🖱️ 点击测试</h3>
    <div class="counter" id="counter">0</div>
    <div style="text-align:center">
      <button class="btn-blue" onclick="changeCount(1)">+1</button>
      <button class="btn-red" onclick="changeCount(-1)">-1</button>
      <button class="btn-green" onclick="resetCount()">重置</button>
    </div>
  </div>

  <div class="card">
    <h3>📋 表单测试</h3>
    <select id="selectBox" onchange="log('选择: ' + this.value)">
      <option value="">请选择...</option>
      <option value="playwright">Playwright</option>
      <option value="chromium">Chromium</option>
      <option value="cdp">CDP Protocol</option>
    </select>
    <br><br>
    <label><input type="checkbox" id="cb1" onchange="log('复选框: ' + this.checked)"> 启用功能 A</label><br>
    <label><input type="checkbox" id="cb2" onchange="log('复选框B: ' + this.checked)"> 启用功能 B</label>
  </div>

  <div class="card">
    <h3>🔗 导航测试</h3>
    <p><a href="/page2">跳转到第二页</a></p>
    <p><a href="/api/status">查看 API 状态 (JSON)</a></p>
    <button class="btn-blue" onclick="window.open('/page2','_blank')">新窗口打开</button>
  </div>
</div>

<div class="card">
  <h3>📊 操作日志</h3>
  <div id="log">等待操作...</div>
</div>

<script>
let count = 0;

document.getElementById('textInput').addEventListener('input', function() {
  document.getElementById('inputEcho').textContent = this.value || '-';
  log('输入: ' + this.value);
});

function changeCount(n) { count += n; document.getElementById('counter').textContent = count; log('计数: ' + count); }
function resetCount() { count = 0; document.getElementById('counter').textContent = 0; log('计数已重置'); }

function log(msg) {
  const el = document.getElementById('log');
  const time = new Date().toLocaleTimeString();
  el.textContent += '\\n[' + time + '] ' + msg;
  el.scrollTop = el.scrollHeight;
}

log('页面加载完成');
</script>
</body>
</html>"""

PAGE2 = """<!DOCTYPE html>
<html lang="zh">
<head><meta charset="UTF-8"><title>第二页</title>
<style>body{font-family:system-ui,sans-serif;padding:40px;background:#e8f4fd;} .card{background:white;border-radius:8px;padding:24px;box-shadow:0 2px 4px rgba(0,0,0,0.1);} a{color:#4a90d9;}</style>
</head>
<body>
<div class="card">
  <h1>📄 第二页</h1>
  <p>导航成功！这是通过链接跳转的页面。</p>
  <p><a href="/">← 返回首页</a></p>
</div>
</body></html>"""


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self._html(HTML)
        elif self.path == '/page2':
            self._html(PAGE2)
        elif self.path == '/api/status':
            self._json({"status": "ok", "server": "test", "chromium": "1205"})
        else:
            self.send_error(404)

    def _html(self, content):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(content.encode())

    def _json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")


if __name__ == '__main__':
    port = 8765
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f'测试服务器启动: http://localhost:{port}')
    print(f'在 Claude Code 中输入: 用 playwright 打开 http://localhost:{port}')
    print('Ctrl+C 停止')
    server.serve_forever()
