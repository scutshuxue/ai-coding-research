# WSS 隧道代理 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 构建一个基于 WSS（WebSocket over TLS）的隧道代理系统，让网络隔离的 Linux 通过 Windows 出网，替代 SSH 反向隧道方案，端口扫描和流量分析均无法识别。

**Architecture:** Linux 端运行 WSS Server（TLS 加密，伪装为 HTTPS 网站）+ Local Proxy（127.0.0.1:8054）。Windows 端主动连接 Linux WSS Server 建立隧道。Linux 应用通过 Local Proxy 发起代理请求，请求通过 WSS 隧道多路复用转发到 Windows 端执行出网。

**Tech Stack:** Python 3.8+, `websockets` 库, `ssl` stdlib, `asyncio`

**Design Doc:** `dev_project/proxy-tunnel/wss-tunnel-design.md`

---

## 文件结构

```
dev_project/proxy-tunnel/wss-tunnel/
├── tunnel_common.py    # 共享模块：消息协议、证书生成、Token 管理
├── tunnel_server.py    # Linux 端：WSS Server + Local Proxy（单 asyncio 进程）
├── tunnel_client.py    # Windows 端：WSS Client + 出网执行
├── setup_linux.sh      # Linux 端配置辅助脚本
└── tests/
    ├── test_common.py      # tunnel_common 单元测试
    ├── test_integration.py # 端到端集成测试（本机 loopback）
    └── conftest.py         # pytest fixtures
```

| 文件 | 职责 | 依赖 |
|------|------|------|
| `tunnel_common.py` | 消息构造/解析、自签名证书生成（调用 openssl CLI）、Token 生成/存储/加载、证书指纹计算 | stdlib only |
| `tunnel_server.py` | WSS Server（TLS + 伪装页面 + Token 鉴权 + 消息收发）、Local Proxy（HTTP/HTTPS 代理 → 隧道转发）、TunnelManager（多路复用） | `websockets`, `tunnel_common` |
| `tunnel_client.py` | WSS Client（连接 + 指纹校验 + 断线重连）、消息分发、TCP 出网连接管理 | `websockets`, `tunnel_common` |
| `setup_linux.sh` | 检查隧道连通性、设置代理环境变量 | — |

---

## Task 1: tunnel_common.py — 消息协议

**Files:**
- Create: `dev_project/proxy-tunnel/wss-tunnel/tunnel_common.py`
- Create: `dev_project/proxy-tunnel/wss-tunnel/tests/test_common.py`
- Create: `dev_project/proxy-tunnel/wss-tunnel/tests/conftest.py`

- [x] **Step 1: 创建目录结构**

```bash
mkdir -p dev_project/proxy-tunnel/wss-tunnel/tests
touch dev_project/proxy-tunnel/wss-tunnel/tests/__init__.py
touch dev_project/proxy-tunnel/wss-tunnel/tests/conftest.py
```

- [x] **Step 2: 编写消息协议的测试**

写入 `dev_project/proxy-tunnel/wss-tunnel/tests/test_common.py`:

```python
"""tunnel_common 单元测试"""
import json
import base64
import pytest


def test_make_connect():
    from tunnel_common import make_msg
    raw = make_msg('connect', 'abc123', host='example.com', port=443)
    msg = json.loads(raw)
    assert msg['type'] == 'connect'
    assert msg['id'] == 'abc123'
    assert msg['host'] == 'example.com'
    assert msg['port'] == 443


def test_make_connect_ok():
    from tunnel_common import make_msg
    raw = make_msg('connect_ok', 'abc123')
    msg = json.loads(raw)
    assert msg['type'] == 'connect_ok'
    assert msg['id'] == 'abc123'


def test_make_connect_fail():
    from tunnel_common import make_msg
    raw = make_msg('connect_fail', 'abc123', error='Connection refused')
    msg = json.loads(raw)
    assert msg['type'] == 'connect_fail'
    assert msg['id'] == 'abc123'
    assert msg['error'] == 'Connection refused'


def test_make_data():
    from tunnel_common import make_msg
    payload = b'GET / HTTP/1.1\r\nHost: example.com\r\n\r\n'
    raw = make_msg('data', 'abc123', payload=payload)
    msg = json.loads(raw)
    assert msg['type'] == 'data'
    assert msg['id'] == 'abc123'
    decoded = base64.b64decode(msg['payload'])
    assert decoded == payload


def test_make_close():
    from tunnel_common import make_msg
    raw = make_msg('close', 'abc123')
    msg = json.loads(raw)
    assert msg['type'] == 'close'
    assert msg['id'] == 'abc123'


def test_parse_msg():
    from tunnel_common import make_msg, parse_msg
    raw = make_msg('connect', 'x1', host='google.com', port=80)
    msg = parse_msg(raw)
    assert msg['type'] == 'connect'
    assert msg['id'] == 'x1'
    assert msg['host'] == 'google.com'
    assert msg['port'] == 80


def test_parse_data_returns_bytes():
    from tunnel_common import make_msg, parse_msg
    original = b'\x00\x01\x02\xff'
    raw = make_msg('data', 'x2', payload=original)
    msg = parse_msg(raw)
    assert msg['payload'] == original


def test_parse_invalid_json():
    from tunnel_common import parse_msg
    with pytest.raises(ValueError):
        parse_msg('not json')


def test_parse_missing_type():
    from tunnel_common import parse_msg
    with pytest.raises(ValueError):
        parse_msg('{"id": "abc"}')
```

- [x] **Step 3: 运行测试确认失败**

```bash
cd dev_project/proxy-tunnel/wss-tunnel && python -m pytest tests/test_common.py -v
```

预期：全部 FAIL（`ModuleNotFoundError: No module named 'tunnel_common'`）

- [x] **Step 4: 实现消息协议**

写入 `dev_project/proxy-tunnel/wss-tunnel/tunnel_common.py`:

```python
"""
WSS 隧道共享模块 — 消息协议、证书管理、Token 管理
Linux 端和 Windows 端共用此文件。
"""

import base64
import hashlib
import json
import os
import secrets
import subprocess

# ── 消息协议 ─────────────────────────────────────────────

def make_msg(msg_type: str, stream_id: str, **kwargs) -> str:
    """构造隧道 JSON 消息。

    Args:
        msg_type: connect | connect_ok | connect_fail | data | close
        stream_id: 流标识符
        **kwargs: 额外字段 (host, port, error, payload)
            payload 接受 bytes，自动 base64 编码
    Returns:
        JSON 字符串
    """
    msg = {'type': msg_type, 'id': stream_id}
    for k, v in kwargs.items():
        if k == 'payload' and isinstance(v, bytes):
            msg[k] = base64.b64encode(v).decode('ascii')
        else:
            msg[k] = v
    return json.dumps(msg, separators=(',', ':'))


def parse_msg(raw: str) -> dict:
    """解析隧道 JSON 消息。

    data 类型的 payload 字段自动从 base64 解码为 bytes。

    Raises:
        ValueError: JSON 解析失败或缺少 type 字段
    """
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f'Invalid JSON: {e}')
    if 'type' not in msg:
        raise ValueError('Missing "type" field')
    if msg.get('type') == 'data' and 'payload' in msg:
        msg['payload'] = base64.b64decode(msg['payload'])
    return msg


def generate_stream_id() -> str:
    """生成 8 字节 hex 流标识符。"""
    return secrets.token_hex(8)
```

