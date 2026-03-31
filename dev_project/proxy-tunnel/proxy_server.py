#!/usr/bin/env python3
"""
正向 HTTP/HTTPS 代理服务器（Windows 端运行）
支持 Basic Auth 认证，配合 SSH 反向隧道让 Linux 借用 Windows 网络。

用法:
    python proxy_server.py                          # 默认 18080 端口
    python proxy_server.py --port 8888              # 指定端口
    python proxy_server.py --user admin --pass s3cr # 指定账号密码
    python proxy_server.py --no-auth                # 关闭认证（仅测试用）

SSH 反向隧道:
    ssh -R 18080:127.0.0.1:18080 user@linux-server

Linux 端使用:
    export http_proxy=http://proxy:proxy123@127.0.0.1:18080
    export https_proxy=http://proxy:proxy123@127.0.0.1:18080
    curl http://example.com
"""

import argparse
import base64
import logging
import select
import socket
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('proxy')

# ── 全局配置 ──────────────────────────────────────────────

AUTH_ENABLED = True
AUTH_USER = 'proxy'
AUTH_PASS = 'proxy123'
BUFFER_SIZE = 65536
TUNNEL_TIMEOUT = 60
# 对来自这些地址的请求跳过认证（SSH 隧道走 127.0.0.1，安全可控）
AUTH_WHITELIST = {'127.0.0.1', '::1'}


def check_auth(headers, client_ip: str = '') -> bool:
    """验证 Proxy-Authorization 头，白名单 IP 免认证"""
    if not AUTH_ENABLED:
        return True
    if client_ip in AUTH_WHITELIST:
        return True
    auth = headers.get('Proxy-Authorization', '')
    if not auth.startswith('Basic '):
        return False
    try:
        decoded = base64.b64decode(auth[6:]).decode('utf-8')
        user, passwd = decoded.split(':', 1)
        return user == AUTH_USER and passwd == AUTH_PASS
    except Exception:
        return False


def relay(sock_a, sock_b):
    """双向转发数据，直到任一端关闭"""
    sockets = [sock_a, sock_b]
    try:
        while True:
            readable, _, errored = select.select(sockets, [], sockets, TUNNEL_TIMEOUT)
            if errored:
                break
            if not readable:
                break  # 超时
            for s in readable:
                data = s.recv(BUFFER_SIZE)
                if not data:
                    return
                target = sock_b if s is sock_a else sock_a
                target.sendall(data)
    except (OSError, ConnectionError):
        pass
    finally:
        for s in sockets:
            try:
                s.close()
            except OSError:
                pass


