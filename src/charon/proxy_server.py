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
import http.server
import json
import socketserver
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from .proxy import GatewayProxy


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
        """Human-facing provider id for failover headers/logs — never a secret."""
        return self.provider or urlsplit(self.upstream_base).netloc or self.upstream_base

_SKIP_HEADERS = {"host", "authorization", "content-length", "connection",
                 "accept-encoding", "proxy-authorization"}
_DEFAULT_UA = "charon-proxy/0.1"
# Library-default UAs upstream bot-protection bans (Cloudflare 1010); normalize
# these to the proxy's own identity so an internal urllib caller isn't blocked.
_BANNED_UA_PREFIXES = ("python-urllib", "python-requests")
# Cap the streamed bytes buffered while looking for the response `model` id (the
# silent-downgrade check before committing a stream); bounds memory on a stream
# that never carries a model field.
_STREAM_HEAD_CAP = 65536


def _extract(raw: bytes, content_type: str) -> dict:
    """Pull a ``{model, usage}`` view out of an upstream response — JSON for a
    normal completion, or the SSE ``data:`` chunks for a streamed one (agents like
    OpenCode stream). Returns {} if nothing parseable."""
    text = raw.decode("utf-8", "replace")
    if "text/event-stream" in content_type or text.lstrip().startswith("data:"):
        model = ""
        usage = None
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload in ("", "[DONE]"):
                continue
            try:
                obj = json.loads(payload)
            except Exception:
                continue
            model = model or obj.get("model", "")
            if obj.get("usage"):
                usage = obj["usage"]  # final SSE chunk carries usage (include_usage)
        out: dict = {}
        if model:
            out["model"] = model
        if usage:
            out["usage"] = usage
        return out
    try:
        return json.loads(text)
    except Exception:
        return {}


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
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _authorized(self, token: str) -> bool:
        """Bearer token via ``Authorization`` header or ``?token=`` query (so a
        browser URL works); constant-time compare to avoid leaking via timing."""
        presented = ""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            presented = auth[len("Bearer "):].strip()
        if not presented:
            qs = parse_qs(urlsplit(self.path).query)
            presented = (qs.get("token") or [""])[0]
        return bool(presented) and hmac.compare_digest(presented, token)

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
        except Exception:
            pass
        return b"".join(out)

    def _send_resp_headers(self, status: int, ctype: str, provider: str | None,
                           failovers: list[dict], downgrade: bool) -> None:
        """Send status + Content-Type + the failover-visibility headers (ADR D3)."""
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
        self.end_headers()

    def _build_upstream_req(self, srv, route: UpstreamRoute, orig_bj: dict,
                            raw_body: bytes) -> urllib.request.Request:
        """Build the upstream request for ONE attempt from the ORIGINAL request —
        each provider gets its own ``upstream_model`` (ADR R10b), and the client
        query string is dropped so our ``?token=`` bearer never leaks upstream
        (security review HIGH)."""
        bj = dict(orig_bj)
        if bj:
            if route.upstream_model:
                bj["model"] = route.upstream_model
            if bj.get("stream") is True:
                opts = dict(bj.get("stream_options") or {})
                opts["include_usage"] = True
                bj["stream_options"] = opts
            data: bytes | None = json.dumps(bj).encode()
        else:
            data = raw_body or None

        path = urlsplit(self.path).path  # PATH ONLY — never forward the query string
        strip_v1 = route.strip_v1 if route.strip_v1 is not None else srv.strip_v1
        if strip_v1 and path.startswith("/v1"):
            path = path[len("/v1"):]  # upstream_base already ends in /v1
        url = route.upstream_base.rstrip("/") + path

        req = urllib.request.Request(url, data=data, method=self.command)
        for hk in self.headers.keys():
            # User-Agent is normalized separately (below) — never forwarded raw.
            if hk.lower() not in _SKIP_HEADERS and hk.lower() != "user-agent":
                req.add_header(hk, self.headers[hk])
        req.add_header("Content-Type", "application/json")
        # Egress identity: forward the agent's real UA (some gateways 403 an unknown
        # one), but replace an absent/library-default UA — "Python-urllib/3.x" trips
        # Cloudflare 1010 (→403). Live-verified.
        client_ua = self.headers.get("User-Agent", "")
        if client_ua and not client_ua.lower().startswith(_BANNED_UA_PREFIXES):
            req.add_header("User-Agent", client_ua)
        else:
            req.add_header("User-Agent", _DEFAULT_UA)
        if route.api_key:
            req.add_header("Authorization", f"Bearer {route.api_key}")
        return req

    def _handle(self) -> None:
        srv: GatewayProxyServer = self.server  # type: ignore[assignment]

        # Token gate (gateway mode). Default ``token=None`` keeps the bare proxy
        # open — exactly its prior behavior; a set token requires it on every call.
        if srv.token is not None and not self._authorized(srv.token):
            self._json(401, {"error": {"message": "missing or invalid bearer token"}})
            return

        # Aggregated model list (gateway mode). Served locally — never forwarded —
        # and field-allowlisted to ids only (no key_env/upstream_base leak, ADR R4).
        path_only = urlsplit(self.path).path.rstrip("/")
        if (self.command == "GET" and srv.model_ids is not None
                and path_only in ("/v1/models", "/models")):
            self._json(200, {"object": "list", "data": [
                {"id": m, "object": "model", "owned_by": "charon"} for m in srv.model_ids]})
            return

        # Read the client request (size-capped — memory-DoS guard on an exposed bind).
        length = int(self.headers.get("Content-Length") or 0)
        if length > srv.max_body_bytes:
            self._json(413, {"error": {"message": "request body too large"}})
            return
        raw_body = self.rfile.read(length) if length else b""

        orig_bj: dict = {}
        requested = ""
        try:
            orig_bj = json.loads(raw_body) if raw_body else {}
            requested = orig_bj.get("model", "")
        except Exception:
            pass

        chain = srv.chain_for(requested)
        if not chain:
            srv.observer.observe(requested, 502, {}, {}, count_usage=False)
            self._json(502, {"error": {"message": f"no route for model {requested!r}"}})
            return

        is_stream = orig_bj.get("stream") is True
        ordered = srv.order_by_cooldown(chain)  # fresh providers first, cooled last (R7)
        failovers: list[dict] = []

        for i, route in enumerate(ordered):
            more = i < len(ordered) - 1
            okey = route.pool_id or requested  # exclusion/observe key (orchestrator compat)
            expected = route.upstream_model or requested or None
            req = self._build_upstream_req(srv, route, orig_bj, raw_body)

            try:
                resp = urllib.request.urlopen(req, timeout=srv.fwd_timeout)
                status, rhdrs = resp.status, dict(resp.headers)
            except urllib.error.HTTPError as exc:
                resp, status, rhdrs = exc, exc.code, dict(exc.headers)
            except Exception:  # provider unreachable → fail over (don't 502 outright)
                srv.observer.record(srv.observer.classify(okey, 503, {}, {},
                                    expected_model=expected), count_usage=False)
                srv.set_cooldown(route, None)
                if more:  # count only providers we actually move PAST
                    failovers.append({"provider": route.label, "status": "unreachable",
                                      "reason": "connection error"})
                    continue
                self._send_resp_headers(502, "application/json", route.label, failovers, False)
                self._write(json.dumps(
                    {"error": {"message": "all upstreams unreachable"}}).encode())
                srv.note_request(requested, route.label, failovers)
                return

            ctype = rhdrs.get("Content-Type", "application/json")
            try:
                # ---- non-200 ----
                if status != 200:
                    body_bytes = self._drain(resp)
                    obs = srv.observer.classify(okey, status, rhdrs, {}, expected_model=expected)
                    srv.observer.record(obs, count_usage=False)
                    if obs.failover:  # 429/402/503/404 = capacity/gone → fail over (R6)
                        if obs.exhausted:  # 429/402/503 are account-level → cool the
                            srv.set_cooldown(route, obs.retry_after)  # provider (R10c);
                        # a 404 ("model gone") is model-level — do NOT cool the provider.
                        if more:  # count only providers we actually move PAST
                            failovers.append({"provider": route.label, "status": status,
                                              "reason": obs.note or "exhausted"})
                            continue
                    # terminal capacity error, OR a 400/401/403 client/auth error we must
                    # NOT fail over (R6) — relay the real upstream response as-is.
                    self._send_resp_headers(status, ctype, route.label, failovers, False)
                    self._write(body_bytes)
                    srv.note_request(requested, route.label, failovers)
                    return

                # ---- 200, non-streaming: buffer, then check for a silent downgrade ----
                if not is_stream:
                    body_bytes = self._drain(resp)
                    observed = _extract(body_bytes, ctype)
                    obs = srv.observer.classify(okey, 200, rhdrs, observed, expected_model=expected)
                    if obs.pseudo_success and more:  # downgrade + alternatives → fail over
                        srv.observer.record(obs, count_usage=False)
                        failovers.append({"provider": route.label, "status": 200,
                                          "reason": obs.note})
                        continue
                    srv.observer.record(obs, count_usage=True)  # served → bill usage (R10a)
                    self._send_resp_headers(200, ctype, route.label, failovers, obs.pseudo_success)
                    self._write(body_bytes)
                    srv.note_request(requested, route.label, failovers)
                    return

                # ---- 200, streaming: buffer the head until `model` is seen (or a cap),
                #      so we can fail over a downgrade BEFORE committing bytes (R1) ----
                head: list[bytes] = []
                head_bytes = 0
                stream_broke = False
                try:
                    while head_bytes < _STREAM_HEAD_CAP:
                        c = resp.read(8192)
                        if not c:
                            break
                        head.append(c)
                        head_bytes += len(c)
                        if _extract(b"".join(head), ctype).get("model"):
                            break
                except Exception:  # upstream dropped/garbled before we committed any byte
                    stream_broke = True
                if stream_broke:  # nothing sent yet → treat like a failed attempt, fail over
                    srv.observer.record(srv.observer.classify(okey, 503, {}, {},
                                        expected_model=expected), count_usage=False)
                    if more:
                        failovers.append({"provider": route.label, "status": "stream-error",
                                          "reason": "upstream stream interrupted"})
                        continue
                    self._send_resp_headers(502, "application/json", route.label, failovers, False)
                    self._write(json.dumps(
                        {"error": {"message": "upstream stream failed"}}).encode())
                    srv.note_request(requested, route.label, failovers)
                    return

                obs = srv.observer.classify(okey, 200, rhdrs, _extract(b"".join(head), ctype),
                                            expected_model=expected)
                if obs.pseudo_success and more:  # downgrade detected pre-commit → fail over
                    srv.observer.record(obs, count_usage=False)
                    failovers.append({"provider": route.label, "status": 200, "reason": obs.note})
                    continue
                # commit: stream the buffered head + the remainder (headers now sent —
                # a later read error can only truncate, never fail over).
                self._send_resp_headers(200, ctype, route.label, failovers, obs.pseudo_success)
                full = list(head)
                ok = all(self._write(c) for c in head)
                try:
                    while ok:
                        c = resp.read(8192)
                        if not c:
                            break
                        full.append(c)
                        ok = self._write(c)
                except Exception:
                    pass  # headers committed; partial stream is unavoidable
                srv.observer.record(srv.observer.classify(okey, 200, rhdrs,
                                    _extract(b"".join(full), ctype), expected_model=expected),
                                    count_usage=True)
                srv.note_request(requested, route.label, failovers)
                return
            finally:
                try:  # release the upstream socket/fd promptly (don't lean on GC)
                    resp.close()
                except Exception:
                    pass
            return


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
        max_body_bytes: int = 10 * 1024 * 1024,
        default_cooldown: float = 60.0,
        failover_log_path: str | None = None,
    ) -> None:
        super().__init__((host, port), _ProxyHandler)
        self.upstream_base = upstream_base
        self.api_key = api_key
        self.routes = routes or {}
        self.observer = observer or GatewayProxy()
        self.fwd_timeout = fwd_timeout
        self.strip_v1 = strip_v1
        # Gateway mode (ADR-0005 P1): a bearer token (None = open) and the
        # agent-facing model ids to serve at /v1/models (None = don't intercept).
        self.token = token
        self.model_ids = model_ids
        # P2 failover: model id → ordered (cost-ranked) candidate chain; a
        # provider-keyed cooldown with Retry-After expiry (R7/R10c); and a bounded
        # in-memory failover event log (+ optional JSONL file) for visibility (D3).
        self.pools = pools or {}
        self.max_body_bytes = max_body_bytes
        self.default_cooldown = default_cooldown
        self.failover_log_path = failover_log_path
        self._cooldown: dict[str, float] = {}
        self._cooldown_lock = threading.Lock()
        self.failover_events: collections.deque[dict] = collections.deque(maxlen=200)

    def route_for(self, model: str) -> UpstreamRoute | None:
        """Which upstream serves ``model``: an explicit route, else the single
        upstream fallback, else None (no route → 502)."""
        if model in self.routes:
            return self.routes[model]
        if self.upstream_base:
            return UpstreamRoute(self.upstream_base, self.api_key)
        return None

    def chain_for(self, model: str) -> list[UpstreamRoute]:
        """The ordered failover chain for ``model``: a configured pool (multiple
        cost-ranked providers), else a single route/upstream (a chain of one), else
        ``[]`` (no route → 502). A 1-element chain never fails over — exactly the
        pre-P2 single-upstream behavior."""
        if model in self.pools:
            return list(self.pools[model])
        single = self.route_for(model)
        return [single] if single is not None else []

    def order_by_cooldown(self, chain: list[UpstreamRoute]) -> list[UpstreamRoute]:
        """Try providers NOT in active cooldown first; keep cooled ones as a
        last resort so a stale cooldown never permanently blocks a request (R7)."""
        now = time.monotonic()
        with self._cooldown_lock:
            fresh = [r for r in chain if self._cooldown.get(r.upstream_base, 0.0) <= now]
            cooled = [r for r in chain if self._cooldown.get(r.upstream_base, 0.0) > now]
        return fresh + cooled

    def set_cooldown(self, route: UpstreamRoute, retry_after: int | None) -> None:
        """Mark a provider out-of-capacity until ``Retry-After`` (or a default),
        keyed by provider (upstream_base) — a 429 is account-level, so all of that
        provider's models are skipped, not just the one (R10c)."""
        secs = float(retry_after) if (retry_after and retry_after > 0) else self.default_cooldown
        with self._cooldown_lock:
            self._cooldown[route.upstream_base] = time.monotonic() + secs

    def note_request(self, model: str, served_by: str, failovers: list[dict]) -> None:
        """Record a request that involved failover (visibility, D3): an in-memory
        ring buffer the console reads, plus an optional JSONL append. No-op when no
        failover happened (the common path stays silent and cheap)."""
        if not failovers:
            return
        event = {"model": model, "served_by": served_by, "failovers": list(failovers)}
        with self._cooldown_lock:
            self.failover_events.append(event)
        if self.failover_log_path:
            try:
                with open(self.failover_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event) + "\n")
            except OSError:
                pass

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