- [x] **Step 5: 运行测试确认通过**

```bash
cd dev_project/proxy-tunnel/wss-tunnel && python -m pytest tests/test_common.py -v
```

预期：9 tests PASSED

- [x] **Step 6: Commit**

```bash
git add dev_project/proxy-tunnel/wss-tunnel/tunnel_common.py \
        dev_project/proxy-tunnel/wss-tunnel/tests/
git commit -m "feat(wss-tunnel): add message protocol in tunnel_common.py with tests"
```

---

## Task 2: tunnel_common.py — 证书与 Token 管理

**Files:**
- Modify: `dev_project/proxy-tunnel/wss-tunnel/tunnel_common.py`
- Modify: `dev_project/proxy-tunnel/wss-tunnel/tests/test_common.py`

- [x] **Step 1: 编写证书和 Token 的测试**

追加到 `tests/test_common.py`:

```python
import tempfile
import os


def test_generate_token():
    from tunnel_common import generate_token
    token = generate_token()
    assert len(token) == 64  # 32 bytes hex
    assert all(c in '0123456789abcdef' for c in token)


def test_generate_token_unique():
    from tunnel_common import generate_token
    tokens = {generate_token() for _ in range(100)}
    assert len(tokens) == 100


def test_save_and_load_config(tmp_path):
    from tunnel_common import save_config, load_config
    config = {'token': 'abc123', 'fingerprint': 'SHA256:xxx'}
    save_config(config, tmp_path / 'server.json')
    loaded = load_config(tmp_path / 'server.json')
    assert loaded['token'] == 'abc123'
    assert loaded['fingerprint'] == 'SHA256:xxx'


def test_generate_self_signed_cert(tmp_path):
    from tunnel_common import generate_self_signed_cert
    cert_path, key_path = generate_self_signed_cert(tmp_path)
    assert os.path.exists(cert_path)
    assert os.path.exists(key_path)
    # cert 文件应包含 PEM 头
    with open(cert_path) as f:
        content = f.read()
    assert '-----BEGIN CERTIFICATE-----' in content


def test_get_cert_fingerprint(tmp_path):
    from tunnel_common import generate_self_signed_cert, get_cert_fingerprint
    cert_path, _ = generate_self_signed_cert(tmp_path)
    fp = get_cert_fingerprint(cert_path)
    assert fp.startswith('SHA256:')
    # SHA256 hex = 64 chars
    assert len(fp.split(':')[1]) == 64


def test_generate_stream_id():
    from tunnel_common import generate_stream_id
    sid = generate_stream_id()
    assert len(sid) == 16  # 8 bytes hex
    ids = {generate_stream_id() for _ in range(100)}
    assert len(ids) == 100
```

- [x] **Step 2: 运行测试确认新增用例失败**

```bash
cd dev_project/proxy-tunnel/wss-tunnel && python -m pytest tests/test_common.py -v -k "token or config or cert or stream_id"
```

预期：FAIL（`ImportError` — 函数不存在）

- [x] **Step 3: 实现证书与 Token 管理**

在 `tunnel_common.py` 末尾追加：

```python
# ── Token 管理 ───────────────────────────────────────────

def generate_token() -> str:
    """生成 32 字节 hex Token（64 字符）。"""
    return secrets.token_hex(32)


# ── 配置文件 ─────────────────────────────────────────────

def save_config(config: dict, path) -> None:
    """保存配置到 JSON 文件。"""
    path = str(path)
    with open(path, 'w') as f:
        json.dump(config, f, indent=2)
    os.chmod(path, 0o600)


def load_config(path) -> dict:
    """加载 JSON 配置文件。"""
    with open(str(path)) as f:
        return json.load(f)


# ── 证书管理（调用 openssl CLI） ─────────────────────────

def generate_self_signed_cert(cert_dir, days: int = 365) -> tuple:
    """使用 openssl 生成自签名证书。

    Returns:
        (cert_path, key_path) 元组
    """
    cert_dir = str(cert_dir)
    os.makedirs(cert_dir, exist_ok=True)
    cert_path = os.path.join(cert_dir, 'cert.pem')
    key_path = os.path.join(cert_dir, 'key.pem')

    subprocess.run([
        'openssl', 'req', '-x509', '-newkey', 'rsa:2048',
        '-keyout', key_path, '-out', cert_path,
        '-days', str(days), '-nodes',
        '-subj', '/CN=Test Dashboard/O=System/C=US'
    ], check=True, capture_output=True)

    os.chmod(key_path, 0o600)
    os.chmod(cert_path, 0o600)
    return cert_path, key_path


def get_cert_fingerprint(cert_path: str) -> str:
    """获取证书 SHA256 指纹。

    Returns:
        格式: SHA256:aabbccdd...（64 hex 字符）
    """
    result = subprocess.run(
        ['openssl', 'x509', '-in', str(cert_path), '-noout', '-fingerprint', '-sha256'],
        check=True, capture_output=True, text=True
    )
    # 输出格式: sha256 Fingerprint=AA:BB:CC:...
    line = result.stdout.strip()
    # 兼容不同 openssl 版本的输出格式
    fp_hex = line.split('=', 1)[1].replace(':', '').lower()
    return f'SHA256:{fp_hex}'
```

- [x] **Step 4: 运行全部测试确认通过**

```bash
cd dev_project/proxy-tunnel/wss-tunnel && python -m pytest tests/test_common.py -v
```

预期：15 tests PASSED（需要系统安装了 openssl）

- [x] **Step 5: Commit**

```bash
git add dev_project/proxy-tunnel/wss-tunnel/tunnel_common.py \
        dev_project/proxy-tunnel/wss-tunnel/tests/test_common.py
git commit -m "feat(wss-tunnel): add cert generation, token management to tunnel_common"
```

---

## Task 3: tunnel_server.py — TunnelManager 核心

**Files:**
- Create: `dev_project/proxy-tunnel/wss-tunnel/tunnel_server.py`

- [x] **Step 1: 编写 TunnelManager 类**

创建 `dev_project/proxy-tunnel/wss-tunnel/tunnel_server.py`:

