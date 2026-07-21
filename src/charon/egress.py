"""Preset-derived egress allowlist — the Phase-1 app-layer key-exfil control.

WHY THIS IS NOT THE SIX-ROUND TRANSPORT DENYLIST (read this first).
The six failed rounds each stated the property as a universally-quantified claim
over an unbounded, growing set of in-process code paths —

    ∀ send-site in src/: the provider key does not reach a non-provider host

— and enforced it with a fail-OPEN enumeration of transports (call sites, an AST
linter, a Semgrep denylist of transport names). An unlisted transport passed, and
the space of ways Python can move bytes is not enumerable, so every round was
beaten by one more spelling. This module does the OPPOSITE and it changes the
quantifier: a narrow, fail-CLOSED ALLOWLIST of the finite set of destinations the
product is permitted to reach, checked against the EFFECTIVE (fully-resolved,
post-merge) upstream base at the one sink every completion flows through
(``routing_policy.route_from_spec``). An unknown external host is REFUSED, not
passed. Adding a byte-transport does not help an attacker whose destination is not
on the list.

SOURCE OF THE ALLOWLIST — this is the security property, not a detail.
The allowlist is derived ONLY from the git-tracked provider presets
(``src/charon/provider_presets/*.py``). It is NEVER derived from the runtime
``providers.json`` under ``$CHARON_HOME``, which the token-gated ``add_provider``
web handler writes — deriving the allowlist from attacker-writable config would
auto-admit an attacker's host the instant they add a provider (DESIGN §2.1; the
round-6 self-poisoning bug relocated to the network layer). Extending the egress
set is therefore a deliberate, out-of-band operator action (edit the presets in
git), which is exactly the point.

THE NESTED-CONFIG LESSON (LiteLLM CVE-2024-6587).
LiteLLM's first fix checked the request's FLAT top-level ``api_base`` while the
value that was actually used nested inside ``litellm_params`` — a no-op. The
correct check validates the EFFECTIVE/resolved value, not the request's top-level
shape. :func:`is_allowed_base` is applied to the base ``route_from_spec`` actually
resolved (preset ⊕ ``providers.json`` override ⊕ model spec), i.e. after every
merge; :func:`find_base_override_keys` additionally rejects a base-override key at
ANY nesting depth in a config payload.

NECESSARY, NOT SUFFICIENT. An in-process check can be bypassed at runtime
(``full_url`` mutation after validation, DNS rebinding, a future raw-socket send).
The *enforcing* control is the out-of-process egress denial — Stripe Smokescreen
made the container's only route out (Phase-1 infra, not this file). This module
closes the config-override class that the network layer cannot see the intent of,
and it is fail-closed so a poisoned ``providers.json`` entry drops the route
instead of routing a key to an attacker host. See docs/adr/0019 and DESIGN §2-4.
"""
from __future__ import annotations

import functools
import ipaddress
import logging
import os
import socket
from collections.abc import Mapping
from urllib.parse import urlsplit

from charon import netutil
from charon.provider_presets import MERGED_RAW_DATA
from charon.secrets import _normalize_host  # IDNA-consistent host folding (homoglyph-safe)

_log = logging.getLogger(__name__)


class EgressPolicyError(ValueError):
    """A destination or config payload violated the egress allowlist policy.

    Subclasses ``ValueError`` so existing handler layers that already map a bad
    request to HTTP 400 surface it as a 400 without new plumbing."""


# ---------------------------------------------------------------------------
# 1. Preset-derived hostname allowlist (validating the EFFECTIVE/nested config).
# ---------------------------------------------------------------------------


def _is_local_host(host: str) -> bool:
    """True for loopback / RFC1918-private / unspecified hosts.

    Local providers (``lmstudio``/``jan``/``ollama``/``vllm``/``local``) carry NO
    key (``key_env`` is None) and a self-hosted gateway reaching an Ollama box on
    the LAN is the product's documented normal case — ``netutil.validate_base_url``
    already permits RFC1918 for exactly this reason. These destinations are outside
    the key-exfil threat model, so they are allowed regardless of the preset set.
    Link-local is deliberately NOT treated as local here: the cloud-metadata
    endpoint lives in that range (``netutil`` rejects it upstream). The residual
    LAN-SSRF for a poisoned private base is round-6 MEDIUM-4 — ticketed, and inert
    for key exfil because ``secrets.get_provider_key`` is base-bound (no external
    key resolves for a private base)."""
    if netutil.is_loopback(host):
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        # A non-IP hostname that is not in the presets is NOT assumed local —
        # fail closed. An operator with a custom-hostname LAN provider adds it to
        # the git-tracked presets (the deliberate out-of-band step, DESIGN §2.1).
        return False
    # Link-local (169.254/16, fe80::/10) reports is_private=True in Python, but it
    # is where the cloud-metadata endpoint lives — it must NEVER count as a benign
    # local provider. Exclude it explicitly (belt-and-suspenders with netutil).
    if addr.is_link_local or addr.is_multicast or addr.is_reserved:
        return False
    return bool(addr.is_private or addr.is_unspecified or addr.is_loopback)


