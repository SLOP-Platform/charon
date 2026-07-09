"""Tiny stdlib network helpers shared by the web service and the gateway.

Kept dependency-free so the gateway (ADR-0005) stays Windows-native / stdlib-only.
"""
from __future__ import annotations

import ipaddress

# Shared browser-like outbound User-Agent (P5). Cloudflare bot-protection returns
# HTTP 403 "error code: 1010" for non-browser UAs like "charon-proxy/0.1" or
# "python-urllib/*", which wrongly marks healthy, funded providers (groq/cerebras/
# together) dead. A current mainstream Chrome-on-Windows UA flips those edges to
# 200 (live-verified). Defined here — the leaf stdlib-only helper module — so every
# outbound provider/probe caller imports ONE constant and it can never drift.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.6422.113 Safari/537.36"
)


def is_loopback(host: str) -> bool:
    """True only for hosts we can PROVE are loopback (``127.0.0.0/8``, ``::1``,
    ``localhost``). Anything else — ``""``/``0.0.0.0``/``::`` (bind-all) or an
    unresolved hostname — is treated as EXPOSED, so a token guard fails safe."""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
