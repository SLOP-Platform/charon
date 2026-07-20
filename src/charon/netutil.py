"""Tiny stdlib network helpers shared by the web service and the gateway.

Kept dependency-free so the gateway (ADR-0005) stays Windows-native / stdlib-only.

KEY-EGRESS CHOKE POINT — :func:`keyed_request` is the ONLY place in the tree that
attaches an ``Authorization`` header to an outbound request, and :func:`open_keyed`
is the ONLY place that sends one. Both facts are enforced mechanically by
``tools/check_security.py`` (check ``(e)``), because three consecutive rounds of
the provider-key-exfil fix worked by hand-enumerating the key-bearing call sites
and each round missed one — the forwarder (the highest-volume site of all) was
still following redirects with the provider key attached after round 4. Making the
unsafe request *unrepresentable* is the only version of this fix that cannot be
re-broken by adding a new call site.
"""
from __future__ import annotations

import ipaddress
import urllib.request
from collections.abc import Mapping
from urllib.parse import urlsplit

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


# ---------------------------------------------------------------------------
# The key-egress choke point (see the module docstring).
# ---------------------------------------------------------------------------


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse to follow redirects. A key-bearing request carries the provider key
    as an ``Authorization`` header and urllib does **not** strip that header
    cross-host, so a ``302`` from an upstream would hand the operator's key to
    whatever host the ``Location`` points at. Every outbound request in the tree
    goes through :func:`open_keyed`, so no send site can opt back in."""

    def redirect_request(self, *a, **k):  # noqa: ANN002, ANN003
        return None


# Stamped on requests built by keyed_request; open_keyed refuses anything else, so
# a hand-rolled Request can never reach the wire through the shared opener.
_KEYED_MARK = "_charon_keyed"


def validate_base_url(base_url: str) -> str:
    """Validate ``base_url`` and return it with trailing slashes stripped.

    Refuses non-http(s) schemes and link-local / cloud-metadata hosts (the SSRF
    guard). Lives here — the leaf module every send site already imports — so the
    egress choke point can apply it without importing ``providers``;
    ``providers.validate_base_url`` re-exports it for the existing callers."""
    parts = urlsplit(base_url)
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"invalid base URL scheme {parts.scheme!r}")
    host = parts.hostname or ""
    if host.startswith("169.254.") or host == "metadata.google.internal":
        raise ValueError(f"refusing link-local / metadata host {host!r}")
    return base_url.rstrip("/")


def keyed_request(
    url: str,
    *,
    api_key: str | None = None,
    data: bytes | None = None,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    user_agent: str | None = BROWSER_UA,
    auth_scheme: str = "Bearer",
) -> urllib.request.Request:
    """Build an outbound request, optionally carrying *api_key* as credentials.

    THE single constructor of ``Authorization``-bearing requests (enforced by
    ``tools/check_security.py``). The base is SSRF-validated here rather than at
    each call site, so a send site cannot forget it. Pass the credential as
    *api_key* — an ``Authorization`` entry in *headers* is rejected outright, so a
    caller cannot smuggle one past the choke point.

    A falsy *api_key* is fine and yields an unkeyed request: the same no-redirect,
    base-validated treatment is correct for unauthenticated probes too, and having
    ONE builder is what lets the gate ban bare ``urlopen`` everywhere else.
    """
    validate_base_url(url)
    req = urllib.request.Request(url, data=data, method=method)
    for name, value in (headers or {}).items():
        if name.lower() == "authorization":
            raise ValueError(
                "pass credentials as keyed_request(api_key=...), not an Authorization header")
        req.add_header(name, value)
    if user_agent:
        req.add_header("User-Agent", user_agent)
    if api_key:
        req.add_header("Authorization", f"{auth_scheme} {api_key}")
    setattr(req, _KEYED_MARK, True)
    return req


def open_keyed(req: urllib.request.Request, *, timeout: float):  # noqa: ANN201
    """Send a request built by :func:`keyed_request`, never following redirects.

    THE single outbound sender (enforced by ``tools/check_security.py``, which
    bans ``urlopen``/``build_opener`` everywhere else). Errors propagate exactly
    as ``urlopen``'s do, so callers keep their existing ``HTTPError``/``URLError``
    handling."""
    if not getattr(req, _KEYED_MARK, False):
        raise ValueError("outbound requests must be built by netutil.keyed_request")
    return urllib.request.build_opener(_NoRedirect()).open(req, timeout=timeout)
