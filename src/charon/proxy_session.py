"""Session-cookie signing and key management for the gateway proxy (seam C).

Module-level constants and pure functions extracted verbatim from
proxy_server.py: HMAC-signed session cookies, key resolution, and the
enumerated GUI-route surface. proxy_server re-imports and uses these
inline; the definitions are separated so that session logic can be owned
independently of the HTTP serving shell.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qsl, urlencode, urlsplit

# ---- /charon session cookie (SR-13, AUTH-GUI-DESIGN Option C) ---------------
# Opaque, signed, stdlib-only session that authorizes the /charon/* console ONLY.
# The gateway token stays the byte-for-byte /v1/* Bearer credential; the session
# cookie is an ADDITIONAL front door for the browser and is never accepted for
# /v1/*. Signed with CHARON_SESSION_KEY (separate from the token — rotating the
# token does NOT log the operator out).
_SESSION_COOKIE = "charon_sess"
_SESSION_TTL = 30 * 24 * 3600  # 2_592_000 — 30-day sliding lifetime

# SR-13 F1: the ENUMERATED browser-console surface. Only these exact paths are
# ``is_gui`` — i.e. session-cookie-authorizable and login-redirectable. An
# un-enumerated ``/charon/*`` path is deliberately NOT here, so a stolen session
# cookie can never authorize it and it can never fall through to the billed
# data-plane forwarder (it 404s / 401s instead). Keep in sync with the routes
# consumed by console_router.try_handle_public_gui / try_handle_control_plane.
_GUI_ROUTES = frozenset({
    "", "/charon",                                    # console home
    "/charon/login", "/charon/logout",                # public auth pages
    "/charon/status", "/charon/cost", "/charon/work",  # read-only panels
    "/charon/setup", "/charon/config",                # setup UI + summary
    "/charon/providers", "/charon/models", "/charon/models/import",
    "/charon/pools", "/charon/tiers", "/charon/fallback",
    "/charon/enable", "/charon/disable", "/charon/remove",  # setup writes
    "/charon/balance",                               # DRAIN-AND-PARK re-arm
})


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign_session(session_key: str, exp: int) -> str:
    """``b64url(payload).b64url(HMAC_SHA256(key, b64url(payload)))``; the compact
    payload is ``{"exp": <unix>, "v": 1}`` — no PII, no username."""
    payload = _b64url(json.dumps({"exp": int(exp), "v": 1},
                                 separators=(",", ":")).encode("utf-8"))
    mac = hmac.new(session_key.encode("utf-8"), payload.encode("ascii"),
                   hashlib.sha256).digest()
    return f"{payload}.{_b64url(mac)}"


def _verify_session(session_key: str, raw: str, *, now: float | None = None) -> int | None:
    """Return the payload ``exp`` if ``raw`` is a valid, unexpired session for
    ``session_key``; else None. Constant-time MAC compare (``hmac.compare_digest``)
    over the presented signature — a tampered MAC or an expired ``exp`` is rejected."""
    now = time.time() if now is None else now
    parts = raw.split(".")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    payload, sig = parts
    expected = _b64url(hmac.new(session_key.encode("utf-8"),
                                payload.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        data = json.loads(_b64url_decode(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    exp = data.get("exp")
    if not isinstance(exp, int) or exp < now:
        return None
    return exp


def _resolve_session_key() -> str:
    """Get-or-create the HMAC session-signing key: ``CHARON_SESSION_KEY`` env
    override wins, else the value stored in ``secrets.json``, else generate one and
    persist it 0600 (best effort, atomic — reuses the existing secrets writer).

    NOTE: first-start generation properly belongs in the gateway/secrets bootstrap
    (a coordinated follow-on per the SR-13 scope note). This lazy resolver keeps the
    server self-contained and testable until then, and NEVER logs the key."""
    import secrets as _stdlib_secrets

    env = os.environ.get("CHARON_SESSION_KEY")
    if env:
        return env
    from . import secrets as _store
    stored = _store.load_secrets().get("CHARON_SESSION_KEY")
    if stored:
        return stored
    key = _stdlib_secrets.token_hex(32)
    try:
        _store.set_secret("CHARON_SESSION_KEY", key)
    except OSError:
        pass
    return key


def _strip_token_from_path(path: str) -> str:
    """Drop the ``token`` query param, preserving any others — used to 302 the raw
    ``?token=`` link off the address bar/history after a TOFU cookie upgrade."""
    parts = urlsplit(path)
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k != "token"]
    q = urlencode(kept)
    base = parts.path or "/charon"
    return base + ("?" + q if q else "")
