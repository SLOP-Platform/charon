"""Tiny stdlib network helpers shared by the web service and the gateway.

Kept dependency-free so the gateway (ADR-0005) stays Windows-native / stdlib-only.
"""
from __future__ import annotations

import ipaddress


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