class ProxyHandler(BaseHTTPRequestHandler):
    """处理 HTTP 代理请求（GET/POST 等）和 HTTPS CONNECT 隧道"""

    # 抑制默认日志
    def log_message(self, fmt, *args):
        pass

    def _auth_failed(self):
        self.send_response(407)
        self.send_header('Proxy-Authenticate', 'Basic realm="Proxy"')
        self.send_header('Content-Length', '0')
        self.end_headers()
        log.warning(f'AUTH FAIL  {self.client_address[0]}')

    # ── CONNECT（HTTPS 隧道） ──────────────────────────────

    def do_CONNECT(self):
        if not check_auth(self.headers, self.client_address[0]):
            self._auth_failed()
            return

        host, port = self._parse_host_port(self.path, default_port=443)
        log.info(f'CONNECT  {host}:{port}  from {self.client_address[0]}')

        try:
            remote = socket.create_connection((host, port), timeout=10)
        except Exception as e:
            self.send_error(502, f'Cannot connect to {host}:{port}: {e}')
            return

        self.send_response(200, 'Connection Established')
        self.end_headers()

        # 双向转发
        relay(self.connection, remote)

    # ── 普通 HTTP 请求 ────────────────────────────────────

    def do_GET(self):
        self._proxy_request()

    def do_POST(self):
        self._proxy_request()

    def do_PUT(self):
        self._proxy_request()

    def do_DELETE(self):
        self._proxy_request()

    def do_HEAD(self):
        self._proxy_request()

    def do_OPTIONS(self):
        self._proxy_request()

    def do_PATCH(self):
        self._proxy_request()

    def _proxy_request(self):
        if not check_auth(self.headers, self.client_address[0]):
            self._auth_failed()
            return

        url = urlparse(self.path)
        host, port = self._parse_host_port(url.netloc, default_port=80)
        path = url.path or '/'
        if url.query:
            path += '?' + url.query

        log.info(f'{self.command:7s}  {self.path}  from {self.client_address[0]}')

        try:
            remote = socket.create_connection((host, port), timeout=10)
        except Exception as e:
            self.send_error(502, f'Cannot connect to {host}:{port}: {e}')
            return

        try:
            # 构造转发请求
            req_line = f'{self.command} {path} HTTP/1.1\r\n'
            headers = ''
            for key, val in self.headers.items():
                # 跳过代理相关头
                if key.lower() in ('proxy-authorization', 'proxy-connection'):
                    continue
                headers += f'{key}: {val}\r\n'
            headers += f'Host: {url.netloc}\r\n'
            headers += 'Connection: close\r\n'

            remote.sendall((req_line + headers + '\r\n').encode())

            # 转发请求体
            content_len = int(self.headers.get('Content-Length', 0))
            if content_len > 0:
                body = self.rfile.read(content_len)
                remote.sendall(body)

            # 读取并转发响应
            response = b''
            while True:
                chunk = remote.recv(BUFFER_SIZE)
                if not chunk:
                    break
                response += chunk

            self.wfile.write(response)
        except Exception as e:
            log.error(f'Relay error: {e}')
        finally:
            remote.close()

    # ── 工具方法 ──────────────────────────────────────────

    @staticmethod
    def _parse_host_port(addr: str, default_port: int = 80):
        if ':' in addr:
            host, port_str = addr.rsplit(':', 1)
            try:
                return host, int(port_str)
            except ValueError:
                return addr, default_port
        return addr, default_port


class ThreadedHTTPServer(HTTPServer):
    """每个请求一个线程"""
    daemon_threads = True

    def process_request(self, request, client_address):
        t = threading.Thread(target=self._handle, args=(request, client_address))
        t.daemon = True
        t.start()

    def _handle(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)


def main():
    global AUTH_ENABLED, AUTH_USER, AUTH_PASS

    parser = argparse.ArgumentParser(description='HTTP/HTTPS 正向代理（配合 SSH 反向隧道）')
    parser.add_argument('--port', type=int, default=18080, help='监听端口 (默认 18080)')
    parser.add_argument('--bind', default='127.0.0.1', help='绑定地址 (默认 127.0.0.1)')
    parser.add_argument('--user', default='proxy', help='认证用户名 (默认 proxy)')
    parser.add_argument('--pass', dest='password', default='proxy123', help='认证密码 (默认 proxy123)')
    parser.add_argument('--no-auth', action='store_true', help='关闭认证')
    args = parser.parse_args()

    AUTH_USER = args.user
    AUTH_PASS = args.password
    AUTH_ENABLED = not args.no_auth

    server = ThreadedHTTPServer((args.bind, args.port), ProxyHandler)
    auth_info = f'{AUTH_USER}:{AUTH_PASS}' if AUTH_ENABLED else '无认证'

    print(f'''
╔══════════════════════════════════════════════════════════╗
║  HTTP/HTTPS 正向代理服务器                                ║
╠══════════════════════════════════════════════════════════╣
║  监听地址:  {args.bind}:{args.port:<39s}  ║
║  认证信息:  {auth_info:<43s}  ║
╠══════════════════════════════════════════════════════════╣
║  下一步:                                                  ║
║  1. 建立 SSH 反向隧道:                                    ║
║     ssh -R {args.port}:127.0.0.1:{args.port} user@linux  {" " * (25 - len(str(args.port)) * 2)}║
║                                                          ║
║  2. Linux 端配置代理:                                     ║
║     export http_proxy=http://{auth_info}@127.0.0.1:{args.port}{" " * max(0, 14 - len(auth_info) - len(str(args.port)))}║
║     export https_proxy=$http_proxy                       ║
╚══════════════════════════════════════════════════════════╝
''')
    print('Ctrl+C 停止\n')

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n代理服务器已停止')
        server.server_close()


if __name__ == '__main__':
    main()