```python
#!/usr/bin/env python3
"""
WSS 隧道服务端（Linux 端运行）
包含 WSS Server（TLS 加密 + 伪装页面）和 Local Proxy（HTTP/HTTPS 代理）。

用法:
    python tunnel_server.py --init          # 首次初始化证书和 Token
    python tunnel_server.py                 # 启动服务
    python tunnel_server.py --wss-port 8044 --proxy-port 8054
"""

import argparse
import asyncio
import logging
import os
import ssl
import sys
from urllib.parse import urlparse

import websockets
from websockets.exceptions import ConnectionClosed

from tunnel_common import (
    make_msg, parse_msg, generate_stream_id,
    generate_token, generate_self_signed_cert, get_cert_fingerprint,
    save_config, load_config,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('tunnel-server')

# ── 伪装页面 ─────────────────────────────────────────────

DISGUISE_PAGE = b"""\
<!DOCTYPE html>
<html>
<head><title>Test Dashboard</title></head>
<body>
<h1>System Status</h1>
<p>All services passed.</p>
</body>
</html>"""

DISGUISE_404 = b"""\
<!DOCTYPE html>
<html>
<head><title>404 Not Found</title></head>
<body>
<h1>404 Not Found</h1>
</body>
</html>"""


# ── TunnelManager ────────────────────────────────────────

class TunnelManager:
    """管理 WSS 隧道连接和多路复用流。"""

    def __init__(self):
        self.ws = None
        self.connected = asyncio.Event()
        self.streams: dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()

    async def register_client(self, ws):
        """注册 WSS 客户端连接。"""
        async with self._lock:
            if self.ws is not None:
                # 替换旧连接
                try:
                    await self.ws.close()
                except Exception:
                    pass
            self.ws = ws
            self.connected.set()
            log.info('Tunnel client connected')

    async def unregister_client(self):
        """注销 WSS 客户端连接，清理所有流。"""
        async with self._lock:
            self.ws = None
            self.connected.clear()
            # 向所有等待中的流发送 None 信号
            for q in self.streams.values():
                await q.put(None)
            self.streams.clear()
            log.info('Tunnel client disconnected')

    def create_stream(self) -> str:
        """创建新的多路复用流，返回 stream_id。"""
        stream_id = generate_stream_id()
        self.streams[stream_id] = asyncio.Queue()
        return stream_id

    def remove_stream(self, stream_id: str):
        """移除流。"""
        self.streams.pop(stream_id, None)

    async def send(self, msg: str):
        """发送消息到 WSS 客户端。"""
        if self.ws is None:
            raise ConnectionError('No tunnel client connected')
        await self.ws.send(msg)

    async def dispatch(self, raw: str):
        """分发从 WSS 客户端收到的消息到对应的流队列。"""
        msg = parse_msg(raw)
        stream_id = msg.get('id')
        if stream_id and stream_id in self.streams:
            await self.streams[stream_id].put(msg)
        else:
            log.warning(f'Unknown stream {stream_id}, dropping message')

    async def wait_for_client(self, timeout: float = None):
        """等待 WSS 客户端连接。"""
        if timeout:
            await asyncio.wait_for(self.connected.wait(), timeout)
        else:
            await self.connected.wait()
```

- [x] **Step 2: 运行语法检查**

```bash
cd dev_project/proxy-tunnel/wss-tunnel && python -c "import tunnel_server; print('OK')"
```

预期：`OK`（需要 `pip install websockets`）

- [x] **Step 3: Commit**

```bash
git add dev_project/proxy-tunnel/wss-tunnel/tunnel_server.py
git commit -m "feat(wss-tunnel): add TunnelManager core in tunnel_server.py"
```

---

## Task 4: tunnel_server.py — WSS Server（TLS + 伪装 + Token 鉴权）

**Files:**
- Modify: `dev_project/proxy-tunnel/wss-tunnel/tunnel_server.py`

- [x] **Step 1: 添加 WSS Server 逻辑**

在 `tunnel_server.py` 的 `TunnelManager` 类之后追加：

```python
# ── WSS Server ───────────────────────────────────────────

class WSSServer:
    """WSS Server: TLS 加密 + 伪装页面 + Token 鉴权。"""

    def __init__(self, tunnel: TunnelManager, token: str, ssl_ctx: ssl.SSLContext):
        self.tunnel = tunnel
        self.token = token
        self.ssl_ctx = ssl_ctx

    async def start(self, bind: str, port: int):
        """启动 WSS Server。"""
        server = await websockets.serve(
            self._handler,
            bind, port,
            ssl=self.ssl_ctx,
            process_request=self._process_http_request,
            ping_interval=30,
            ping_timeout=10,
        )
        log.info(f'WSS Server listening on {bind}:{port} (TLS)')
        return server

    async def _process_http_request(self, path, request_headers):
        """处理非 WebSocket 请求，返回伪装页面。

        websockets 库在 WebSocket 升级前调用此回调。
        返回 (status, headers, body) 则拦截请求，不升级为 WS。
        返回 None 则继续 WS 升级流程。
        """
        # 检查是否是 WebSocket 升级请求到 /ws 路径
        if path == '/ws':
            # 检查 Token
            protocols = request_headers.get('Sec-WebSocket-Protocol', '')
            if self.token in protocols.split(', '):
                return None  # 允许 WS 升级
            # Token 错误
            return (
                403,
                [('Server', 'nginx/1.24.0'), ('Content-Type', 'text/plain')],
                b'Forbidden',
            )

        # 非 /ws 路径：返回伪装页面
        if path == '/' or path == '/index.html':
            return (
                200,
                [('Server', 'nginx/1.24.0'), ('Content-Type', 'text/html; charset=utf-8')],
                DISGUISE_PAGE,
            )
        return (
            404,
            [('Server', 'nginx/1.24.0'), ('Content-Type', 'text/html; charset=utf-8')],
            DISGUISE_404,
        )

    async def _handler(self, websocket, path=None):
        """处理已认证的 WSS 连接。"""
        await self.tunnel.register_client(websocket)
        try:
            async for raw in websocket:
                await self.tunnel.dispatch(raw)
        except ConnectionClosed:
            pass
        finally:
            await self.tunnel.unregister_client()
```

- [x] **Step 2: 语法检查**

```bash
cd dev_project/proxy-tunnel/wss-tunnel && python -c "from tunnel_server import WSSServer; print('OK')"
```

预期：`OK`

- [x] **Step 3: Commit**

```bash
git add dev_project/proxy-tunnel/wss-tunnel/tunnel_server.py
git commit -m "feat(wss-tunnel): add WSS Server with TLS, disguise page, token auth"
```

---

## Task 5: tunnel_server.py — Local Proxy（HTTP/HTTPS 代理）

**Files:**
- Modify: `dev_project/proxy-tunnel/wss-tunnel/tunnel_server.py`

- [x] **Step 1: 添加 Local Proxy 逻辑**

在 `WSSServer` 类之后追加：

