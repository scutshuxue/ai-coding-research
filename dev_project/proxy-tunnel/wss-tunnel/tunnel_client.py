#!/usr/bin/env python3
"""WSS Tunnel Client — connects to the Linux WSS Server, receives proxy
requests, and executes outbound TCP connections on behalf of the server.

Windows/macOS-side component.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import ssl
import sys

import websockets

from tunnel_common import make_msg, parse_msg

logger = logging.getLogger("tunnel_client")


class TunnelClient:
    """WSS tunnel client with cert fingerprint verification and auto-reconnect."""

    def __init__(
        self,
        host: str,
        port: int,
        token: str,
        fingerprint: str,
        reconnect: bool = True,
        max_retry: int = 0,
    ) -> None:
        self.host = host
        self.port = port
        self.token = token
        self.fingerprint = fingerprint.removeprefix("SHA256:").lower()
        self.reconnect = reconnect
        self.max_retry = max_retry

        # Active target connections: stream_id -> (reader, writer)
        self._connections: dict[str, tuple[asyncio.StreamReader, asyncio.StreamWriter]] = {}
        self._ws: websockets.ClientConnection | None = None
        self._tasks: set[asyncio.Task] = set()

    # ------------------------------------------------------------------
    # SSL
    # ------------------------------------------------------------------

    def _make_ssl_ctx(self) -> ssl.SSLContext:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _verify_fingerprint(self, ws: websockets.ClientConnection) -> None:
        """Verify the server certificate fingerprint after connecting."""
        transport = ws.transport
        ssl_object = transport.get_extra_info("ssl_object")
        if ssl_object is None:
            raise RuntimeError("No TLS connection — cannot verify fingerprint")
        cert_der = ssl_object.getpeercert(binary_form=True)
        if cert_der is None:
            raise RuntimeError("Server presented no certificate")
        actual = hashlib.sha256(cert_der).hexdigest()
        if actual != self.fingerprint:
            raise RuntimeError(
                f"Certificate fingerprint mismatch!\n"
                f"  expected: {self.fingerprint}\n"
                f"  actual:   {actual}"
            )
        logger.info("Certificate fingerprint verified OK")

    # ------------------------------------------------------------------
    # Main loop with reconnect
    # ------------------------------------------------------------------

    async def run(self) -> None:
        retry_count = 0
        delay = 1.0

        while True:
            try:
                await self._connect_and_serve()
                # Clean disconnect — reset retry state
                retry_count = 0
                delay = 1.0
            except Exception as exc:
                logger.error("Connection lost: %s", exc)

            if not self.reconnect:
                break

            retry_count += 1
            if self.max_retry > 0 and retry_count > self.max_retry:
                logger.error("Max retry count (%d) exceeded, giving up", self.max_retry)
                break

            logger.info("Reconnecting in %.0fs (attempt %d)...", delay, retry_count)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60.0)

    # ------------------------------------------------------------------
    # Connect and serve
    # ------------------------------------------------------------------

    async def _connect_and_serve(self) -> None:
        uri = f"wss://{self.host}:{self.port}/ws"
        ssl_ctx = self._make_ssl_ctx()

        logger.info("Connecting to %s", uri)

        async with websockets.connect(
            uri,
            ssl=ssl_ctx,
            subprotocols=[self.token],
            max_size=4 * 1024 * 1024,
            additional_headers={"User-Agent": "Mozilla/5.0"},
        ) as ws:
            self._ws = ws
            self._verify_fingerprint(ws)
            logger.info("Connected to server")

            try:
                async for raw in ws:
                    if isinstance(raw, str):
                        task = asyncio.create_task(self._handle_message(raw))
                        self._tasks.add(task)
                        task.add_done_callback(self._tasks.discard)
                    else:
                        logger.warning("Received binary frame, ignoring")
            except websockets.ConnectionClosed:
                logger.info("Server disconnected")
            finally:
                self._ws = None
                await self._close_all_connections()

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    async def _handle_message(self, raw: str) -> None:
        try:
            msg = parse_msg(raw)
        except ValueError as exc:
            logger.warning("Invalid message: %s", exc)
            return

        msg_type = msg["type"]
        sid = msg.get("id", "")

        if msg_type == "connect":
            await self._handle_connect(sid, msg.get("host", ""), msg.get("port", 0))
        elif msg_type == "data":
            await self._handle_data(sid, msg.get("payload", b""))
        elif msg_type == "close":
            await self._handle_close(sid)
        else:
            logger.debug("Unknown message type: %s", msg_type)

    async def _handle_connect(self, sid: str, host: str, port: int) -> None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=10,
            )
            self._connections[sid] = (reader, writer)
            logger.info("Connected to target %s:%d (stream %s)", host, port, sid)
            await self._ws_send(make_msg("connect_ok", sid))
            # Start reading from the target
            task = asyncio.create_task(self._read_from_target(sid, reader))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        except Exception as exc:
            logger.warning("Failed to connect to %s:%d — %s", host, port, exc)
            await self._ws_send(make_msg("connect_fail", sid, error=str(exc)))

    async def _handle_data(self, sid: str, payload: bytes) -> None:
        conn = self._connections.get(sid)
        if conn is None:
            logger.debug("Data for unknown stream %s", sid)
            return
        _, writer = conn
        try:
            writer.write(payload)
            await writer.drain()
        except Exception as exc:
            logger.debug("Write to target failed (stream %s): %s", sid, exc)
            await self._close_stream(sid)

    async def _handle_close(self, sid: str) -> None:
        await self._close_stream(sid)

    # ------------------------------------------------------------------
    # Target reading
    # ------------------------------------------------------------------

    async def _read_from_target(self, sid: str, reader: asyncio.StreamReader) -> None:
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                await self._ws_send(make_msg("data", sid, payload=data))
        except (ConnectionError, asyncio.CancelledError):
            pass
        except Exception as exc:
            logger.debug("Read from target error (stream %s): %s", sid, exc)
        finally:
            await self._ws_send(make_msg("close", sid))
            self._remove_connection(sid)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _ws_send(self, msg: str) -> None:
        if self._ws is not None:
            try:
                await self._ws.send(msg)
            except Exception:
                pass

    async def _close_stream(self, sid: str) -> None:
        conn = self._connections.pop(sid, None)
        if conn is None:
            return
        _, writer = conn
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

    def _remove_connection(self, sid: str) -> None:
        conn = self._connections.pop(sid, None)
        if conn is None:
            return
        _, writer = conn
        try:
            writer.close()
        except Exception:
            pass

    async def _close_all_connections(self) -> None:
        sids = list(self._connections.keys())
        for sid in sids:
            await self._close_stream(sid)
        # Cancel outstanding tasks
        for task in list(self._tasks):
            task.cancel()
        logger.info("Closed %d target connections", len(sids))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="WSS Tunnel Client — connect to Linux WSS server and proxy outbound traffic"
    )
    parser.add_argument("--host", required=True, help="Linux server address")
    parser.add_argument("--port", type=int, default=9443, help="WSS port (default: 9443)")
    parser.add_argument("--token", required=True, help="Auth token")
    parser.add_argument("--fingerprint", required=True, help="Cert fingerprint SHA256:xxx")
    parser.add_argument(
        "--no-reconnect", action="store_true", help="Disable auto reconnect"
    )
    parser.add_argument(
        "--max-retry", type=int, default=0,
        help="Max reconnect attempts (0 = unlimited, default: 0)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )

    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    print("=" * 60)
    print("  WSS Tunnel Client")
    print("=" * 60)
    print(f"  Server:      {args.host}:{args.port}")
    print(f"  Reconnect:   {'OFF' if args.no_reconnect else 'ON'}")
    if not args.no_reconnect and args.max_retry > 0:
        print(f"  Max retry:   {args.max_retry}")
    print(f"  Fingerprint: {args.fingerprint[:20]}...")
    print("=" * 60)
    print()

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
        print("\nShutting down.")


if __name__ == "__main__":
    main()
