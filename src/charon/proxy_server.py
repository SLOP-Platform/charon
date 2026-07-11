"""HTTP serving shell for the observing proxy (ADR-0004 R1).

Wraps ``GatewayProxy.observe`` in a tiny OpenAI-compatible reverse proxy that the
ACP agent points at (its provider ``baseURL`` → this server). For each call the
server forwards to the configured upstream — injecting the real provider key, so
credentials stay in Charon's control plane and never reach the agent — observes
the response (status / usage / returned model), and relays it back unchanged.

Stdlib only (``http.server`` + ``urllib``). This is the serving plumbing on top of
the unit-tested observation core; it is exercised both by an in-process
integration test (mock upstream) and live via a real OpenCode-Go call.
"""
from __future__ import annotations

import base64
import collections
import hashlib
import hmac
import http.cookies
import http.server
import json
import os
import socketserver
import threading
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit

from . import console_router, forwarder
from .balance import BalanceTracker
from .cache import SemanticCache
from .latency import RollingLatency
from .consensus import ConsensusRouter
from .guardrails import Guardrails
from .netutil import is_loopback
from .observability import Observability
from .policy_router import PolicyRouter
from .providers import WIRE_OPENAI
from .proxy import GatewayProxy

# Facade re-exports (decompose): keep the public import surface resolving
# unchanged from charon.proxy_server for the test suite and callers.
from .proxy_console_assets import (
    _CONSOLE_HTML,
    _LOGIN_HTML,
    _SETUP_HTML,
    _WORK_HTML,
)
from .proxy_response import _extract, _pre_flight_estimate
from .quality_scorer import QualityScorer
from .request_inspector import RequestInspector
from .response_normalizer import ResponseNormalizer
from .session_affinity import SessionAffinity
from .speculative_execution import SpeculativeExecutor
from .spend_limits import SpendLimiter
from .virtual_keys import VirtualKeyManager

# Public import surface re-exported from this facade (decompose). Declaring the
# re-exports in __all__ marks them as intentionally re-exported (clears F401) and
# keeps ``charon.proxy_server`` resolving these names for the test suite/callers.
__all__ = [
    "GatewayProxyServer",
    "UpstreamRoute",
    "_CONSOLE_HTML",
    "_LOGIN_HTML",
    "_SETUP_HTML",
    "_WORK_HTML",
    "_extract",
    "_pre_flight_estimate",
]


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


@dataclass(frozen=True)
class UpstreamRoute:
    """Where one agent-facing model id is forwarded (multi-provider pools)."""

    upstream_base: str
    api_key: str | None = None
    upstream_model: str | None = None  # rewrite the body's model to this id upstream
    pool_id: str | None = None  # observe under this id (the router's pool id) if set
    provider: str | None = None  # display label for failover visibility (X-Charon-Provider)
    strip_v1: bool | None = None  # per-provider quirk; None → use the server default
    wire: str = WIRE_OPENAI  # upstream wire format (SR-6): WIRE_OPENAI | WIRE_ANTHROPIC
    adapter: str | None = None  # response-shape adapter key (response_adapters.py);
    model_id: str | None = None  # registry model id (for live meter lookup in R2)
    #                             None → IDENTITY passthrough (byte-identical relay)
    # R7 capability-engine: per-route hard limits (None = unknown / no limit)
    max_context: int | None = None       # max tokens this route admits
    max_concurrency: int | None = None   # max in-flight requests to this route

    @property
    def label(self) -> str:
        """Human-facing provider id for failover headers/logs — never a secret. Uses
        host[:port] (NOT netloc) so any ``user:pass@`` userinfo in a misconfigured
        base never surfaces in a header/console (P4 review)."""
        if self.provider:
            return self.provider
        parts = urlsplit(self.upstream_base)
        host = parts.hostname or self.upstream_base
        return f"{host}:{parts.port}" if parts.port else host