```python
# ── Local Proxy ──────────────────────────────────────────

class LocalProxy:
    """HTTP/HTTPS 代理，应用层入口。将请求通过 WSS 隧道转发。"""

    CONNECT_TIMEOUT = 60  # 等待 Windows 端连接目标的超时

    def __init__(self, tunnel: TunnelManager):
        self.tunnel = tunnel

    async def start(self, bind: str, port: int):
        """启动代理服务器。"""
        server = await asyncio.start_server(self._handle_client, bind, port)
        log.info(f'Local Proxy listening on {bind}:{port}')
        return server

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """处理一个代理客户端连接。"""
        try:
            # 读取请求行
            line = await asyncio.wait_for(reader.readline(), timeout=60)
            if not line:
                return
            request_line = line.decode('utf-8', errors='replace').strip()
            parts = request_line.split(' ', 2)
            if len(parts) < 2:
                writer.close()
                return

            method = parts[0].upper()

            # 读取请求头
            headers = {}
            while True:
                hline = await reader.readline()
                if hline in (b'\r\n', b'\n', b''):
                    break
                if b':' in hline:
                    k, v = hline.decode('utf-8', errors='replace').split(':', 1)
                    headers[k.strip().lower()] = v.strip()

            if method == 'CONNECT':
                await self._handle_connect(parts[1], reader, writer, headers)
            else:
                await self._handle_http(request_line, reader, writer, headers)
        except Exception as e:
            log.error(f'Proxy error: {e}')
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _handle_connect(self, target: str, reader, writer, headers):
        """处理 CONNECT 请求（HTTPS 隧道）。"""
        host, port = self._parse_host_port(target, 443)
        log.info(f'CONNECT {host}:{port}')

        if not self.tunnel.connected.is_set():
            writer.write(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
            return

        stream_id = self.tunnel.create_stream()
        try:
            # 发送 connect 请求到 Windows
            await self.tunnel.send(make_msg('connect', stream_id, host=host, port=port))

            # 等待 connect_ok / connect_fail
            q = self.tunnel.streams[stream_id]
            resp = await asyncio.wait_for(q.get(), timeout=self.CONNECT_TIMEOUT)
            if resp is None or resp.get('type') != 'connect_ok':
                error = resp.get('error', 'unknown') if resp else 'tunnel disconnected'
                writer.write(f'HTTP/1.1 502 Bad Gateway\r\nX-Error: {error}\r\n\r\n'.encode())
                return

            # 连接成功
            writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            await writer.drain()

            # 双向转发
            await self._relay(stream_id, reader, writer)
        except asyncio.TimeoutError:
            writer.write(b'HTTP/1.1 504 Gateway Timeout\r\n\r\n')
        finally:
            self.tunnel.remove_stream(stream_id)
            try:
                await self.tunnel.send(make_msg('close', stream_id))
            except Exception:
                pass

    async def _handle_http(self, request_line: str, reader, writer, headers):
        """处理普通 HTTP 代理请求（GET/POST 等）。"""
        parts = request_line.split(' ', 2)
        method = parts[0]
        url = parts[1]
        http_version = parts[2] if len(parts) > 2 else 'HTTP/1.1'

        parsed = urlparse(url)
        host, port = self._parse_host_port(parsed.netloc, 80)
        path = parsed.path or '/'
        if parsed.query:
            path += '?' + parsed.query

        log.info(f'{method} {url}')

        if not self.tunnel.connected.is_set():
            writer.write(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
            return

        stream_id = self.tunnel.create_stream()
        try:
            # 请求 Windows 建立到目标的 TCP 连接
            await self.tunnel.send(make_msg('connect', stream_id, host=host, port=port))

            q = self.tunnel.streams[stream_id]
            resp = await asyncio.wait_for(q.get(), timeout=self.CONNECT_TIMEOUT)
            if resp is None or resp.get('type') != 'connect_ok':
                error = resp.get('error', 'unknown') if resp else 'tunnel disconnected'
                writer.write(f'HTTP/1.1 502 Bad Gateway\r\nX-Error: {error}\r\n\r\n'.encode())
                return

            # 构造转发请求
            req = f'{method} {path} {http_version}\r\n'
            for k, v in headers.items():
                if k in ('proxy-authorization', 'proxy-connection'):
                    continue
                req += f'{k}: {v}\r\n'
            if 'host' not in headers:
                req += f'host: {parsed.netloc}\r\n'
            req += 'connection: close\r\n\r\n'

            # 发送请求头
            await self.tunnel.send(make_msg('data', stream_id, payload=req.encode()))

            # 发送请求体
            content_len = int(headers.get('content-length', '0'))
            if content_len > 0:
                body = await reader.readexactly(content_len)
                await self.tunnel.send(make_msg('data', stream_id, payload=body))

            # 接收响应并转发给客户端
            while True:
                msg = await asyncio.wait_for(q.get(), timeout=60)
                if msg is None:
                    break
                if msg['type'] == 'data':
                    writer.write(msg['payload'])
                    await writer.drain()
                elif msg['type'] == 'close':
                    break
        except asyncio.TimeoutError:
            writer.write(b'HTTP/1.1 504 Gateway Timeout\r\n\r\n')
        finally:
            self.tunnel.remove_stream(stream_id)
            try:
                await self.tunnel.send(make_msg('close', stream_id))
            except Exception:
                pass

    async def _relay(self, stream_id: str, reader, writer):
        """CONNECT 模式双向数据转发。"""

        async def client_to_tunnel():
            """读取客户端数据，发送到隧道。"""
            try:
                while True:
                    data = await reader.read(65536)
                    if not data:
                        break
                    await self.tunnel.send(make_msg('data', stream_id, payload=data))
            except Exception:
                pass

        async def tunnel_to_client():
            """从隧道队列读取数据，发送到客户端。"""
            q = self.tunnel.streams.get(stream_id)
            if not q:
                return
            try:
                while True:
                    msg = await q.get()
                    if msg is None:
                        break
                    if msg['type'] == 'data':
                        writer.write(msg['payload'])
                        await writer.drain()
                    elif msg['type'] == 'close':
                        break
            except Exception:
                pass

        # 并发双向转发，任一方向结束则全部结束
        tasks = [
            asyncio.create_task(client_to_tunnel()),
            asyncio.create_task(tunnel_to_client()),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()

    @staticmethod
    def _parse_host_port(addr: str, default_port: int) -> tuple:
        if ':' in addr:
            host, port_str = addr.rsplit(':', 1)
            try:
                return host, int(port_str)
            except ValueError:
                return addr, default_port
        return addr, default_port
```

- [x] **Step 2: 语法检查**

```bash
cd dev_project/proxy-tunnel/wss-tunnel && python -c "from tunnel_server import LocalProxy; print('OK')"
```

预期：`OK`

- [x] **Step 3: Commit**

```bash
git add dev_project/proxy-tunnel/wss-tunnel/tunnel_server.py
git commit -m "feat(wss-tunnel): add Local Proxy with HTTP/HTTPS support"
```

