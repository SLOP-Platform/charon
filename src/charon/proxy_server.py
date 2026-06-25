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

from .proxy import GatewayProxy


class _ProxyHandler(http.server.BaseHTTPRequestHandler):
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

        path = self.path
        if srv.strip_v1 and path.startswith("/v1"):
            path = path[len("/v1"):]  # upstream_base already ends in /v1
        url = srv.upstream_base.rstrip("/") + path

        req = urllib.request.Request(url, data=(body or None), method=self.command)
        # Forward the client's headers faithfully (some gateways 403 an unfamiliar
        # User-Agent), but never the hop-by-hop ones or the caller's auth/host —
        # the proxy injects the real upstream key itself (creds stay here).
        _skip = {"host", "authorization", "content-length", "connection",
                 "accept-encoding", "proxy-authorization"}
        for hk in self.headers.keys():
            if hk.lower() not in _skip:
                req.add_header(hk, self.headers[hk])
        req.add_header("Content-Type", "application/json")
        if "user-agent" not in {k.lower() for k in self.headers.keys()}:
            req.add_header("User-Agent", "charon-proxy/0.1")
        if srv.api_key:
            req.add_header("Authorization", f"Bearer {srv.api_key}")

        try:
            resp = urllib.request.urlopen(req, timeout=srv.fwd_timeout)
            status, data, rhdrs = resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as exc:
            status, data, rhdrs = exc.code, exc.read(), dict(exc.headers)
        except Exception as exc:  # upstream unreachable
            status = 502
            data = json.dumps({"error": {"message": str(exc)}}).encode()
            rhdrs = {}

        # observe (the whole point): turn this response into a Charon signal
        requested = ""
        try:
            requested = json.loads(body or b"{}").get("model", "")
        except Exception:
            pass
        body_json = {}
        try:
            body_json = json.loads(data)
        except Exception:
            pass
        srv.observer.observe(requested, status, rhdrs, body_json)

        # relay unchanged
        self.send_response(status)
        self.send_header("Content-Type", rhdrs.get("Content-Type", "application/json"))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class GatewayProxyServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """A loopback OpenAI-compatible proxy in front of one upstream gateway."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        upstream_base: str,
        api_key: str | None,
        observer: GatewayProxy | None = None,
        host: str = "127.0.0.1",
        port: int = 0,
        fwd_timeout: float = 180.0,
        strip_v1: bool = True,
    ) -> None:
        super().__init__((host, port), _ProxyHandler)
        self.upstream_base = upstream_base
        self.api_key = api_key
        self.observer = observer or GatewayProxy()
        self.fwd_timeout = fwd_timeout
        self.strip_v1 = strip_v1

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
