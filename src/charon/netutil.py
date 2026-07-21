"""Tiny stdlib network helpers shared by the web service and the gateway.

Kept dependency-free so the gateway (ADR-0005) stays Windows-native / stdlib-only.

KEY-EGRESS CONVENTION — BY CONVENTION ONLY, NOT MECHANICALLY ENFORCED.
:func:`keyed_request` is intended to be the only constructor of
``Authorization``-bearing requests and :func:`open_keyed` the only sender, and
every call site in the tree has been converted to them. That is a **convention
maintained by review**, and nothing in this repository enforces it. Six
consecutive rounds tried to enforce it mechanically and every one was defeated:
four hand-enumerated the key-bearing call sites and each missed one; round 5's
hand-rolled AST gate was beaten by an EXECUTED bare-name ``urlopen`` sender; and
round 6's Semgrep denylist was beaten by 16 transport spellings plus three
mutations of the request object these very functions hand back
(``add_unredirected_header``, direct ``.headers[...]`` assignment, and rewriting
``full_url`` after validation). **Do not read the helpers below as a security
boundary.** They reduce exposure by making the safe path the easy path; they do
not make the unsafe path unrepresentable, and no static rule can, because the
last three bypasses happen at runtime on a well-formed object.

The real invariant — that this process holds no provider credential at all —
lands in the credential-injecting reverse-proxy (credproxy) phase, not here.

**Read docs/adr/0019-provider-key-egress-choke-point.md before changing anything
in this module.** It records the full failure history, the reviewer-fallibility
record, and — critically — the fact that this module is an explicit STOPGAP. It
exists in this shape only because the core is stdlib-only today. If the LiteLLM
adopt (ADR-0017) lands, ``requests`` strips ``Authorization`` cross-host natively
via ``Session.rebuild_auth`` and ``httpx`` does not follow redirects by default,
at which point most of this file should be DELETED rather than ported.
"""
from __future__ import annotations

import ipaddress
import logging
import urllib.error
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
# The key-egress helpers (see the module docstring: convention, not enforcement).
# ---------------------------------------------------------------------------


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse to follow redirects. A key-bearing request carries the provider key
    as an ``Authorization`` header and urllib does **not** strip that header
    cross-host, so a ``302`` from an upstream would hand the operator's key to
    whatever host the ``Location`` points at. Every send site in the tree has been
    converted to :func:`open_keyed`; nothing stops a future one from not being."""

    def redirect_request(self, *a, **k):  # noqa: ANN002, ANN003
        return None


# Built ONCE at import. `urllib.request.build_opener` instantiates `HTTPSHandler`,
# which calls `ssl.create_default_context()` — a full system CA-trust-store load,
# measured at ~12.4 ms — so building it per request added ~12.7 ms of GIL-holding
# CPU to EVERY outbound call: both forwarder legs, every discover/keyprobe/balance
# probe, and (worst) `speculative_execution`'s N-way thread race, which serialises
# on it because the cost is CPU-bound C work. `OpenerDirector.open` holds no
# per-request state, so a module-global instance is safe to share across threads.
# The default `ProxyHandler` is retained, so HTTP_PROXY/HTTPS_PROXY still work —
# but note it snapshots `getproxies()` at import rather than per call.
_OPENER = urllib.request.build_opener(_NoRedirect())


class _KeyedRequest(urllib.request.Request):
    """A request that PROVABLY came from :func:`keyed_request`.

    Round 5 used a ``setattr(req, "_charon_keyed", True)`` stamp instead, which
    made the docstring's "keyed_request is the ONLY constructor" claim false: a
    hand-rolled ``Request`` plus the same one-line ``setattr`` reached the wire
    having skipped both the SSRF validation and the Authorization-smuggling
    rejection (round-5 review, H4). A private subclass cannot be forged by
    setting an attribute — a caller would have to reach into this module's
    privates and instantiate this class, at which point they are inside the
    choke point rather than around it.
    """


# Hostnames that resolve to a cloud metadata endpoint. Blocking the IP is not
# enough because these names are what the docs and exploit tooling actually use.
_METADATA_HOSTS = frozenset({
    "metadata.google.internal",
    "metadata.goog",
    "metadata",
    "instance-data",
})


def _parse_permissive_ipv4(host: str) -> ipaddress.IPv4Address | None:
    """Parse *host* the way the C resolver's ``inet_aton`` does, or return None.

    ``ipaddress.ip_address`` is deliberately STRICT: it rejects ``2852039166``,
    ``0xA9FEA9FE``, ``0250.0376.0251.0376`` and zero-padded octets (the latter a
    2021 CVE fix). But ``socket``/``inet_aton`` — which is what urllib actually
    connects through — accepts every one of them, and they all denote the cloud
    metadata address. Round 5's guard string-matched the dotted-quad prefix and
    so passed all of them straight through to the metadata endpoint.

    inet_aton also accepts 1-, 2- and 3-part forms, where the final part absorbs
    the remaining bytes (``169.16689662`` is that same address again).
    """
    parts = host.split(".")
    if not 1 <= len(parts) <= 4:
        return None
    values: list[int] = []
    for part in parts:
        if not part:
            return None
        text = part.lower()
        try:
            if text.startswith("0x"):
                values.append(int(text, 16))
            elif text.startswith("0") and len(text) > 1:
                values.append(int(text, 8))
            else:
                values.append(int(text, 10))
        except ValueError:
            return None
    if any(v < 0 for v in values):
        return None
    # The last part absorbs every byte the earlier parts did not name.
    packed = 0
    for i, value in enumerate(values[:-1]):
        if value > 0xFF:
            return None
        packed |= value << (8 * (3 - i))
    tail_width = 8 * (4 - len(values) + 1)
    if values[-1] >= (1 << tail_width):
        return None
    packed |= values[-1]
    try:
        return ipaddress.IPv4Address(packed)
    except ipaddress.AddressValueError:
        return None


def _candidate_addresses(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Every address *host* could denote, with IPv6 wrappers unwrapped.

    Unwrapping matters: an IPv4-MAPPED IPv6 form of the metadata address reports
    ``is_link_local == False``, because IPv6 link-local means fe80::/10. Checking
    the wrapper alone therefore lets the mapped form of the metadata address
    through — so the embedded IPv4 address is classified in its own right.
    """
    found: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    try:
        found.append(ipaddress.ip_address(host))
    except ValueError:
        pass
    permissive = _parse_permissive_ipv4(host)
    if permissive is not None:
        found.append(permissive)

    unwrapped: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for addr in found:
        if isinstance(addr, ipaddress.IPv6Address):
            for embedded in (addr.ipv4_mapped, addr.sixtofour):
                if embedded is not None:
                    unwrapped.append(embedded)
    return found + unwrapped