---

## Task 6: tunnel_server.py — main() 启动入口

**Files:**
- Modify: `dev_project/proxy-tunnel/wss-tunnel/tunnel_server.py`

- [x] **Step 1: 添加 main 函数和 --init 逻辑**

在文件末尾追加：

```python
# ── 启动入口 ─────────────────────────────────────────────

DEFAULT_CERT_DIR = os.path.expanduser('~/.wss-tunnel')


def do_init(cert_dir: str):
    """首次初始化：生成证书和 Token。"""
    print(f'Initializing in {cert_dir}...')
    cert_path, key_path = generate_self_signed_cert(cert_dir)
    fp = get_cert_fingerprint(cert_path)
    token = generate_token()
    config = {'token': token, 'fingerprint': fp}
    save_config(config, os.path.join(cert_dir, 'server.json'))

    print(f'''
╔══════════════════════════════════════════════════════════╗
║  WSS 隧道初始化完成                                       ║
╠══════════════════════════════════════════════════════════╣
║  证书:       {cert_path}
║  私钥:       {key_path}
║  配置:       {os.path.join(cert_dir, 'server.json')}
╠══════════════════════════════════════════════════════════╣
║  Token:       {token}
║  Fingerprint: {fp}
╠══════════════════════════════════════════════════════════╣
║  请记录 Token 和 Fingerprint，Windows 端连接时需要        ║
╚══════════════════════════════════════════════════════════╝
''')


async def run_server(args):
    """启动 WSS Server + Local Proxy。"""
    cert_dir = args.cert_dir
    config_path = os.path.join(cert_dir, 'server.json')

    if not os.path.exists(config_path):
        print(f'Error: {config_path} not found. Run --init first.')
        sys.exit(1)

    config = load_config(config_path)
    token = config['token']

    cert_path = os.path.join(cert_dir, 'cert.pem')
    key_path = os.path.join(cert_dir, 'key.pem')

    # 创建 SSL 上下文
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(cert_path, key_path)

    tunnel = TunnelManager()

    # 启动 WSS Server
    wss = WSSServer(tunnel, token, ssl_ctx)
    wss_server = await wss.start(args.wss_bind, args.wss_port)

    # 启动 Local Proxy
    proxy = LocalProxy(tunnel)
    proxy_server = await proxy.start(args.proxy_bind, args.proxy_port)

    print(f'''
╔══════════════════════════════════════════════════════════╗
║  WSS 隧道服务端已启动                                     ║
╠══════════════════════════════════════════════════════════╣
║  WSS Server:   {args.wss_bind}:{args.wss_port} (TLS)
║  Local Proxy:  {args.proxy_bind}:{args.proxy_port}
╠══════════════════════════════════════════════════════════╣
║  等待 Windows 客户端连接...                               ║
║  Ctrl+C 停止                                             ║
╚══════════════════════════════════════════════════════════╝
''')

    # 保持运行
    try:
        await asyncio.Future()  # run forever
    except asyncio.CancelledError:
        pass
    finally:
        wss_server.close()
        proxy_server.close()


def main():
    parser = argparse.ArgumentParser(description='WSS 隧道服务端（Linux 端）')
    parser.add_argument('--init', action='store_true', help='首次初始化：生成证书和 Token')
    parser.add_argument('--wss-port', type=int, default=8044, help='WSS Server 端口 (默认 8044)')
    parser.add_argument('--wss-bind', default='0.0.0.0', help='WSS Server 绑定地址 (默认 0.0.0.0)')
    parser.add_argument('--proxy-port', type=int, default=8054, help='Local Proxy 端口 (默认 8054)')
    parser.add_argument('--proxy-bind', default='127.0.0.1', help='Local Proxy 绑定地址 (默认 127.0.0.1)')
    parser.add_argument('--cert-dir', default=DEFAULT_CERT_DIR, help=f'证书目录 (默认 {DEFAULT_CERT_DIR})')
    args = parser.parse_args()

    if args.init:
        do_init(args.cert_dir)
        return

    try:
        asyncio.run(run_server(args))
    except KeyboardInterrupt:
        print('\n服务已停止')


if __name__ == '__main__':
    main()
```

- [x] **Step 2: 验证 --init 功能**

```bash
cd dev_project/proxy-tunnel/wss-tunnel && python tunnel_server.py --init --cert-dir /tmp/test-wss-tunnel
```

预期：打印证书路径、Token、Fingerprint。检查 `/tmp/test-wss-tunnel/` 下有 `cert.pem`、`key.pem`、`server.json`。

- [x] **Step 3: 验证 server 启动（快速退出）**

```bash
cd dev_project/proxy-tunnel/wss-tunnel && timeout 3 python tunnel_server.py --cert-dir /tmp/test-wss-tunnel --wss-port 8044 --proxy-port 8054 || true
```

预期：看到「WSS 隧道服务端已启动」输出，3 秒后 timeout 退出。

- [x] **Step 4: 清理测试文件并 Commit**

```bash
rm -rf /tmp/test-wss-tunnel
git add dev_project/proxy-tunnel/wss-tunnel/tunnel_server.py
git commit -m "feat(wss-tunnel): add main() entry with --init and server startup"
```

---

## Task 7: tunnel_client.py — WSS 客户端 + 出网执行

**Files:**
- Create: `dev_project/proxy-tunnel/wss-tunnel/tunnel_client.py`

- [x] **Step 1: 编写完整的 tunnel_client.py**

创建 `dev_project/proxy-tunnel/wss-tunnel/tunnel_client.py`:

