"""Shared utilities for WSS tunnel — message protocol, cert & token management.

Uses only Python stdlib. No third-party dependencies.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Task 1 — Message protocol
# ---------------------------------------------------------------------------


def make_msg(msg_type: str, stream_id: str, **kwargs) -> str:
    """Build a JSON message string.

    If *payload* is ``bytes``, it is base64-encoded before serialisation.
    """
    msg: dict = {"type": msg_type, "stream_id": stream_id}
    for key, value in kwargs.items():
        if key == "payload" and isinstance(value, bytes):
            msg[key] = base64.b64encode(value).decode("ascii")
        else:
            msg[key] = value
    return json.dumps(msg)


def parse_msg(raw: str) -> dict:
    """Parse a JSON message string.

    For ``data`` messages the *payload* field is base64-decoded back to
    ``bytes``.  Raises ``ValueError`` on invalid JSON or missing ``type``.
    """
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    if "type" not in msg:
        raise ValueError("missing required field: type")

    # Decode base64 payload for data messages
    if msg["type"] == "data" and "payload" in msg:
        try:
            msg["payload"] = base64.b64decode(msg["payload"])
        except Exception:
            pass  # leave as-is if not valid base64

    return msg


def generate_stream_id() -> str:
    """Return an 8-byte random hex string (16 hex characters)."""
    return secrets.token_hex(8)


# ---------------------------------------------------------------------------
# Task 2 — Cert & token management
# ---------------------------------------------------------------------------


def generate_token() -> str:
    """Return a 32-byte random hex string (64 hex characters)."""
    return secrets.token_hex(32)


def save_config(config: dict, path: str | os.PathLike) -> None:
    """Save *config* as JSON to *path* with mode 600."""
    p = Path(path)
    p.write_text(json.dumps(config, indent=2), encoding="utf-8")
    os.chmod(p, 0o600)


def load_config(path: str | os.PathLike) -> dict:
    """Load and return a JSON config from *path*."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def generate_self_signed_cert(
    cert_dir: str | os.PathLike,
    days: int = 365,
) -> tuple[str, str]:
    """Generate a self-signed TLS certificate using the ``openssl`` CLI.

    Returns ``(cert_path, key_path)`` — both with mode 600.
    """
    cert_dir = Path(cert_dir)
    cert_dir.mkdir(parents=True, exist_ok=True)

    cert_path = cert_dir / "cert.pem"
    key_path = cert_dir / "key.pem"

    subprocess.run(
        [
            "openssl", "req",
            "-x509",
            "-newkey", "rsa:2048",
            "-nodes",
            "-days", str(days),
            "-subj", "/CN=Internal Dashboard/O=System/C=US",
            "-keyout", str(key_path),
            "-out", str(cert_path),
        ],
        check=True,
        capture_output=True,
    )

    os.chmod(cert_path, 0o600)
    os.chmod(key_path, 0o600)

    return str(cert_path), str(key_path)


def get_cert_fingerprint(cert_path: str | os.PathLike) -> str:
    """Return the SHA-256 fingerprint of *cert_path* as ``SHA256:<64-hex>``."""
    result = subprocess.run(
        ["openssl", "x509", "-in", str(cert_path), "-noout", "-fingerprint", "-sha256"],
        check=True,
        capture_output=True,
        text=True,
    )
    # Output looks like: sha256 Fingerprint=AA:BB:CC:...
    # or: SHA256 Fingerprint=AA:BB:CC:...
    line = result.stdout.strip()
    hex_with_colons = line.split("=", 1)[1]
    hex_str = hex_with_colons.replace(":", "").lower()
    return f"SHA256:{hex_str}"