def validate_base_url(base_url: str, *, allow_private: bool = True) -> str:
    """Validate ``base_url`` and return it with trailing slashes stripped.

    Refuses non-http(s) schemes and any host that denotes a link-local,
    multicast, reserved or unspecified address IN ANY ENCODING, plus the known
    cloud-metadata hostnames. Lives here — the leaf module every send site
    already imports — so the egress choke point can apply it without importing
    ``providers``; ``providers.validate_base_url`` re-exports it.

    ``allow_private`` defaults to True because loopback and RFC1918 bases are a
    SHIPPED, DOCUMENTED FEATURE, not an oversight: the ``lmstudio``/``jan``/
    ``ollama``/``vllm``/``local`` presets all ship ``http://localhost:PORT/v1``
    bases, and a self-hosted gateway reaching an Ollama box on the LAN is the
    product's normal case. Blocking RFC1918 wholesale would break all five
    presets. Link-local is blocked regardless, because the cloud-metadata
    endpoint lives in that range and no legitimate provider does. Callers that
    genuinely need egress restricted to public hosts pass ``allow_private=False``.

    KNOWN RESIDUAL RISK — DNS rebinding. This validates the base at the moment it
    is written, but the connection resolves the name again later, so a hostname
    that answers with a public IP here and the metadata address at connect
    time is not stopped by anything in this function. In-process validation CANNOT close that
    class. The mitigation is at the network layer — an egress allowlist (outbound
    proxy or container egress policy, derived from the provider manifest). See
    docs/adr/0019.
    """
    parts = urlsplit(base_url)
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"invalid base URL scheme {parts.scheme!r}")
    host = (parts.hostname or "").strip().rstrip(".").lower()
    if host in _METADATA_HOSTS:
        raise ValueError(f"refusing cloud-metadata host {host!r}")

    candidates = _candidate_addresses(host)

    # Link-local is checked across ALL candidates FIRST so the metadata endpoint
    # is always reported as such. Checked per-class rather than per-address
    # because `::ffff:169.254.169.254` is is_reserved as an IPv6 wrapper, so a
    # per-address loop would report the mapped metadata address as merely
    # "non-routable" and bury the fact that it is the credential-stealing one.
    for addr in candidates:
        if addr.is_link_local:
            raise ValueError(
                f"refusing link-local host {host!r} (resolves to {addr} — the cloud "
                f"metadata endpoint lives in this range)")
    for addr in candidates:
        # Loopback is exempted explicitly: `ipaddress.ip_address("::1").is_reserved`
        # is True, so a blanket reserved check silently bricks `http://[::1]:PORT`
        # — the IPv6 spelling of the localhost bases five shipped presets use.
        # Caught by test_ipv6_loopback_is_allowed, which fails without this.
        if addr.is_loopback:
            continue
        # `0.0.0.0` / `::` are exempted for the same reason as loopback: they are
        # the WILDCARD BIND address, and operators copy them out of an Ollama or
        # vLLM `--host 0.0.0.0` flag straight into a provider base_url. Master
        # accepted them and Linux connects them to loopback, so rejecting them is
        # a regression that breaks a common local-provider config with a message
        # ("non-routable host") that does not suggest `127.0.0.1`. They denote the
        # local host, which is exactly the class `allow_private` governs — so they
        # are still refused below when `allow_private=False`. Regression-pinned by
        # test_wildcard_bind_address_is_allowed.
        if addr.is_unspecified:
            continue
        if addr.is_multicast or addr.is_reserved:
            raise ValueError(f"refusing non-routable host {host!r} (resolves to {addr})")
    if not allow_private:
        for addr in candidates:
            if addr.is_private or addr.is_loopback or addr.is_unspecified:
                raise ValueError(f"refusing private/loopback host {host!r} (resolves to {addr})")

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

    The intended single constructor of ``Authorization``-bearing requests. This is
    a convention, not an enforced invariant (see the module docstring). The base is
    SSRF-validated here rather than at each call site, so a send site cannot forget
    it — but note the validation is one-shot at construction: a caller that rewrites
    ``full_url`` afterwards sends to an unvalidated host. Pass the credential as
    *api_key* — an ``Authorization`` entry in *headers* is rejected outright, so a
    caller cannot smuggle one past the choke point.

    A falsy *api_key* is fine and yields an unkeyed request: the same no-redirect,
    base-validated treatment is correct for unauthenticated probes too, and having
    ONE builder keeps the safe path the easy path.
    """
    validate_base_url(url)
    req = _KeyedRequest(url, data=data, method=method)
    for name, value in (headers or {}).items():
        if name.lower() == "authorization":
            raise ValueError(
                "pass credentials as keyed_request(api_key=...), not an Authorization header")
        req.add_header(name, value)
    if user_agent:
        req.add_header("User-Agent", user_agent)
    if api_key:
        req.add_header("Authorization", f"{auth_scheme} {api_key}")
    return req


def open_keyed(req: urllib.request.Request, *, timeout: float):  # noqa: ANN201
    """Send a request built by :func:`keyed_request`, never following redirects.

    The intended single outbound sender — by convention, not enforcement (see the
    module docstring). The :class:`_KeyedRequest` check below proves provenance
    only; it cannot prove the object was not mutated after construction. Errors
    propagate exactly as ``urlopen``'s do, so callers keep their existing
    ``HTTPError``/``URLError`` handling."""
    if not isinstance(req, _KeyedRequest):
        raise ValueError("outbound requests must be built by netutil.keyed_request")
    try:
        return _OPENER.open(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        # A refused redirect surfaces as a bare 30x with an empty body. Round 5
        # shipped that with no diagnostic anywhere: an operator whose provider
        # started 301-ing (trailing-slash canonicalisation, regional move) saw
        # their agent die on an inexplicable empty 301 with nothing in the log
        # (round-5 regression review, HIGH). Log the refusal and the host we
        # declined to hand the key to, then re-raise unchanged so every existing
        # caller's HTTPError handling is untouched.
        if 300 <= exc.code < 400:
            location = exc.headers.get("Location", "") if exc.headers else ""
            target = urlsplit(location).hostname or "(no Location header)"
            logging.warning(
                "refused redirect: %s -> %s (HTTP %s). The Authorization header is "
                "NOT stripped cross-host by urllib, so the redirect was not followed. "
                "If this provider legitimately moved, update its base_url.",
                urlsplit(req.full_url).hostname, target, exc.code)
        raise