```python
#!/usr/bin/env python3
"""
WSS 隧道客户端（Windows 端运行）
主动连接 Linux WSS Server，接收代理请求并执行出网。

用法:
    python tunnel_client.py --host <linux-ip> --token <token> --fingerprint <SHA256:xxxx>
    python tunnel_client.py --host 192.168.1.100 --port 8044 --token abc123 --fingerprint SHA256:def456
"""

import argparse
import asyncio
import logging
import socket
import ssl
import sys

import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatusCode

from tunnel_common import make_msg, parse_msg

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('tunnel-client')


class TunnelClient:
    """WSS 隧道客户端：连接 Linux Server，接收代理请求，执行出网。"""

    def __init__(self, host: str, port: int, token: str, fingerprint: str,
                 reconnect: bool = True, max_retry: int = 0):
        self.host = host
        self.port = port
        self.token = token
        self.fingerprint = fingerprint
        self.reconnect = reconnect
        self.max_retry = max_retry
        self.connections: dict[str, tuple[asyncio.StreamReader, asyncio.StreamWriter]] = {}
        self.ws = None

    def _make_ssl_context(self) -> ssl.SSLContext:
        """创建 SSL 上下文，配置证书指纹校验。"""
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        # 自签名证书不走 CA 验证，通过指纹校验代替
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _verify_fingerprint(self, ws) -> bool:
        """校验服务端证书指纹。"""
        transport = ws.transport
        ssl_object = transport.get_extra_info('ssl_object')
        if not ssl_object:
            log.error('No SSL connection')
            return False
        cert_der = ssl_object.getpeercert(binary_form=True)
        if not cert_der:
            log.error('No peer certificate')
            return False
        import hashlib
        fp = hashlib.sha256(cert_der).hexdigest()
        expected = self.fingerprint.replace('SHA256:', '').lower()
        if fp != expected:
            log.error(f'Fingerprint mismatch! Got SHA256:{fp}, expected {self.fingerprint}')
            return False
        return True

    async def run(self):
        """主循环：连接 + 重连。"""
        retry = 0
        while True:
            try:
                await self._connect_and_serve()
                retry = 0  # 成功连接后重置
            except (ConnectionRefusedError, OSError, InvalidStatusCode) as e:
                log.warning(f'Connection failed: {e}')
            except ConnectionClosed:
                log.warning('WSS connection closed')
            except Exception as e:
                log.error(f'Unexpected error: {e}')

            if not self.reconnect:
                break

            retry += 1
            if self.max_retry and retry > self.max_retry:
                log.error(f'Max retries ({self.max_retry}) exceeded')
                break

            delay = min(2 ** retry, 60)
            log.info(f'Reconnecting in {delay}s (attempt {retry})...')
            await asyncio.sleep(delay)

    async def _connect_and_serve(self):
        """建立 WSS 连接并处理消息。"""
        url = f'wss://{self.host}:{self.port}/ws'
        ssl_ctx = self._make_ssl_context()

        async with websockets.connect(
            url,
            ssl=ssl_ctx,
            subprotocols=[self.token],
            ping_interval=30,
            ping_timeout=10,
        ) as ws:
            # 校验证书指纹
            if not self._verify_fingerprint(ws):
                log.error('Certificate fingerprint verification failed, disconnecting')
                return

            self.ws = ws
            log.info(f'Connected to {url}')
            print(f'Tunnel established, ready to relay.')

            try:
                async for raw in ws:
                    asyncio.create_task(self._handle_message(raw))
            finally:
                self.ws = None
                await self._close_all_connections()

    async def _handle_message(self, raw: str):
        """处理从服务端收到的消息。"""
        try:
            msg = parse_msg(raw)
        except ValueError as e:
            log.warning(f'Invalid message: {e}')
            return

        msg_type = msg['type']
        stream_id = msg.get('id', '')

        if msg_type == 'connect':
            await self._handle_connect(stream_id, msg['host'], msg['port'])
        elif msg_type == 'data':
            await self._handle_data(stream_id, msg['payload'])
        elif msg_type == 'close':
            await self._handle_close(stream_id)

    async def _handle_connect(self, stream_id: str, host: str, port: int):
        """处理 connect 请求：建立到目标的 TCP 连接。"""
        log.info(f'[{stream_id[:8]}] Connecting to {host}:{port}')
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=60,
            )
            self.connections[stream_id] = (reader, writer)
            await self.ws.send(make_msg('connect_ok', stream_id))
            # 启动从目标读取数据的协程
            asyncio.create_task(self._read_from_target(stream_id, reader))
        except Exception as e:
            log.warning(f'[{stream_id[:8]}] Connect failed: {e}')
            try:
                await self.ws.send(make_msg('connect_fail', stream_id, error=str(e)))
            except Exception:
                pass

    async def _handle_data(self, stream_id: str, payload: bytes):
        """处理 data 消息：转发到目标。"""
        conn = self.connections.get(stream_id)
        if not conn:
            return
        _, writer = conn
        try:
            writer.write(payload)
            await writer.drain()
        except Exception as e:
            log.warning(f'[{stream_id[:8]}] Write to target failed: {e}')
            await self._handle_close(stream_id)

    async def _handle_close(self, stream_id: str):
        """处理 close 消息：关闭到目标的连接。"""
        conn = self.connections.pop(stream_id, None)
        if conn:
            _, writer = conn
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _read_from_target(self, stream_id: str, reader: asyncio.StreamReader):
        """从目标服务器读取响应，通过隧道回传。"""
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                if self.ws:
                    await self.ws.send(make_msg('data', stream_id, payload=data))
        except Exception:
            pass
        finally:
            # 目标关闭连接，通知服务端
            self.connections.pop(stream_id, None)
            if self.ws:
                try:
                    await self.ws.send(make_msg('close', stream_id))
                except Exception:
                    pass

    async def _close_all_connections(self):
        """关闭所有到目标的连接。"""
        for stream_id, (_, writer) in list(self.connections.items()):
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
        self.connections.clear()


def main():
    parser = argparse.ArgumentParser(description='WSS 隧道客户端（Windows 端）')
    parser.add_argument('--host', required=True, help='Linux 服务器地址')
    parser.add_argument('--port', type=int, default=8044, help='WSS Server 端口 (默认 8044)')
    parser.add_argument('--token', required=True, help='鉴权 Token')
    parser.add_argument('--fingerprint', required=True, help='证书指纹 (SHA256:xxxx)')
    parser.add_argument('--no-reconnect', action='store_true', help='禁用自动重连')
    parser.add_argument('--max-retry', type=int, default=0, help='最大重连次数 (0=无限)')
    args = parser.parse_args()

    print(f'''
╔══════════════════════════════════════════════════════════╗
║  WSS 隧道客户端                                          ║
╠══════════════════════════════════════════════════════════╣
║  目标:  wss://{args.host}:{args.port}/ws
║  重连:  {"关闭" if args.no_reconnect else "开启"}
╚══════════════════════════════════════════════════════════╝
''')

    client = TunnelClient(
        host=args.host,
        port=args.port,
        token=args.token,
        fingerprint=args.fingerprint,
        reconnect=not args.no_reconnect,
        max_retry=args.max_retry,
    )

    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print('\n客户端已停止')


if __name__ == '__main__':
    main()
```

- [x] **Step 2: 语法检查**

```bash
cd dev_project/proxy-tunnel/wss-tunnel && python -c "from tunnel_client import TunnelClient; print('OK')"
```

预期：`OK`

- [x] **Step 3: Commit**

```bash
git add dev_project/proxy-tunnel/wss-tunnel/tunnel_client.py
git commit -m "feat(wss-tunnel): add tunnel_client.py - WSS client with reconnect and fingerprint verification"
```

---

## Task 8: 端到端集成测试

**Files:**
- Create: `dev_project/proxy-tunnel/wss-tunnel/tests/test_integration.py`

- [x] **Step 1: 编写集成测试**

创建 `dev_project/proxy-tunnel/wss-tunnel/tests/test_integration.py`:

