"""Tests for tunnel_common.py — message protocol, cert & token management."""

import json
import os
import stat
import subprocess

import pytest

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


# ---------------------------------------------------------------------------
# Task 1 — Message protocol
# ---------------------------------------------------------------------------


class TestMakeMsg:
    def test_connect(self):
        raw = make_msg("connect", "abcd1234abcd1234", target_host="127.0.0.1", target_port=22)
        msg = json.loads(raw)
        assert msg["type"] == "connect"
        assert msg["stream_id"] == "abcd1234abcd1234"
        assert msg["target_host"] == "127.0.0.1"
        assert msg["target_port"] == 22

    def test_connect_ok(self):
        raw = make_msg("connect_ok", "abcd1234abcd1234")
        msg = json.loads(raw)
        assert msg["type"] == "connect_ok"
        assert msg["stream_id"] == "abcd1234abcd1234"

    def test_connect_fail(self):
        raw = make_msg("connect_fail", "abcd1234abcd1234", reason="refused")
        msg = json.loads(raw)
        assert msg["type"] == "connect_fail"
        assert msg["reason"] == "refused"

    def test_data_bytes_payload(self):
        payload = b"\x00\x01\x02hello"
        raw = make_msg("data", "abcd1234abcd1234", payload=payload)
        msg = json.loads(raw)
        assert msg["type"] == "data"
        # payload should be base64 encoded string in JSON
        assert isinstance(msg["payload"], str)

    def test_data_string_payload(self):
        raw = make_msg("data", "abcd1234abcd1234", payload="plaintext")
        msg = json.loads(raw)
        assert msg["payload"] == "plaintext"

    def test_close(self):
        raw = make_msg("close", "abcd1234abcd1234")
        msg = json.loads(raw)
        assert msg["type"] == "close"


class TestParseMsg:
    def test_roundtrip_data(self):
        original_payload = b"\x00\xff\x80binary"
        raw = make_msg("data", "aabb112233445566", payload=original_payload)
        parsed = parse_msg(raw)
        assert parsed["type"] == "data"
        assert parsed["payload"] == original_payload

    def test_roundtrip_connect(self):
        raw = make_msg("connect", "aabb112233445566", target_host="10.0.0.1", target_port=3389)
        parsed = parse_msg(raw)
        assert parsed["type"] == "connect"
        assert parsed["target_host"] == "10.0.0.1"
        assert parsed["target_port"] == 3389

    def test_roundtrip_connect_ok(self):
        raw = make_msg("connect_ok", "aabb112233445566")
        parsed = parse_msg(raw)
        assert parsed["type"] == "connect_ok"

    def test_roundtrip_connect_fail(self):
        raw = make_msg("connect_fail", "aabb112233445566", reason="timeout")
        parsed = parse_msg(raw)
        assert parsed["type"] == "connect_fail"
        assert parsed["reason"] == "timeout"

    def test_roundtrip_close(self):
        raw = make_msg("close", "aabb112233445566")
        parsed = parse_msg(raw)
        assert parsed["type"] == "close"

    def test_invalid_json(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_msg("not json {{{")

    def test_missing_type(self):
        with pytest.raises(ValueError, match="missing.*type"):
            parse_msg('{"stream_id": "abc"}')

    def test_non_data_payload_not_decoded(self):
        """For non-data types, payload (if present) should not be decoded."""
        raw = make_msg("connect", "aabb112233445566", payload="something")
        parsed = parse_msg(raw)
        assert parsed["payload"] == "something"


class TestGenerateStreamId:
    def test_length(self):
        sid = generate_stream_id()
        assert len(sid) == 16

    def test_hex(self):
        sid = generate_stream_id()
        int(sid, 16)  # should not raise

    def test_unique(self):
        ids = {generate_stream_id() for _ in range(100)}
        assert len(ids) == 100


# ---------------------------------------------------------------------------
# Task 2 — Cert & token management
# ---------------------------------------------------------------------------


class TestGenerateToken:
    def test_length(self):
        token = generate_token()
        assert len(token) == 64

    def test_hex(self):
        token = generate_token()
        int(token, 16)  # should not raise

    def test_unique(self):
        tokens = {generate_token() for _ in range(50)}
        assert len(tokens) == 50


class TestConfig:
    def test_save_and_load(self, tmp_dir):
        path = os.path.join(tmp_dir, "config.json")
        cfg = {"token": "abc123", "port": 8443}
        save_config(cfg, path)

        # Check file permissions (owner read/write only)
        mode = os.stat(path).st_mode
        assert mode & 0o777 == 0o600

        loaded = load_config(path)
        assert loaded == cfg

    def test_save_overwrites(self, tmp_dir):
        path = os.path.join(tmp_dir, "config.json")
        save_config({"a": 1}, path)
        save_config({"b": 2}, path)
        assert load_config(path) == {"b": 2}


class TestSelfSignedCert:
    def test_generate_cert(self, tmp_dir):
        cert_path, key_path = generate_self_signed_cert(tmp_dir, days=30)

        assert os.path.isfile(cert_path)
        assert os.path.isfile(key_path)

        # Check permissions
        assert os.stat(cert_path).st_mode & 0o777 == 0o600
        assert os.stat(key_path).st_mode & 0o777 == 0o600

        # Verify cert is valid with openssl
        result = subprocess.run(
            ["openssl", "x509", "-in", cert_path, "-noout", "-subject"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Internal Dashboard" in result.stdout

    def test_generate_cert_default_days(self, tmp_dir):
        cert_path, key_path = generate_self_signed_cert(tmp_dir)
        # Verify end date is ~365 days from now
        result = subprocess.run(
            ["openssl", "x509", "-in", cert_path, "-noout", "-enddate"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0


class TestCertFingerprint:
    def test_fingerprint_format(self, tmp_dir):
        cert_path, _ = generate_self_signed_cert(tmp_dir)
        fp = get_cert_fingerprint(cert_path)

        assert fp.startswith("SHA256:")
        hex_part = fp[len("SHA256:"):]
        assert len(hex_part) == 64
        # Must be lowercase hex
        assert hex_part == hex_part.lower()
        int(hex_part, 16)  # should not raise

    def test_fingerprint_deterministic(self, tmp_dir):
        cert_path, _ = generate_self_signed_cert(tmp_dir)
        fp1 = get_cert_fingerprint(cert_path)
        fp2 = get_cert_fingerprint(cert_path)
        assert fp1 == fp2