class _ProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"  # close-delimited; works for SSE without length

    def log_message(self, *args) -> None:  # keep the coordinator's stdout clean
        pass

    def do_POST(self) -> None:
        self._handle()

    def do_GET(self) -> None:
        self._handle()

    def _json(self, status: int, obj: dict) -> None:
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self._maybe_set_token_cookie()
        self._maybe_set_session_cookie()
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _html(self, html: str, status: int = 200) -> None:
        data = html.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._maybe_set_token_cookie()
        self._maybe_set_session_cookie()
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _authorized(self, token: str) -> bool:
        """Bearer token via ``Authorization`` header, ``?token=`` query, or
        ``charon_token`` cookie; constant-time compare to avoid leaking via timing."""
        presented = ""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            presented = auth[len("Bearer "):].strip()
        if not presented:
            qs = parse_qs(urlsplit(self.path).query)
            presented = (qs.get("token") or [""])[0]
        if not presented:
            cookie_header = self.headers.get("Cookie", "")
            cookies = http.cookies.SimpleCookie()
            cookies.load(cookie_header)
            cookie_token = cookies.get("charon_token")
            if cookie_token:
                presented = cookie_token.value
        return bool(presented) and hmac.compare_digest(presented, token)

    def _maybe_set_token_cookie(self) -> None:
        """Legacy raw-token cookie hook. Superseded by the signed ``charon_sess``
        session (SR-13) — nothing assigns ``_set_token_cookie`` anymore, so this is
        inert; kept so the emit helpers keep a single call site during the one-
        release window in which ``_authorized`` still accepts an old ``charon_token``."""
        v = getattr(self, '_set_token_cookie', None)
        if v:
            self.send_header("Set-Cookie",
                f"charon_token={v}; Path=/; HttpOnly; SameSite=Lax; Max-Age=900")

    # ---- /charon session cookie (SR-13) ---------------------------------

    def _maybe_set_session_cookie(self) -> None:
        """Emit a pending ``charon_sess`` Set-Cookie (issue or clear) queued by the
        dispatch / login / logout paths."""
        v = getattr(self, "_session_cookie_header", None)
        if v:
            self.send_header("Set-Cookie", v)

    def _issue_session(self, srv: GatewayProxyServer) -> None:
        """Queue a fresh signed ``charon_sess`` cookie (30-day sliding lifetime).
        HttpOnly + SameSite=Lax; no ``Secure`` (plain http on the LAN would drop it —
        documented tradeoff)."""
        exp = int(time.time()) + _SESSION_TTL
        val = _sign_session(srv.session_key(), exp)
        self._session_cookie_header = (
            f"{_SESSION_COOKIE}={val}; Path=/; HttpOnly; SameSite=Lax; "
            f"Max-Age={_SESSION_TTL}")

    def _clear_session(self) -> None:
        """Queue a ``charon_sess`` deletion (logout)."""
        self._session_cookie_header = (
            f"{_SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0")

    def _session_exp(self, srv: GatewayProxyServer) -> int | None:
        """The ``exp`` of a valid ``charon_sess`` cookie on this request, else None.
        Authorizes ``/charon/*`` ONLY — callers must never accept it for ``/v1/*``."""
        jar = http.cookies.SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie", ""))
        except http.cookies.CookieError:
            return None
        c = jar.get(_SESSION_COOKIE)
        if not c:
            return None
        return _verify_session(srv.session_key(), c.value)

    def _valid_session(self, srv: GatewayProxyServer) -> bool:
        return self._session_exp(srv) is not None

    def _redirect(self, location: str, status: int = 302) -> None:
        """A tiny 302 that still emits any pending session cookie (login/logout/TOFU)."""
        self.send_response(status)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self._maybe_set_token_cookie()
        self._maybe_set_session_cookie()
        self.end_headers()

    # ---- helpers ---------------------------------------------------------

    def _write(self, data: bytes) -> bool:
        """Write to the client; False if the client hung up (so we stop)."""
        try:
            self.wfile.write(data)
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False

    def _drain(self, resp) -> bytes:
        out: list[bytes] = []
        try:
            while True:
                c = resp.read(8192)
                if not c:
                    break
                out.append(c)
        except Exception:  # noqa: BLE001
            pass
        return b"".join(out)

    def _send_resp_headers(self, status: int, ctype: str, provider: str | None,
                           failovers: list[dict], downgrade: bool,
                           cache_status: str | None = None,
                           retry_after: int | None = None) -> None:
        """Send status + Content-Type + the failover-visibility headers (ADR D3).

        ``retry_after`` (P1): when truthy and > 0, emit a bounded ``Retry-After``
        so the GATEWAY owns retry cadence on a transient exhaustion (a dual-402
        can never become a client's runaway ~8h exponential backoff). Callers that
        omit it keep byte-identical headers to before."""
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        if provider:
            self.send_header("X-Charon-Provider", provider)
        self.send_header("X-Charon-Failovers", str(len(failovers)))
        if failovers:
            self.send_header("X-Charon-Failover-Reasons",
                             "; ".join(f"{f['provider']}={f['status']}" for f in failovers))
        if downgrade:
            self.send_header("X-Charon-Downgrade", "served a different model than requested")
        if cache_status:  # real header — must precede end_headers (never in the body)
            self.send_header("X-Cache-Status", cache_status)
        if retry_after and retry_after > 0:  # P1: bounded gateway-owned retry cadence
            self.send_header("Retry-After", str(int(retry_after)))
        self._maybe_set_token_cookie()
        self._maybe_set_session_cookie()
        self.end_headers()

    def _handle(self) -> None:
        srv: GatewayProxyServer = self.server  # type: ignore[assignment]

        # Anti-DNS-rebinding (security review HIGH): on a loopback bind, reject a Host
        # header that isn't a loopback literal — defeats the rebinding that would
        # otherwise let a web page drive the ungated-default gateway and exfiltrate keys.
        if srv.require_loopback_host:
            hosthdr = self.headers.get("Host", "")
            if hosthdr and not is_loopback(urlsplit("//" + hosthdr).hostname or ""):
                self._json(403, {"error": {"message": "host not allowed"}})
                return

        # Surface-aware auth (SR-13). ``/charon/*`` is the browser console; ``/v1/*``
        # is the machine API. The gateway token authorizes BOTH exactly as before; a
        # signed ``charon_sess`` cookie authorizes ``/charon/*`` ONLY — ``/v1/*`` stays
        # byte-for-byte token-only, so opencode / ACP / LAN clients never see a change.
        path_only = urlsplit(self.path).path.rstrip("/")
        # SR-13 F1(a): the session-authorizable surface is the ENUMERATED console
        # routes ONLY — never a bare ``/charon/*`` prefix. An unknown ``/charon/xyz``
        # is not ``is_gui``, so a session cookie can't authorize it and it can never
        # reach the forwarder; it 404s below instead.
        is_gui = path_only in _GUI_ROUTES

        # Public /charon routes (login page + login POST + logout) must be reachable
        # WITHOUT credentials — they run before the gate and self-serve.
        if console_router.try_handle_public_gui(self, srv):
            return

        authed_by_token = srv.token is None or self._authorized(srv.token)
        authed_by_session = (
            not authed_by_token and is_gui and self._valid_session(srv))
        if not (authed_by_token or authed_by_session):
            if is_gui and self.command == "GET":
                # A browser hitting the console gets a login page, not raw 401 JSON.
                self._redirect("/charon/login")
            else:
                self._json(401,
                           {"error": {"message": "missing or invalid bearer token"}})
            return

        # TOFU upgrade: a browser that arrived on a /charon page via ?token= is handed
        # a durable session cookie and 302'd to the same page WITHOUT the token — one
        # hop strips the secret from the address bar/history (replaces the old raw-
        # token cookie). Machine ``/v1/*`` clients (Bearer header, no ?token=) are
        # untouched.
        if is_gui and self.command == "GET" and srv.token is not None:
            qs = parse_qs(urlsplit(self.path).query)
            if qs.get("token", [""])[0]:
                self._issue_session(srv)
                self._redirect(_strip_token_from_path(self.path))
                return

        # Sliding refresh: re-issue the session on each authorized console request so
        # an active operator's cookie keeps extending toward a fresh 30-day horizon.
        if authed_by_session:
            self._issue_session(srv)

        # Control-plane dispatch (console/setup/discovery); True = fully served.
        if console_router.try_handle_control_plane(self, srv):
            return

        # SR-13 F1(a): an un-enumerated ``/charon/*`` path that fell through both
        # routers is NOT a data-plane target — 404 rather than forward it to the
        # billed provider call (which routes on the body ``model``, ignoring the URL).
        if path_only in ("", "/charon") or path_only.startswith("/charon/"):
            self._json(404, {"error": {"message": "not found"}})
            return

        # SR-13 F1(b), belt-and-suspenders: the data plane is Bearer-token ONLY. A
        # request authorized solely by a ``charon_sess`` session cookie must never
        # reach the forwarder, regardless of path — a stolen console cookie is not a
        # spend credential.
        if not authed_by_token:
            self._json(401,
                       {"error": {"message": "missing or invalid bearer token"}})
            return

        forwarder.forward_with_failover(self, srv)


class GatewayProxyServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """A loopback OpenAI-compatible proxy in front of one or many upstreams.

    Single-upstream: pass ``upstream_base`` + ``api_key``. Multi-provider pools
    (failover across providers): pass ``routes`` mapping the agent-facing model id
    to its ``UpstreamRoute`` (base, key, optional upstream model-id rewrite); the
    single upstream, if also given, is the fallback."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        upstream_base: str | None = None,
        api_key: str | None = None,
        observer: GatewayProxy | None = None,
        routes: dict[str, UpstreamRoute] | None = None,
        host: str = "127.0.0.1",
        port: int = 0,
        fwd_timeout: float = 180.0,
        strip_v1: bool = True,
        token: str | None = None,
        session_key: str | None = None,
        model_ids: list[str] | None = None,
        pools: dict[str, list[UpstreamRoute]] | None = None,
        model_meta: dict[str, dict] | None = None,
        model_pricing: dict[str, dict] | None = None,
        max_body_bytes: int = 10 * 1024 * 1024,
        default_cooldown: float = 60.0,
        max_cooldown_s: float = 120.0,
        failover_log_path: str | None = None,
        failover_on_downgrade: bool = False,
        anthropic_prompt_cache: bool = True,
        guardrails: Guardrails | None = None,
        semantic_cache: SemanticCache | None = None,
        response_normalizer: ResponseNormalizer | None = None,
        observability: Observability | None = None,
        quality_scorer: QualityScorer | None = None,
        spend_limiter: SpendLimiter | None = None,
        request_inspector: RequestInspector | None = None,
        session_affinity: SessionAffinity | None = None,
        speculative_executor: SpeculativeExecutor | None = None,
        consensus_router: ConsensusRouter | None = None,
        virtual_key_manager: VirtualKeyManager | None = None,
        policy_router: PolicyRouter | None = None,
        balance_tracker: BalanceTracker | None = None,
        latency_tracker: RollingLatency | None = None,
        slow_provider_threshold_ms: float | None = None,
    ) -> None:
        super().__init__((host, port), _ProxyHandler)
        self.upstream_base = upstream_base
        self.api_key = api_key
        self.routes = routes or {}
        self.observer = observer or GatewayProxy(model_pricing=model_pricing)
        self.fwd_timeout = fwd_timeout
        self.strip_v1 = strip_v1
        # Anti-DNS-rebinding: when bound to loopback, only accept requests whose Host
        # header is a loopback literal — a rebound attacker domain (Host: evil.com) is
        # rejected, so a malicious web page can't drive the ungated-loopback gateway
        # (security review HIGH). A non-loopback (tokened) bind relies on the token.
        self.require_loopback_host = is_loopback(host)
        # Gateway mode (ADR-0005 P1): a bearer token (None = open) and the
        # agent-facing model ids to serve at /v1/models (None = don't intercept).
        self.token = token
        # HMAC key that signs /charon session cookies (SR-13). Separate from the
        # gateway token — rotating the token does NOT invalidate console sessions.
        # None → resolved lazily on first use (env → secrets.json → generate+persist),
        # so construction never touches the filesystem (tests pass an explicit key).
        self._session_key = session_key
        self.model_ids = model_ids
        # Per-model metadata surfaced in /v1/models (context_window, max_tokens,
        # reasoning, vision, audio) — optional, never carries secrets.
        self.model_meta = model_meta or {}
        # Per-model pricing (cost_input, cost_output) for computing cost_usd when
        # the provider doesn't self-report — optional (SR-5b).
        self.model_pricing = model_pricing or {}
        # P2 failover: model id → ordered (cost-ranked) candidate chain; a
        # provider-keyed cooldown with Retry-After expiry (R7/R10c); and a bounded
        # in-memory failover event log (+ optional JSONL file) for visibility (D3).
        self.pools = pools or {}
        self.max_body_bytes = max_body_bytes
        self.default_cooldown = default_cooldown
        # Ceiling on any single cooldown, including a provider-reported Retry-After
        # (cooldown-anchor-demotion red): an upstream that returns an extreme backoff
        # (observed ~3420s / 57min) must never sideline a provider — anchor or not —
        # for tens of minutes. set_cooldown() clamps to this; the default-60s no-
        # Retry-After path is unaffected (60 < 120).
        self.max_cooldown_s = max_cooldown_s
        self.failover_log_path = failover_log_path
        # R7 capability-engine: per-provider in-flight request counter
        self._inflight: dict[str, int] = {}
        # Operator toggle (SR-2): on a GENUINE silent downgrade, fail over to the next
        # provider to try for the asked model instead of serving the downgrade. The
        # discarded attempt is recorded with count_usage=True (visible, not the old
        # silent double-bill). Default False → serve the downgrade once, billed once.
        self.failover_on_downgrade = failover_on_downgrade
        # Operator toggle (SR-6, default ON): for a route whose upstream speaks the
        # Anthropic wire format, inject one prompt-cache breakpoint into the outbound
        # body so a long stable tools+system prefix is billed at the cache-read (not
        # full-input) price. OFF → the body is forwarded byte-identical. OpenAI-wire
        # routes are NEVER touched regardless of this flag.
        self.anthropic_prompt_cache = anthropic_prompt_cache
        self.guardrails = guardrails
        self.semantic_cache = semantic_cache
        self.response_normalizer = response_normalizer
        self.observability = observability
        self.quality_scorer = quality_scorer
        self.spend_limiter = spend_limiter
        self.request_inspector = request_inspector
        self.session_affinity = session_affinity
        self.speculative_executor = speculative_executor
        self.consensus_router = consensus_router
        self.virtual_key_manager = virtual_key_manager
        self.policy_router = policy_router
        self.balance_tracker = balance_tracker
        self.latency_tracker = latency_tracker or RollingLatency()
        self.slow_provider_threshold_ms = slow_provider_threshold_ms
        self._cooldown: dict[str, float] = {}
        self._cooldown_lock = threading.Lock()
        self.failover_events: collections.deque[dict] = collections.deque(maxlen=200)
        # per-provider counters for the console (P4): label → served/failed/cost.
        self.provider_stats: dict[str, dict] = {}
        # Optional web-setup write handler (Setup phase): callable(action, payload) ->
        # (status, dict). None (default) keeps the console READ-ONLY. The gateway wires
        # this only for the user-config-dir flow; it writes config + reloads routes.
        self.setup_handler = None

    def session_key(self) -> str:
        """The HMAC key that signs ``/charon`` session cookies (SR-13). Resolved
        lazily and cached: an explicit key (tests) wins, else
        ``CHARON_SESSION_KEY`` env, else the stored value, else a generated key
        persisted 0600. Never logged; never forwarded upstream."""
        if self._session_key is None:
            self._session_key = _resolve_session_key()
        return self._session_key

    def route_for(self, model: str) -> UpstreamRoute | None:
        """Which upstream serves ``model``: an explicit route, else the single
        upstream fallback, else None (no route → 502)."""
        if model in self.routes:
            return self.routes[model]
        if self.upstream_base:
            return UpstreamRoute(self.upstream_base, self.api_key)
        return None

    def apply_routes(self, routes: dict, pools: dict, model_ids: list[str],
                     model_meta: dict[str, dict] | None = None,
                     model_pricing: dict[str, dict] | None = None) -> None:
        """Atomically swap the live routing config (web-setup hot-reload) under the
        same lock ``chain_for`` reads — so an in-flight request never sees a torn
        (mixed old/new) routes-vs-pools view (security review LOW). Also refreshes
        the observer's pricing so a live config reload updates cost_usd too (SR-5b)."""
        with self._cooldown_lock:
            self.routes = routes
            self.pools = pools
            self.model_ids = model_ids
            self.model_meta = model_meta or {}
            self.model_pricing = model_pricing or {}
            self.observer.set_pricing(self.model_pricing)

    def chain_for(self, model: str) -> list[UpstreamRoute]:
        """The ordered failover chain for ``model``: a configured pool (multiple
        cost-ranked providers), else a single route/upstream (a chain of one), else
        ``[]`` (no route → 502). A 1-element chain never fails over — exactly the
        pre-P2 single-upstream behavior."""
        with self._cooldown_lock:  # paired with apply_routes → consistent snapshot
            if model in self.pools:
                return list(self.pools[model])
            if (self.policy_router is not None and model.startswith("policy/")):
                policy_name = model[len("policy/"):]
                return self.policy_router.resolve(policy_name, self.routes,
                                                  self.pools)
            single = self.route_for(model)
            return [single] if single is not None else []

    def order_by_cooldown(self, chain: list[UpstreamRoute]) -> list[UpstreamRoute]:
        """Try providers NOT in active cooldown first; keep cooled ones as a
        last resort so a stale cooldown never permanently blocks a request (R7).
        Within the cooled bucket, order by soonest-to-recover first (ascending
        remaining cooldown) — cooldown-anchor-demotion red: among several cooled
        providers, prefer the one closest to coming back rather than an arbitrary
        (insertion) order.

        R8 latency-signal tiebreak: among providers with the same cooldown status
        (both fresh or both cooled with identical remaining cooldown), prefer the
        one with lower measured EWMA latency. None-safe: if no latency data exists
        for a provider, it sorts as if its latency were ``+inf`` (i.e. deprioritised
        but never removed)."""
        now = time.monotonic()
        with self._cooldown_lock:
            fresh = [r for r in chain if self._cooldown.get(r.upstream_base, 0.0) <= now]
            cooled = [r for r in chain if self._cooldown.get(r.upstream_base, 0.0) > now]

        def _lat_sort_key(route: UpstreamRoute) -> float:
            # Lower latency first; missing data → +inf so known-good routes win.
            lat = self.latency_tracker.latency_ms(route.label)
            return float(lat) if lat is not None else float("inf")

        fresh.sort(key=_lat_sort_key)
        # R8 fix: stable composite-key sort — cooldown is PRIMARY, latency tiebreaks.
        cooled.sort(key=lambda r: (self._cooldown.get(r.upstream_base, 0.0), _lat_sort_key(r)))
        return fresh + cooled

    def is_slow_provider(self, route: UpstreamRoute) -> bool:
        """True when the provider's measured EWMA latency exceeds the configured
        ``slow_provider_threshold_ms``.  None-safe: False when no data or no
        threshold is configured."""
        return self.latency_tracker.is_slow(
            route.label, self.slow_provider_threshold_ms)

    def retry_after_hint(self, chain: list[UpstreamRoute]) -> int:
        """Seconds until the soonest member of ``chain`` recovers — a bounded
        ``Retry-After`` for the terminal 503 (P1). Reads the same ``_cooldown``
        map as ``order_by_cooldown`` (under the same lock): the soonest remaining
        cooldown among cooled members, falling back to ``default_cooldown`` when
        none is cooled, clamped to ``[1, max_cooldown_s]``. No routing/spend
        effect — purely a header hint."""
        now = time.monotonic()
        with self._cooldown_lock:
            remaining = [self._cooldown[r.upstream_base] - now
                         for r in chain
                         if self._cooldown.get(r.upstream_base, 0.0) > now]
        soonest = min(remaining) if remaining else self.default_cooldown
        return int(max(1.0, min(soonest, self.max_cooldown_s)))

    def inflight_inc(self, route: UpstreamRoute) -> None:
        """Increment the in-flight counter for *route.label* (R7)."""
        with self._cooldown_lock:
            self._inflight[route.label] = self._inflight.get(route.label, 0) + 1

    def inflight_dec(self, route: UpstreamRoute) -> None:
        """Decrement the in-flight counter for *route.label* (R7), clamped at 0."""
        with self._cooldown_lock:
            self._inflight[route.label] = max(self._inflight.get(route.label, 0) - 1, 0)

    def inflight_count(self, route: UpstreamRoute) -> int:
        """Current in-flight count for *route.label* (R7)."""
        with self._cooldown_lock:
            return self._inflight.get(route.label, 0)

    def set_cooldown(self, route: UpstreamRoute, retry_after: int | None) -> None:
        """Mark a provider out-of-capacity until ``Retry-After`` (or a default),
        keyed by provider (upstream_base) — a 429 is account-level, so all of that
        provider's models are skipped, not just the one (R10c). The Retry-After-
        derived duration is clamped to ``max_cooldown_s`` (cooldown-anchor-demotion
        red): upstreams occasionally report extreme backoffs (observed ~3420s /
        57min) that would otherwise sideline a provider — anchor or not — for far
        longer than a transient rate limit warrants."""
        secs = float(retry_after) if (retry_after and retry_after > 0) else self.default_cooldown
        secs = min(secs, self.max_cooldown_s)
        with self._cooldown_lock:
            self._cooldown[route.upstream_base] = time.monotonic() + secs

    def note_request(self, model: str, served_by: str, status, cost: float,
                     failovers: list[dict]) -> None:
        """Account one finished request (called on EVERY exit path): bump the served
        provider's served/cost counters and each failed-over provider's failure
        counter (per-provider visibility, D3/P4), and — when failover happened —
        append a failover event (ring buffer + optional JSONL)."""
        def _slot(stats, label):
            return stats.setdefault(label, {"served": 0, "failed": 0, "errors": 0,
                                            "cost": 0.0, "last_status": None})
        with self._cooldown_lock:
            s = _slot(self.provider_stats, served_by)
            if status == 200:
                s["served"] += 1   # a real success
                s["cost"] += cost
            else:
                s["errors"] += 1   # terminal failure/relayed error — NOT a success (P4 review)
            s["last_status"] = status
            for f in failovers:
                fs = _slot(self.provider_stats, f["provider"])
                fs["failed"] += 1
                fs["last_status"] = f["status"]
            if failovers:
                self.failover_events.append(
                    {"model": model, "served_by": served_by, "status": status,
                     "failovers": list(failovers)})
        if failovers and self.failover_log_path:
            try:
                with open(self.failover_log_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(
                        {"model": model, "served_by": served_by, "failovers": failovers}) + "\n")
            except OSError:
                pass

    def status_snapshot(self) -> dict:
        """A JSON-able view for the console (P4): pool config, per-provider stats +
        cooldown, cumulative usage, and the recent failover events."""
        now = time.monotonic()
        with self._cooldown_lock:
            cooled = {base: round(t - now, 1) for base, t in self._cooldown.items() if t > now}
            stats = {k: dict(v) for k, v in self.provider_stats.items()}
            events = list(self.failover_events)
        pools = {vid: [r.label for r in chain] for vid, chain in self.pools.items()}
        for mid, r in self.routes.items():
            pools.setdefault(mid, [r.label])
        # map a provider label → seconds of cooldown remaining (via its base url)
        label_cooldown: dict[str, float] = {}
        for chain in list(self.pools.values()) + [[r] for r in self.routes.values()]:
            for r in chain:
                if r.upstream_base in cooled:
                    label_cooldown[r.label] = cooled[r.upstream_base]
        u = self.observer.cumulative_usage()
        return {
            "pools": pools,
            "providers": stats,
            "cooldown_seconds": label_cooldown,
            "usage": {"tokens_in": u.tokens_in, "tokens_out": u.tokens_out,
                      "cost_usd": round(u.cost_usd, 6)},
            "recent_failovers": events[-50:],
            # Running build/version (baked into the image by SR-10); None outside a build.
            "build_sha": os.environ.get("CHARON_BUILD_SHA"),
        }

    @property
    def url(self) -> str:
        host, port = self.server_address[0], self.server_address[1]
        if isinstance(host, bytes):
            host = host.decode()
        return f"http://{host}:{port}"

    def serve_in_thread(self) -> threading.Thread:
        t = threading.Thread(target=self.serve_forever, daemon=True)
        t.start()
        return t