```python
"""
端到端集成测试：在本机 loopback 上启动 server + client + 目标 HTTP 服务，
验证 Local Proxy 能通过 WSS 隧道访问目标。
"""
import asyncio
import os
import ssl
import tempfile
import pytest

# 将 wss-tunnel 目录加入 path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tunnel_common import (
    generate_self_signed_cert, generate_token, get_cert_fingerprint,
    save_config,
)


@pytest.fixture
def cert_dir():
    """生成临时证书目录。"""
    with tempfile.TemporaryDirectory() as d:
        generate_self_signed_cert(d)
        token = generate_token()
        fp = get_cert_fingerprint(os.path.join(d, 'cert.pem'))
        save_config({'token': token, 'fingerprint': fp}, os.path.join(d, 'server.json'))
        yield d, token, fp


@pytest.fixture
async def target_http_server():
    """启动一个简单的 HTTP 目标服务器。"""
    async def handler(reader, writer):
        await reader.readline()  # request line
        while (await reader.readline()) != b'\r\n':
            pass
        response = (
            b'HTTP/1.1 200 OK\r\n'
            b'Content-Type: text/plain\r\n'
            b'Content-Length: 13\r\n'
            b'Connection: close\r\n'
            b'\r\n'
            b'Hello, World!'
        )
        writer.write(response)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handler, '127.0.0.1', 0)
    port = server.sockets[0].getsockname()[1]
    yield port
    server.close()
    await server.wait_closed()


@pytest.mark.asyncio
async def test_http_proxy_through_tunnel(cert_dir, target_http_server):
    """测试 HTTP 请求通过 WSS 隧道转发。"""
    from tunnel_server import TunnelManager, WSSServer, LocalProxy
    from tunnel_client import TunnelClient

    cert_path_dir, token, fingerprint = cert_dir
    target_port = target_http_server

    # 创建 SSL context
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(
        os.path.join(cert_path_dir, 'cert.pem'),
        os.path.join(cert_path_dir, 'key.pem'),
    )

    tunnel = TunnelManager()

    # 启动 WSS Server（随机端口）
    wss = WSSServer(tunnel, token, ssl_ctx)
    wss_server = await wss.start('127.0.0.1', 0)
    wss_port = wss_server.sockets[0].getsockname()[1]

    # 启动 Local Proxy（随机端口）
    proxy = LocalProxy(tunnel)
    proxy_server = await proxy.start('127.0.0.1', 0)
    proxy_port = proxy_server.sockets[0].getsockname()[1]

    # 启动客户端（不重连）
    client = TunnelClient(
        host='127.0.0.1', port=wss_port,
        token=token, fingerprint=fingerprint,
        reconnect=False,
    )
    client_task = asyncio.create_task(client.run())

    # 等待隧道建立
    await asyncio.wait_for(tunnel.connected.wait(), timeout=5)

    # 通过代理发送 HTTP 请求
    reader, writer = await asyncio.open_connection('127.0.0.1', proxy_port)
    request = (
        f'GET http://127.0.0.1:{target_port}/ HTTP/1.1\r\n'
        f'Host: 127.0.0.1:{target_port}\r\n'
        f'\r\n'
    ).encode()
    writer.write(request)
    await writer.drain()

    # 读取响应
    response = b''
    try:
        while True:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=5)
            if not chunk:
                break
            response += chunk
    except asyncio.TimeoutError:
        pass

    writer.close()

    assert b'200 OK' in response
    assert b'Hello, World!' in response

    # 清理
    client_task.cancel()
    try:
        await client_task
    except asyncio.CancelledError:
        pass
    wss_server.close()
    proxy_server.close()


@pytest.mark.asyncio
async def test_connect_proxy_through_tunnel(cert_dir, target_http_server):
    """测试 CONNECT (HTTPS 隧道) 通过 WSS 隧道转发。"""
    from tunnel_server import TunnelManager, WSSServer, LocalProxy
    from tunnel_client import TunnelClient

    cert_path_dir, token, fingerprint = cert_dir
    target_port = target_http_server

    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(
        os.path.join(cert_path_dir, 'cert.pem'),
        os.path.join(cert_path_dir, 'key.pem'),
    )

    tunnel = TunnelManager()
    wss = WSSServer(tunnel, token, ssl_ctx)
    wss_server = await wss.start('127.0.0.1', 0)
    wss_port = wss_server.sockets[0].getsockname()[1]

    proxy = LocalProxy(tunnel)
    proxy_server = await proxy.start('127.0.0.1', 0)
    proxy_port = proxy_server.sockets[0].getsockname()[1]

    client = TunnelClient(
        host='127.0.0.1', port=wss_port,
        token=token, fingerprint=fingerprint,
        reconnect=False,
    )
    client_task = asyncio.create_task(client.run())
    await asyncio.wait_for(tunnel.connected.wait(), timeout=5)

    # CONNECT 请求
    reader, writer = await asyncio.open_connection('127.0.0.1', proxy_port)
    connect_req = f'CONNECT 127.0.0.1:{target_port} HTTP/1.1\r\n\r\n'.encode()
    writer.write(connect_req)
    await writer.drain()

    # 等待 200 Connection Established
    status_line = await asyncio.wait_for(reader.readline(), timeout=5)
    assert b'200' in status_line

    # 跳过响应头
    while (await reader.readline()) != b'\r\n':
        pass

    # 通过已建立的隧道发送 HTTP 请求
    http_req = b'GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n'
    writer.write(http_req)
    await writer.drain()

    # 读取响应
    response = b''
    try:
        while True:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=5)
            if not chunk:
                break
            response += chunk
    except asyncio.TimeoutError:
        pass

    writer.close()

    assert b'200 OK' in response
    assert b'Hello, World!' in response

    client_task.cancel()
    try:
        await client_task
    except asyncio.CancelledError:
        pass
    wss_server.close()
    proxy_server.close()


@pytest.mark.asyncio
async def test_disguise_page(cert_dir):
    """测试伪装页面响应。"""
    import ssl as _ssl

    cert_path_dir, token, fingerprint = cert_dir

    ssl_ctx = _ssl.SSLContext(_ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(
        os.path.join(cert_path_dir, 'cert.pem'),
        os.path.join(cert_path_dir, 'key.pem'),
    )

    from tunnel_server import TunnelManager, WSSServer
    tunnel = TunnelManager()
    wss = WSSServer(tunnel, token, ssl_ctx)
    wss_server = await wss.start('127.0.0.1', 0)
    wss_port = wss_server.sockets[0].getsockname()[1]

    # 用 HTTPS 请求访问根路径
    client_ctx = _ssl.SSLContext(_ssl.PROTOCOL_TLS_CLIENT)
    client_ctx.check_hostname = False
    client_ctx.verify_mode = _ssl.CERT_NONE

    reader, writer = await asyncio.open_connection(
        '127.0.0.1', wss_port, ssl=client_ctx,
    )
    writer.write(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
    await writer.drain()

    response = b''
    try:
        while True:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
            if not chunk:
                break
            response += chunk
    except asyncio.TimeoutError:
        pass

    writer.close()

    assert b'Test Dashboard' in response
    assert b'nginx/1.24.0' in response

    wss_server.close()
```

