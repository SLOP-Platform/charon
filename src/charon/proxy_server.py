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

import http.server
import json
import socketserver
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass

from .proxy import GatewayProxy


@dataclass(frozen=True)
class UpstreamRoute:
    """Where one agent-facing model id is forwarded (multi-provider pools)."""

    upstream_base: str
    api_key: str | None = None
    upstream_model: str | None = None  # rewrite the body's model to this id upstream
    pool_id: str | None = None  # observe under this id (the router's pool id) if set

_SKIP_HEADERS = {"host", "authorization", "content-length", "connection",
                 "accept-encoding", "proxy-authorization"}
_DEFAULT_UA = "charon-proxy/0.1"
# Library-default UAs upstream bot-protection bans (Cloudflare 1010); normalize
# these to the proxy's own identity so an internal urllib caller isn't blocked.
_BANNED_UA_PREFIXES = ("python-urllib", "python-requests")


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

    def _handle(self) -> None:
        srv: GatewayProxyServer = self.server  # type: ignore[assignment]
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""

        bj: dict = {}
        requested = ""
        try:
            bj = json.loads(body) if body else {}
            requested = bj.get("model", "")
        except Exception:
            pass

        # Which upstream serves this model (multi-provider pools)?
        route = srv.route_for(requested)
        if route is None:
            srv.observer.observe(requested, 502, {}, {})
            data = json.dumps({"error": {"message": f"no route for model {requested!r}"}}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)
            return

        # Rewrite the body: the upstream's real model id, and (if streaming) ask
        # for usage in the stream so we can still see tokens/cost.
        if bj:
            if route.upstream_model:
                bj["model"] = route.upstream_model
            if bj.get("stream") is True:
                opts = dict(bj.get("stream_options") or {})
                opts["include_usage"] = True
                bj["stream_options"] = opts
            body = json.dumps(bj).encode()

        path = self.path
        if srv.strip_v1 and path.startswith("/v1"):
            path = path[len("/v1"):]  # upstream_base already ends in /v1
        url = route.upstream_base.rstrip("/") + path

        req = urllib.request.Request(url, data=(body or None), method=self.command)
        for hk in self.headers.keys():
            # User-Agent is normalized separately (below) — never forwarded raw.
            if hk.lower() not in _SKIP_HEADERS and hk.lower() != "user-agent":
                req.add_header(hk, self.headers[hk])
        req.add_header("Content-Type", "application/json")
        # Egress identity: forward the agent's real UA (e.g. opencode/x — some
        # gateways 403 an unknown one), but replace an absent or library-default
        # UA with the proxy's own. A urllib/requests default leaks through as
        # "Python-urllib/3.x", which upstream bot-protection bans (Cloudflare
        # error 1010 → 403) — e.g. Charon's own pre-flight probe. Live-verified.
        client_ua = self.headers.get("User-Agent", "")
        if client_ua and not client_ua.lower().startswith(_BANNED_UA_PREFIXES):
            req.add_header("User-Agent", client_ua)
        else:
            req.add_header("User-Agent", _DEFAULT_UA)
        if route.api_key:
            req.add_header("Authorization", f"Bearer {route.api_key}")

        try:
            resp = urllib.request.urlopen(req, timeout=srv.fwd_timeout)
            status, rhdrs = resp.status, dict(resp.headers)
        except urllib.error.HTTPError as exc:
            resp, status, rhdrs = exc, exc.code, dict(exc.headers)
        except Exception as exc:  # upstream unreachable
            srv.observer.observe(requested, 502, {}, {})
            data = json.dumps({"error": {"message": str(exc)}}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)
            return

        # Stream the response straight through (so the agent's SSE keeps flowing)
        # while accumulating it to extract the observation afterward.
        ctype = rhdrs.get("Content-Type", "application/json")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        chunks: list[bytes] = []
        try:
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                chunks.append(chunk)
                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
        except Exception:
            pass

        observed = _extract(b"".join(chunks), ctype)
        # observe under the router's pool id (so failover/exclusion line up), or
        # the requested model when single-upstream.
        observe_id = route.pool_id or requested or observed.get("model", "")
        # The native id actually served upstream (after any model rewrite) — the
        # baseline for the pseudo-success/silent-downgrade check, so a prefixed
        # pool id doesn't false-positive an honest 200 (see GatewayProxy.observe).
        expected = route.upstream_model or requested or None
        srv.observer.observe(observe_id, status, rhdrs, observed, expected_model=expected)


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
    ) -> None:
        super().__init__((host, port), _ProxyHandler)
        self.upstream_base = upstream_base
        self.api_key = api_key
        self.routes = routes or {}
        self.observer = observer or GatewayProxy()
        self.fwd_timeout = fwd_timeout
        self.strip_v1 = strip_v1

    def route_for(self, model: str) -> UpstreamRoute | None:
        """Which upstream serves ``model``: an explicit route, else the single
        upstream fallback, else None (no route → 502)."""
        if model in self.routes:
            return self.routes[model]
        if self.upstream_base:
            return UpstreamRoute(self.upstream_base, self.api_key)
        return None

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
