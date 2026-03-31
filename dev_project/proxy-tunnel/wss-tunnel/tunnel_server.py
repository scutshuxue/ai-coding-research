#!/usr/bin/env python3
"""WSS Tunnel Server — TLS WebSocket server + local HTTP/HTTPS proxy.

Linux-side component that:
1. Accepts a single WSS client (tunnel_client) with token auth
2. Serves a disguise HTML page for non-WS requests
3. Runs a local HTTP/HTTPS proxy that forwards traffic through the WSS tunnel
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import ssl
import sys
from pathlib import Path

import websockets
from websockets import Headers, Request, Response

from tunnel_common import (
    generate_self_signed_cert,
    generate_stream_id,
    generate_token,
    get_cert_fingerprint,
    load_config,
    make_msg,
    parse_msg,
    save_config,
)

logger = logging.getLogger("tunnel_server")

# ---------------------------------------------------------------------------
# Disguise pages
# ---------------------------------------------------------------------------

DISGUISE_PAGE = b"""\
<!DOCTYPE html>
<html>
<head><title>Test Dashboard</title></head>
<body>
<h1>System Status</h1>
<p>All services passed.</p>
</body>
</html>"""

PAGE_404 = b"""\
<!DOCTYPE html>
<html>
<head><title>404 Not Found</title></head>
<body>
<h1>404 Not Found</h1>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 1. TunnelManager
# ---------------------------------------------------------------------------


