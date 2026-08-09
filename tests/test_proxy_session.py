"""Session-cookie signing and key management — direct import from proxy_session.

Proves the extracted session module (seam C) is independently importable and
its functions produce correct results — the HMAC roundtrip, expiration, and
constant-time rejections all hold when called directly on the new module.
"""
from __future__ import annotations

import os
import time

from charon.proxy_session import (
    _b64url,
    _b64url_decode,
    _resolve_session_key,
    _sign_session,
    _strip_token_from_path,
    _verify_session,
)


def test_session_sign_and_verify_roundtrip() -> None:
    """Signed session verifies with the same key — a live HMAC roundtrip."""
    key = "roundtrip-key-32-bytes-long-enough"
    exp = int(time.time()) + 3600
    token = _sign_session(key, exp)

    # Valid immediately
    assert _verify_session(key, token) == exp

    # Tampered MAC is rejected (constant-time)
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    assert _verify_session(key, tampered) is None

    # Wrong key is rejected
    assert _verify_session("wrong-key-is-different-32chars", token) is None


def test_session_expiry() -> None:
    """Expired sessions are rejected even with the correct key."""
    key = "expiry-key-32-bytes-long-enough1"
    past = int(time.time()) - 3600
    token = _sign_session(key, past)
    assert _verify_session(key, token) is None


def test_session_now_override() -> None:
    """The *now* parameter controls the expiry check — not wall-clock time."""
    key = "now-key-32-bytes-long-enough12"
    exp = 1_000_000_000
    token = _sign_session(key, exp)
    assert _verify_session(key, token, now=999_999_999) == exp
    assert _verify_session(key, token, now=1_000_000_001) is None


def test_malformed_token_rejected() -> None:
    """Garbage, empty, or wrong-format tokens are rejected."""
    key = "malformed-key-32-bytes-long12"
    assert _verify_session(key, "") is None
    assert _verify_session(key, "abc") is None
    assert _verify_session(key, "abc.def.ghi") is None


def test_b64url_roundtrip() -> None:
    """Base64url encode → decode roundtrip is lossless."""
    for raw in (b"hello", b"\x00\xff", b"pad===test"):
        assert _b64url_decode(_b64url(raw)) == raw


def test_strip_token_from_path() -> None:
    """Token is stripped but other params and path are preserved."""
    assert _strip_token_from_path("/charon?token=secret&foo=bar") == "/charon?foo=bar"
    assert _strip_token_from_path("/charon/login?token=x") == "/charon/login"
    assert _strip_token_from_path("/charon") == "/charon"
    assert _strip_token_from_path("") == "/charon"


def test_resolve_session_key_env_override() -> None:
    """CHARON_SESSION_KEY environment variable takes precedence."""
    os.environ["CHARON_SESSION_KEY"] = "env-override-key-32bytes"
    try:
        assert _resolve_session_key() == "env-override-key-32bytes"
    finally:
        os.environ.pop("CHARON_SESSION_KEY", None)