- [x] **Step 2: 安装测试依赖**

```bash
pip install pytest pytest-asyncio
```

- [x] **Step 3: 运行集成测试**

```bash
cd dev_project/proxy-tunnel/wss-tunnel && python -m pytest tests/test_integration.py -v --timeout=30
```

预期：3 tests PASSED。如果有失败，根据报错调试。

注意：集成测试依赖 `websockets` 库和 `openssl` CLI。`pytest-asyncio` 需要在 `conftest.py` 或 `pyproject.toml` 中配置 `asyncio_mode = "auto"`。

写入 `tests/conftest.py`:

```python
import pytest

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
```

并在 `wss-tunnel/` 下创建 `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [x] **Step 4: Commit**

```bash
git add dev_project/proxy-tunnel/wss-tunnel/tests/ \
        dev_project/proxy-tunnel/wss-tunnel/pyproject.toml
git commit -m "test(wss-tunnel): add integration tests for HTTP, CONNECT, and disguise page"
```

---

## Task 9: setup_linux.sh — Linux 端辅助脚本

**Files:**
- Create: `dev_project/proxy-tunnel/wss-tunnel/setup_linux.sh`

- [x] **Step 1: 编写辅助脚本**

创建 `dev_project/proxy-tunnel/wss-tunnel/setup_linux.sh`:

```bash
#!/bin/bash
# WSS 隧道方案 — Linux 端代理配置脚本
# 用法: source setup_linux.sh [proxy_port]

PROXY_PORT="${1:-8054}"
PROXY_URL="http://127.0.0.1:${PROXY_PORT}"

echo "=== WSS 隧道代理配置 ==="
echo "代理地址: $PROXY_URL"
echo ""

# 1. 检查代理是否可达
echo -n "检查 Local Proxy... "
if nc -z 127.0.0.1 "$PROXY_PORT" -w 3 2>/dev/null; then
    echo "✓ 端口 $PROXY_PORT 可达"
else
    echo "✗ 端口 $PROXY_PORT 不可达，请先启动 tunnel_server.py"
    return 1 2>/dev/null || exit 1
fi

# 2. 设置环境变量
export http_proxy="$PROXY_URL"
export https_proxy="$PROXY_URL"
export HTTP_PROXY="$PROXY_URL"
export HTTPS_PROXY="$PROXY_URL"
export no_proxy="localhost,127.0.0.1,::1"
export NO_PROXY="$no_proxy"

echo ""
echo "已设置环境变量:"
echo "  http_proxy=$http_proxy"
echo "  https_proxy=$https_proxy"
echo "  no_proxy=$no_proxy"
echo ""
echo "验证: curl http://httpbin.org/ip"
echo "取消: unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY"
```

- [x] **Step 2: 设置执行权限**

```bash
chmod +x dev_project/proxy-tunnel/wss-tunnel/setup_linux.sh
```

- [x] **Step 3: Commit**

```bash
git add dev_project/proxy-tunnel/wss-tunnel/setup_linux.sh
git commit -m "feat(wss-tunnel): add Linux proxy setup helper script"
```

---

## Task 10: websockets 版本兼容性检查与修复

`websockets` 库在不同大版本之间 API 有较大变化（v10/v11/v12/v13）。此任务确保代码兼容当前最新版本。

**Files:**
- Modify: `dev_project/proxy-tunnel/wss-tunnel/tunnel_server.py` (可能)
- Modify: `dev_project/proxy-tunnel/wss-tunnel/tunnel_client.py` (可能)

- [x] **Step 1: 确认 websockets 版本**

```bash
python -c "import websockets; print(websockets.__version__)"
```

记录版本号。关键 API 差异：

| API | v10-v11 | v12-v13 (新) |
|-----|---------|-------------|
| `websockets.serve()` | `handler(ws, path)` | `handler(ws)` (path 在 ws.request.path) |
| `process_request` | `callback(path, headers)` 返回 tuple 拦截 | `callback(ws, request)` 返回 Response 拦截 |
| `websockets.connect()` | `subprotocols=` | `additional_headers=` 或 `subprotocols=` |

- [x] **Step 2: 如果 websockets >= 13，调整 API**

检查 `tunnel_server.py` 中 `WSSServer` 的 `_handler` 和 `_process_http_request` 签名：

**v13+ 的 `websockets.serve()` handler 只接受 `(ws)` 而非 `(ws, path)`：**

如果 handler 签名需要修改，更新为：
```python
async def _handler(self, websocket):
    """处理已认证的 WSS 连接。"""
    ...
```

**v13+ 的 `process_request` 签名变为 `(ws, request)`：**

如果需要修改，检查新版文档并调整签名和返回值格式。

- [x] **Step 3: 重新运行集成测试**

```bash
cd dev_project/proxy-tunnel/wss-tunnel && python -m pytest tests/test_integration.py -v --timeout=30
```

预期：3 tests PASSED

- [x] **Step 4: 如有修改则 Commit**

```bash
git add dev_project/proxy-tunnel/wss-tunnel/
git commit -m "fix(wss-tunnel): ensure websockets API compatibility with installed version"
```

---

## Task 11: 最终验证与文档更新

**Files:**
- Modify: `dev_project/proxy-tunnel/wss-tunnel-design.md` (如有变化)

- [x] **Step 1: 运行全部测试**

```bash
cd dev_project/proxy-tunnel/wss-tunnel && python -m pytest tests/ -v --timeout=30
```

预期：所有测试 PASSED

- [x] **Step 2: 手动端到端验证**

```bash
# 终端 1: 初始化 + 启动 server
cd dev_project/proxy-tunnel/wss-tunnel
python tunnel_server.py --init --cert-dir /tmp/wss-test
python tunnel_server.py --cert-dir /tmp/wss-test --wss-port 8044 --proxy-port 8054

# 终端 2: 查看 config 获取 token 和 fingerprint，启动 client
cat /tmp/wss-test/server.json
python tunnel_client.py --host 127.0.0.1 --port 8044 --token <token> --fingerprint <fingerprint>

# 终端 3: 测试代理
curl -x http://127.0.0.1:8054 http://httpbin.org/ip
curl -x http://127.0.0.1:8054 https://httpbin.org/ip

# 测试伪装页面
curl -k https://127.0.0.1:8044/

# 清理
rm -rf /tmp/wss-test
```

- [x] **Step 3: Final Commit**

```bash
git add -A dev_project/proxy-tunnel/
git commit -m "feat(wss-tunnel): complete WSS tunnel proxy with TLS, disguise, and tests"
```