class TunnelManager:
    """Manages the single WSS connection and multiplexed streams."""

    def __init__(self) -> None:
        self.ws: websockets.ServerConnection | None = None
        self.streams: dict[str, asyncio.Queue] = {}
        self._connected = asyncio.Event()

    def register_client(self, ws: websockets.ServerConnection) -> None:
        self.ws = ws
        self._connected.set()
        logger.info("WSS client registered from %s", ws.remote_address)

    def unregister_client(self) -> None:
        logger.info("WSS client unregistered")
        self.ws = None
        self._connected.clear()
        # Signal all waiting streams
        for q in self.streams.values():
            q.put_nowait(None)

    def create_stream(self) -> str:
        sid = generate_stream_id()
        self.streams[sid] = asyncio.Queue()
        return sid

    def remove_stream(self, stream_id: str) -> None:
        self.streams.pop(stream_id, None)

    async def send(self, msg: str) -> None:
        if self.ws is None:
            raise RuntimeError("No WSS client connected")
        await self.ws.send(msg)

    def dispatch(self, raw: str) -> None:
        """Parse incoming message and route to the stream's queue."""
        msg = parse_msg(raw)
        sid = msg.get("id")
        if sid and sid in self.streams:
            self.streams[sid].put_nowait(msg)
        else:
            logger.debug("dispatch: unknown stream %s (type=%s)", sid, msg.get("type"))

    async def wait_for_client(self, timeout: float = 30.0) -> bool:
        try:
            await asyncio.wait_for(self._connected.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False


# ---------------------------------------------------------------------------
# 2. WSSServer
# ---------------------------------------------------------------------------


class WSSServer:
    """TLS-encrypted WebSocket server with disguise page and token auth."""

    def __init__(
        self,
        tunnel: TunnelManager,
        token: str,
        ssl_ctx: ssl.SSLContext,
    ) -> None:
        self.tunnel = tunnel
        self.token = token
        self.ssl_ctx = ssl_ctx

    def _process_request(
        self,
        connection: websockets.ServerConnection,
        request: Request,
    ) -> Response | None:
        """Handle HTTP requests before WebSocket upgrade.

        Returns a Response to reject the upgrade (serve HTTP), or None to
        allow the WebSocket handshake to proceed.
        """
        path = request.path

        # Non-WebSocket paths: serve disguise pages
        # Check if this is a WebSocket upgrade request
        upgrade = request.headers.get("Upgrade", "").lower()

        if upgrade != "websocket":
            # Pure HTTP request — serve static pages
            headers = Headers()
            headers["Server"] = "nginx/1.24.0"
            headers["Content-Type"] = "text/html; charset=utf-8"

            if path in ("/", "/index.html"):
                return Response(200, "OK", headers, DISGUISE_PAGE)
            else:
                return Response(404, "Not Found", headers, PAGE_404)

        # WebSocket upgrade request
        if path != "/ws":
            headers = Headers()
            headers["Server"] = "nginx/1.24.0"
            headers["Content-Type"] = "text/html; charset=utf-8"
            return Response(404, "Not Found", headers, PAGE_404)

        # Check token via Sec-WebSocket-Protocol header
        protocols = request.headers.get("Sec-WebSocket-Protocol", "")
        if self.token not in [p.strip() for p in protocols.split(",")]:
            headers = Headers()
            headers["Server"] = "nginx/1.24.0"
            headers["Content-Type"] = "text/plain"
            return Response(403, "Forbidden", headers, b"Forbidden")

        # Allow WebSocket handshake
        return None

    def _select_subprotocol(
        self,
        connection: websockets.ServerConnection,
        subprotocols: list[str],
    ) -> str | None:
        """Select the token as the subprotocol (required for Sec-WebSocket-Protocol)."""
        if self.token in subprotocols:
            return self.token
        return None

    async def _ws_handler(self, ws: websockets.ServerConnection) -> None:
        """Handle an established WebSocket connection."""
        if self.tunnel.ws is not None:
            logger.warning("Rejecting second WSS client")
            await ws.close(1008, "Only one client allowed")
            return

        self.tunnel.register_client(ws)
        try:
            async for raw in ws:
                if isinstance(raw, str):
                    self.tunnel.dispatch(raw)
                else:
                    logger.warning("Received binary frame, ignoring")
        except websockets.ConnectionClosed:
            logger.info("WSS client disconnected")
        finally:
            self.tunnel.unregister_client()

    async def start(self, bind: str, port: int) -> None:
        """Start the WSS server."""
        server = await websockets.serve(
            self._ws_handler,
            bind,
            port,
            ssl=self.ssl_ctx,
            process_request=self._process_request,
            select_subprotocol=self._select_subprotocol,
            server_header="nginx/1.24.0",
            max_size=4 * 1024 * 1024,  # 4 MiB
        )
        logger.info("WSS server listening on %s:%d", bind, port)
        return server


# ---------------------------------------------------------------------------
# 3. LocalProxy
# ---------------------------------------------------------------------------


class LocalProxy:
    """HTTP/HTTPS proxy that forwards traffic through the WSS tunnel."""

    def __init__(self, tunnel: TunnelManager) -> None:
        self.tunnel = tunnel

    async def start(self, bind: str, port: int) -> None:
        server = await asyncio.start_server(self._handle_client, bind, port)
        logger.info("Local proxy listening on %s:%d", bind, port)
        return server

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            await self._handle_client_inner(reader, writer)
        except Exception as exc:
            logger.debug("Proxy client error: %s", exc)
        finally:
            writer.close()
            await writer.wait_closed()

    async def _handle_client_inner(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        # Read request line
        request_line = await asyncio.wait_for(reader.readline(), timeout=10)
        if not request_line:
            return
        request_line_str = request_line.decode("utf-8", errors="replace").strip()
        parts = request_line_str.split()
        if len(parts) < 3:
            return

        method = parts[0].upper()
        target = parts[1]

        # Read headers
        headers_raw = []
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=10)
            if line in (b"\r\n", b"\n", b""):
                break
            headers_raw.append(line)

        # Check tunnel connected
        if self.tunnel.ws is None:
            error_body = b"502 Bad Gateway: tunnel not connected\r\n"
            writer.write(
                b"HTTP/1.1 502 Bad Gateway\r\n"
                b"Content-Length: " + str(len(error_body)).encode() + b"\r\n"
                b"\r\n" + error_body
            )
            await writer.drain()
            return

        if method == "CONNECT":
            await self._handle_connect(target, reader, writer)
        else:
            await self._handle_http(method, target, parts[2], headers_raw, reader, writer)

    async def _handle_connect(
        self,
        target: str,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle CONNECT method (HTTPS proxy)."""
        host, port_str = self._parse_host_port(target, 443)
        port = int(port_str)

        sid = self.tunnel.create_stream()
        try:
            # Send connect request through tunnel
            await self.tunnel.send(make_msg("connect", sid, host=host, port=port))

            # Wait for connect_ok or connect_fail
            msg = await asyncio.wait_for(self.tunnel.streams[sid].get(), timeout=10)
            if msg is None:
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                await writer.drain()
                return

            if msg["type"] == "connect_fail":
                error = msg.get("error", "connection failed")
                writer.write(
                    b"HTTP/1.1 502 Bad Gateway\r\n\r\n"
                    + error.encode()
                )
                await writer.drain()
                return

            if msg["type"] != "connect_ok":
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                await writer.drain()
                return

            # Send 200 to client
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()

            # Bidirectional relay
            await self._relay(sid, reader, writer)

        except asyncio.TimeoutError:
            writer.write(b"HTTP/1.1 504 Gateway Timeout\r\n\r\n")
            await writer.drain()
        finally:
            # Send close to tunnel
            try:
                await self.tunnel.send(make_msg("close", sid))
            except Exception:
                pass
            self.tunnel.remove_stream(sid)

    async def _handle_http(
        self,
        method: str,
        target: str,
        http_version: str,
        headers_raw: list[bytes],
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle plain HTTP proxy requests."""
        # Parse URL: http://host:port/path
        if target.startswith("http://"):
            url = target[7:]
        else:
            url = target

        slash_idx = url.find("/")
        if slash_idx == -1:
            host_part = url
            path = "/"
        else:
            host_part = url[:slash_idx]
            path = url[slash_idx:]

        host, port_str = self._parse_host_port(host_part, 80)
        port = int(port_str)

        sid = self.tunnel.create_stream()
        try:
            # Connect through tunnel
            await self.tunnel.send(make_msg("connect", sid, host=host, port=port))

            msg = await asyncio.wait_for(self.tunnel.streams[sid].get(), timeout=10)
            if msg is None or msg["type"] != "connect_ok":
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                await writer.drain()
                return

            # Reconstruct and forward the HTTP request
            request = f"{method} {path} {http_version}\r\n".encode()
            for h in headers_raw:
                request += h
            request += b"\r\n"

            # Check for request body (Content-Length)
            content_length = 0
            for h in headers_raw:
                h_lower = h.decode("utf-8", errors="replace").lower()
                if h_lower.startswith("content-length:"):
                    content_length = int(h_lower.split(":", 1)[1].strip())
                    break

            if content_length > 0:
                body = await asyncio.wait_for(
                    reader.readexactly(content_length), timeout=10
                )
                request += body

            await self.tunnel.send(make_msg("data", sid, payload=request))

            # Relay response back
            await self._relay(sid, reader, writer)

        except asyncio.TimeoutError:
            writer.write(b"HTTP/1.1 504 Gateway Timeout\r\n\r\n")
            await writer.drain()
        finally:
            try:
                await self.tunnel.send(make_msg("close", sid))
            except Exception:
                pass
            self.tunnel.remove_stream(sid)

    async def _relay(
        self,
        stream_id: str,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Bidirectional relay between local socket and WSS tunnel stream."""

        async def local_to_tunnel() -> None:
            """Read from local socket, send to tunnel."""
            try:
                while True:
                    data = await reader.read(65536)
                    if not data:
                        break
                    await self.tunnel.send(
                        make_msg("data", stream_id, payload=data)
                    )
            except (ConnectionError, asyncio.CancelledError):
                pass

        async def tunnel_to_local() -> None:
            """Read from tunnel stream queue, write to local socket."""
            try:
                while True:
                    msg = await self.tunnel.streams[stream_id].get()
                    if msg is None:
                        break
                    if msg["type"] == "data":
                        writer.write(msg["payload"])
                        await writer.drain()
                    elif msg["type"] == "close":
                        break
            except (ConnectionError, asyncio.CancelledError):
                pass

        t1 = asyncio.create_task(local_to_tunnel())
        t2 = asyncio.create_task(tunnel_to_local())
        try:
            done, pending = await asyncio.wait(
                [t1, t2], return_when=asyncio.FIRST_COMPLETED
            )
            for t in pending:
                t.cancel()
        except asyncio.CancelledError:
            t1.cancel()
            t2.cancel()

    @staticmethod
    def _parse_host_port(host_port: str, default_port: int) -> tuple[str, str]:
        if ":" in host_port:
            host, port = host_port.rsplit(":", 1)
            return host, port
        return host_port, str(default_port)


# ---------------------------------------------------------------------------
# 4. main() and CLI
# ---------------------------------------------------------------------------


def init_config(cert_dir: str) -> None:
    """Generate cert + token, save config, print info."""
    cert_dir_path = Path(cert_dir).expanduser()
    cert_dir_path.mkdir(parents=True, exist_ok=True)

    config_path = cert_dir_path / "server.json"

    # Generate cert
    cert_path, key_path = generate_self_signed_cert(cert_dir_path)
    fingerprint = get_cert_fingerprint(cert_path)

    # Generate token
    token = generate_token()

    config = {
        "cert": str(cert_path),
        "key": str(key_path),
        "token": token,
        "fingerprint": fingerprint,
    }
    save_config(config, config_path)

    print(f"[init] Config saved to: {config_path}")
    print(f"[init] Certificate:     {cert_path}")
    print(f"[init] Key:             {key_path}")
    print(f"[init] Fingerprint:     {fingerprint}")
    print(f"[init] Token:           {token}")
    print()
    print("Copy the token and fingerprint to the client config.")


async def run_server(args: argparse.Namespace) -> None:
    """Start both WSS server and local proxy."""
    cert_dir = Path(args.cert_dir).expanduser()
    config_path = cert_dir / "server.json"

    if not config_path.exists():
        print(f"Error: config not found at {config_path}")
        print("Run with --init first to generate cert and token.")
        sys.exit(1)

    config = load_config(config_path)

    # SSL context
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(config["cert"], config["key"])
    ssl_ctx.minimum_version = ssl.TLSVersion.TLSv1_2

    tunnel = TunnelManager()
    wss = WSSServer(tunnel, config["token"], ssl_ctx)
    proxy = LocalProxy(tunnel)

    wss_server = await wss.start(args.wss_bind, args.wss_port)
    proxy_server = await proxy.start(args.proxy_bind, args.proxy_port)

    logger.info(
        "Server ready. WSS=%s:%d  Proxy=%s:%d",
        args.wss_bind, args.wss_port,
        args.proxy_bind, args.proxy_port,
    )

    # Run forever
    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        wss_server.close()
        proxy_server.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="WSS Tunnel Server — TLS WebSocket + local proxy"
    )
    parser.add_argument(
        "--init", action="store_true",
        help="Generate cert + token and save config, then exit",
    )
    parser.add_argument(
        "--cert-dir", default="~/.wss-tunnel",
        help="Directory for cert, key, and config (default: ~/.wss-tunnel)",
    )
    parser.add_argument("--wss-port", type=int, default=8044)
    parser.add_argument("--wss-bind", default="0.0.0.0")
    parser.add_argument("--proxy-port", type=int, default=8054)
    parser.add_argument("--proxy-bind", default="127.0.0.1")
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if args.init:
        init_config(args.cert_dir)
        return

    asyncio.run(run_server(args))


if __name__ == "__main__":
    main()
