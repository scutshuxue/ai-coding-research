"""End-to-end integration tests for WSS tunnel."""

from __future__ import annotations

import asyncio
import os
import ssl
import sys

import pytest

# Ensure project root is on sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tunnel_common import generate_self_signed_cert, generate_token, get_cert_fingerprint
from tunnel_server import TunnelManager, WSSServer, LocalProxy
from tunnel_client import TunnelClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cert_dir(tmp_path):
    """Generate cert, token, and fingerprint in a temp directory."""
    cert_path, key_path = generate_self_signed_cert(tmp_path)
    token = generate_token()
    fingerprint = get_cert_fingerprint(cert_path)
    return tmp_path, token, fingerprint


@pytest.fixture
async def target_http_server():
    """Simple TCP server that responds with a fixed HTTP response."""

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            # Read the request (consume until we see end of headers)
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=5)
                if line in (b"\r\n", b"\n", b""):
                    break
            body = b"Hello, World!"
            response = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/plain\r\n"
                b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                b"Connection: close\r\n"
                b"\r\n" + body
            )
            writer.write(response)
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    yield port
    server.close()
    await server.wait_closed()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_proxy_through_tunnel(cert_dir, target_http_server):
    """Test plain HTTP proxy request through the full WSS tunnel."""
    cert_path_dir, token, fingerprint = cert_dir
    target_port = target_http_server

    # SSL context for WSS server
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(
        str(cert_path_dir / "cert.pem"),
        str(cert_path_dir / "key.pem"),
    )

    tunnel = TunnelManager()
    wss = WSSServer(tunnel, token, ssl_ctx)
    proxy = LocalProxy(tunnel)

    wss_server = await wss.start("127.0.0.1", 0)
    wss_port = list(wss_server.sockets)[0].getsockname()[1]

    proxy_server = await proxy.start("127.0.0.1", 0)
    proxy_port = proxy_server.sockets[0].getsockname()[1]

    client = TunnelClient(
        host="127.0.0.1",
        port=wss_port,
        token=token,
        fingerprint=fingerprint,
        reconnect=False,
    )
    client_task = asyncio.create_task(client.run())

    try:
        # Wait for tunnel to establish
        await asyncio.wait_for(tunnel._connected.wait(), timeout=10)

        # Connect to proxy and send HTTP request
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
        request = (
            f"GET http://127.0.0.1:{target_port}/ HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{target_port}\r\n"
            f"\r\n"
        ).encode()
        writer.write(request)
        await writer.drain()

        # Read response
        response = await asyncio.wait_for(reader.read(65536), timeout=10)
        response_str = response.decode("utf-8", errors="replace")

        assert "200 OK" in response_str
        assert "Hello, World!" in response_str

        writer.close()
        await writer.wait_closed()
    finally:
        client_task.cancel()
        try:
            await client_task
        except (asyncio.CancelledError, Exception):
            pass
        wss_server.close()
        proxy_server.close()


@pytest.mark.asyncio
async def test_connect_proxy_through_tunnel(cert_dir, target_http_server):
    """Test CONNECT proxy (HTTPS-style) through the full WSS tunnel."""
    cert_path_dir, token, fingerprint = cert_dir
    target_port = target_http_server

    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(
        str(cert_path_dir / "cert.pem"),
        str(cert_path_dir / "key.pem"),
    )

    tunnel = TunnelManager()
    wss = WSSServer(tunnel, token, ssl_ctx)
    proxy = LocalProxy(tunnel)

    wss_server = await wss.start("127.0.0.1", 0)
    wss_port = list(wss_server.sockets)[0].getsockname()[1]

    proxy_server = await proxy.start("127.0.0.1", 0)
    proxy_port = proxy_server.sockets[0].getsockname()[1]

    client = TunnelClient(
        host="127.0.0.1",
        port=wss_port,
        token=token,
        fingerprint=fingerprint,
        reconnect=False,
    )
    client_task = asyncio.create_task(client.run())

    try:
        await asyncio.wait_for(tunnel._connected.wait(), timeout=10)

        reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)

        # Send CONNECT request
        connect_req = (
            f"CONNECT 127.0.0.1:{target_port} HTTP/1.1\r\n"
            f"\r\n"
        ).encode()
        writer.write(connect_req)
        await writer.drain()

        # Read CONNECT response — skip headers until blank line
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=10)
            if line == b"\r\n" or line == b"\n" or line == b"":
                break
            # First line should contain "200"
            if b"HTTP" in line:
                assert b"200" in line

        # Now send HTTP request through the established tunnel
        http_req = (
            f"GET / HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{target_port}\r\n"
            f"\r\n"
        ).encode()
        writer.write(http_req)
        await writer.drain()

        response = await asyncio.wait_for(reader.read(65536), timeout=10)
        response_str = response.decode("utf-8", errors="replace")

        assert "Hello, World!" in response_str

        writer.close()
        await writer.wait_closed()
    finally:
        client_task.cancel()
        try:
            await client_task
        except (asyncio.CancelledError, Exception):
            pass
        wss_server.close()
        proxy_server.close()


@pytest.mark.asyncio
async def test_disguise_page(cert_dir):
    """Test that non-WebSocket requests get the disguise page."""
    cert_path_dir, token, fingerprint = cert_dir

    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(
        str(cert_path_dir / "cert.pem"),
        str(cert_path_dir / "key.pem"),
    )

    tunnel = TunnelManager()
    wss = WSSServer(tunnel, token, ssl_ctx)

    wss_server = await wss.start("127.0.0.1", 0)
    wss_port = list(wss_server.sockets)[0].getsockname()[1]

    try:
        # Make HTTPS request to root path
        client_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        client_ssl.check_hostname = False
        client_ssl.verify_mode = ssl.CERT_NONE

        reader, writer = await asyncio.open_connection(
            "127.0.0.1", wss_port, ssl=client_ssl
        )

        writer.write(b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        await writer.drain()

        response = await asyncio.wait_for(reader.read(65536), timeout=10)
        response_str = response.decode("utf-8", errors="replace")

        assert "Internal Dashboard" in response_str
        assert "nginx/1.24.0" in response_str

        writer.close()
        await writer.wait_closed()
    finally:
        wss_server.close()