@functools.lru_cache(maxsize=1)
def preset_external_hosts() -> frozenset[str]:
    """The finite set of EXTERNAL hostnames the git-tracked presets reach.

    Localhost/loopback preset bases are excluded (handled by :func:`_is_local_host`).
    Cached because the presets are static in-repo data; the cache is process-local
    and never reads ``providers.json`` (DESIGN §2.1)."""
    hosts: set[str] = set()
    for data in MERGED_RAW_DATA.values():
        base = data.get("base_url")
        if not base:
            continue
        raw = (urlsplit(str(base)).hostname or "").strip().rstrip(".")
        host = _normalize_host(raw)
        if not host or _is_local_host(host):
            continue
        hosts.add(host)
    return frozenset(hosts)


def is_allowed_base(base_url: str | None) -> bool:
    """True when ``base_url``'s host is a preset external host or a local host.

    Fail-closed: an unparseable base, a non-http(s) scheme, or an EXTERNAL host
    absent from the preset allowlist all return False. This is the check applied to
    the EFFECTIVE resolved base (post preset⊕override⊕spec merge), so a poisoned
    ``providers.json`` override pointing at an attacker host is rejected regardless
    of how the value got persisted or how deeply it was nested in config."""
    if not base_url:
        return False
    try:
        parts = urlsplit(str(base_url).strip())
    except ValueError:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    try:
        raw = (parts.hostname or "").strip().rstrip(".")
    except ValueError:
        return False
    host = _normalize_host(raw)
    if not host:
        return False
    if host in preset_external_hosts():
        return True
    return _is_local_host(host)


def assert_base_allowed(base_url: str | None) -> str:
    """Return ``base_url`` if its host is allowlisted, else raise EgressPolicyError."""
    if not is_allowed_base(base_url):
        raise EgressPolicyError(
            f"refusing upstream base {base_url!r}: its host is not one of the "
            f"git-tracked provider presets and is not a local provider. Add a new "
            f"egress destination by editing src/charon/provider_presets/*.py "
            f"(a deliberate out-of-band step), not via runtime config."
        )
    return str(base_url)


# ---------------------------------------------------------------------------
# 2. Nested base-override rejection (the LiteLLM CVE-2024-6587 lesson, executable).
# ---------------------------------------------------------------------------

# Config keys that name an upstream endpoint. A caller may not steer any of these
# from a request payload — endpoints come only from the git-tracked presets.
_OVERRIDE_KEYS = frozenset({"base_url", "api_base", "upstream_base", "balance_base_url"})


def find_base_override_keys(obj: object, _path: str = "") -> list[str]:
    """Every base-override key found ANYWHERE in ``obj``, as dotted paths.

    Walks the WHOLE tree — lists and nested mappings included — because the
    LiteLLM bug was precisely that the value nested one level below where the
    guard looked. A non-empty result means a payload tried to name an upstream
    endpoint. Pure/side-effect-free so it is trivially testable (the canary
    asserts this returns ≥1 path on a known-bad fixture)."""
    found: list[str] = []
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            here = f"{_path}.{key}" if _path else str(key)
            if str(key).lower() in _OVERRIDE_KEYS:
                found.append(here)
            found.extend(find_base_override_keys(value, here))
    elif isinstance(obj, (list, tuple)):
        for i, value in enumerate(obj):
            found.extend(find_base_override_keys(value, f"{_path}[{i}]"))
    return found


def assert_no_nested_base_override(
    payload: object, *, sanctioned: frozenset[str] = frozenset({"base_url"})
) -> None:
    """Reject a config payload that names an upstream endpoint anywhere except the
    single sanctioned TOP-LEVEL field(s).

    ``{"base_url": "..."}`` is the one supported way for the web handler to name a
    base and passes. ``{"api_base": "..."}`` (a non-sanctioned top-level key) and
    ``{"litellm_params": {"api_base": "..."}}`` (the exact LiteLLM nesting) both
    RAISE — a top-level-only check would have let the second through. This runs on
    CONFIG payloads (the token-gated setup handler), never on chat-completion
    bodies, so a user's tool-schema property named ``api_base`` is not a false
    positive here."""
    offending = [p for p in find_base_override_keys(payload) if p not in sanctioned]
    if offending:
        raise EgressPolicyError(
            "a request may not override the upstream endpoint; found base-override "
            f"key(s) at: {', '.join(offending)}. Endpoints come only from the "
            "git-tracked provider presets."
        )


