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

import collections
import hmac
import http.cookies
import http.server
import json
import os
import socketserver
import threading
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from . import console_router, forwarder
from .cache import SemanticCache
from .consensus import ConsensusRouter
from .guardrails import Guardrails
from .netutil import is_loopback
from .observability import Observability
from .policy_router import PolicyRouter
from .proxy import GatewayProxy

# Facade re-exports (decompose): keep the public import surface resolving
# unchanged from charon.proxy_server for the test suite and callers.
from .proxy_console_assets import _CONSOLE_HTML, _SETUP_HTML, _WORK_HTML
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
    "_SETUP_HTML",
    "_WORK_HTML",
    "_extract",
    "_pre_flight_estimate",
]


@dataclass(frozen=True)
class UpstreamRoute:
    """Where one agent-facing model id is forwarded (multi-provider pools)."""

    upstream_base: str
    api_key: str | None = None
    upstream_model: str | None = None  # rewrite the body's model to this id upstream
    pool_id: str | None = None  # observe under this id (the router's pool id) if set
    provider: str | None = None  # display label for failover visibility (X-Charon-Provider)
    strip_v1: bool | None = None  # per-provider quirk; None → use the server default

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
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _html(self, html: str) -> None:
        data = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._maybe_set_token_cookie()
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
        """If this request authenticated via ``?token=``, set a short-lived cookie
        so subsequent page loads don't need the token in the URL."""
        v = getattr(self, '_set_token_cookie', None)
        if v:
            self.send_header("Set-Cookie",
                f"charon_token={v}; Path=/; HttpOnly; SameSite=Lax; Max-Age=900")

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

        # Token gate (gateway mode). Default ``token=None`` keeps the bare proxy
        # open — exactly its prior behavior; a set token requires it on every call.
        if srv.token is not None and not self._authorized(srv.token):
            self._json(401, {"error": {"message": "missing or invalid bearer token"}})
            return

        # If auth was via ?token= query param, set a short-lived cookie so
        # subsequent page loads don't need the token in the URL.
        if srv.token is not None:
            qs = parse_qs(urlsplit(self.path).query)
            qt = qs.get("token")
            if qt and qt[0]:
                self._set_token_cookie = srv.token

        # Control-plane dispatch (console/setup/discovery); True = fully served.
        if console_router.try_handle_control_plane(self, srv):
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
        model_ids: list[str] | None = None,
        pools: dict[str, list[UpstreamRoute]] | None = None,
        model_meta: dict[str, dict] | None = None,
        model_pricing: dict[str, dict] | None = None,
        max_body_bytes: int = 10 * 1024 * 1024,
        default_cooldown: float = 60.0,
        max_cooldown_s: float = 120.0,
        failover_log_path: str | None = None,
        failover_on_downgrade: bool = False,
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
        # Operator toggle (SR-2): on a GENUINE silent downgrade, fail over to the next
        # provider to try for the asked model instead of serving the downgrade. The
        # discarded attempt is recorded with count_usage=True (visible, not the old
        # silent double-bill). Default False → serve the downgrade once, billed once.
        self.failover_on_downgrade = failover_on_downgrade
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
        self._cooldown: dict[str, float] = {}
        self._cooldown_lock = threading.Lock()
        self.failover_events: collections.deque[dict] = collections.deque(maxlen=200)
        # per-provider counters for the console (P4): label → served/failed/cost.
        self.provider_stats: dict[str, dict] = {}
        # Optional web-setup write handler (Setup phase): callable(action, payload) ->
        # (status, dict). None (default) keeps the console READ-ONLY. The gateway wires
        # this only for the user-config-dir flow; it writes config + reloads routes.
        self.setup_handler = None

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
        (insertion) order."""
        now = time.monotonic()
        with self._cooldown_lock:
            fresh = [r for r in chain if self._cooldown.get(r.upstream_base, 0.0) <= now]
            cooled = [r for r in chain if self._cooldown.get(r.upstream_base, 0.0) > now]
            cooled.sort(key=lambda r: self._cooldown.get(r.upstream_base, 0.0))
        return fresh + cooled

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