# ---------------------------------------------------------------------------
# 3. Startup refuse-to-serve self-test (Phase-1 variant).
# ---------------------------------------------------------------------------
#
# Phase-1 proves the EGRESS ROUTE is actually denied: attempt a TCP connect to a
# reachable PUBLIC host that is NOT a provider and REFUSE TO SERVE if it succeeds.
# With Smokescreen + docker egress denial in place (Phase-1 infra), that connect
# must fail; if it succeeds, the container still has a direct route to the
# internet and the whole control is silently absent (the C1 failure mode relocated
# to the network layer, DESIGN §8 pt2 / §9 pt1).
#
# Gated behind CHARON_EGRESS_SELFTEST because the egress-denial INFRA is deployed
# separately from this code: on a pre-infra install egress is still open, so an
# ungated self-test would refuse to serve the live gateway. The operator flips the
# flag ON once Smokescreen + docker denial land. Default OFF.
#
# PHASE-2 VARIANT — NOT BUILT HERE (deliberately). Once credential custody moves
# out of the process (nginx credproxy), the gateway must ALSO refuse to serve if a
# provider key is present in its own env / secrets.json. That belongs to the
# custody phase, not Phase-1, and is intentionally omitted; do not add it until
# custody has actually moved, or it will refuse to start every current install.

_DEFAULT_SELFTEST_HOST = "example.com"  # IANA-reserved, always up; never a provider.
_SELFTEST_ENV = "CHARON_EGRESS_SELFTEST"


def egress_selftest_enabled() -> bool:
    return os.environ.get(_SELFTEST_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def assert_egress_denied(host: str | None = None, *, port: int = 443, timeout: float = 3.0) -> None:
    """Raise EgressPolicyError if a TCP connect to a non-provider PUBLIC host
    SUCCEEDS — proving egress is NOT actually denied. A refused/failed connect is
    the desired outcome and returns cleanly. Never raises for the right reason
    (denied) — only for the wrong one (reachable)."""
    target = host or os.environ.get(_SELFTEST_ENV + "_HOST") or _DEFAULT_SELFTEST_HOST
    try:
        with socket.create_connection((target, port), timeout=timeout):
            pass
    except OSError:
        _log.info("egress self-test OK: %s:%s is unreachable (egress denied)", target, port)
        return
    raise EgressPolicyError(
        f"egress self-test FAILED: reached non-provider host {target}:{port}. The "
        f"container's egress is NOT denied — a provider key could leave to an "
        f"arbitrary host. Refusing to serve. (Deploy the Phase-1 egress denial, "
        f"or unset {_SELFTEST_ENV} on a pre-infra install.)"
    )


def run_startup_egress_selftest() -> None:
    """Run the egress self-test iff CHARON_EGRESS_SELFTEST is enabled. No-op
    otherwise so a pre-infra install is never bricked."""
    if egress_selftest_enabled():
        assert_egress_denied()


# ---------------------------------------------------------------------------
# 4. preset→ACL generator (generator, NOT enforcer).
# ---------------------------------------------------------------------------


def generate_smokescreen_acl(*, project: str = "charon", service: str = "charon-gateway") -> str:
    """Emit a Stripe Smokescreen egress-ACL YAML fragment allowlisting exactly the
    preset EXTERNAL hosts, in ``enforce`` mode with a global default-deny.

    GENERATOR, NOT ENFORCER: ``charon egress acl`` prints this fragment plus the
    reload command; the operator reviews and applies it out-of-band. The host list
    is sourced ONLY from the git-tracked presets (DESIGN §2.1). Validate against
    your Smokescreen version before applying — the schema below targets the v1 ACL
    format and is intended for operator review, not blind ``kubectl apply``."""
    hosts = sorted(preset_external_hosts())
    lines = [
        "# GENERATED by `charon egress acl` — review before applying.",
        "# Source: git-tracked src/charon/provider_presets/*.py (never providers.json).",
        f"# {len(hosts)} external provider host(s). Local providers reach the host direct.",
        "version: v1",
        "services:",
        f"  - name: {service}",
        f"    project: {project}",
        "    action: enforce",
        "    allowed_domains:",
    ]
    lines.extend(f"      - {h}" for h in hosts)
    # Unmatched roles (i.e. anything that is not the gateway service) are denied.
    lines += [
        "default:",
        "    name: default",
        f"    project: {project}",
        "    action: enforce",
        "    allowed_domains: []",
    ]
    return "\n".join(lines) + "\n"


def smokescreen_reload_hint(*, container: str = "smokescreen") -> str:
    """The command that reloads a running Smokescreen after the ACL changes.
    Smokescreen re-reads its ACL on SIGHUP. Printed for the operator; never run."""
    return (
        f"# reload Smokescreen (re-reads its ACL on SIGHUP):\n"
        f"docker kill -s HUP {container}   # or: kill -HUP <smokescreen-pid>"
    )


def nginx_credproxy_template_stub() -> str:
    """PHASE-2 STUB — NOT WIRED. Placeholder for the per-provider nginx credproxy
    template the custody phase will generate (prefix → real base + injected key via
    the official image's envsubst-on-templates). Intentionally inert: emitting a
    real credproxy config is the NEXT unit (Track C), not Phase-1."""
    return (
        "# TODO(phase-2, Track C custody): generate one nginx location per provider\n"
        "# mapping http://credproxy/<prefix>/ -> real base_url with an injected\n"
        "#   proxy_set_header Authorization \"Bearer ${<PROVIDER>_API_KEY}\";\n"
        "# so the gateway process holds NO provider key. Do not wire in Phase-1.\n"
    )
