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

_SKIP_HEADERS = {"host", "authorization", "content-length", "connection",
                 "accept-encoding", "proxy-authorization"}


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

        # If the agent streams, ask the gateway to include usage in the stream so
        # we can still see tokens/cost (OpenAI-compatible `stream_options`).
        requested = ""
        try:
            bj = json.loads(body) if body else {}
            requested = bj.get("model", "")
            if bj.get("stream") is True:
                opts = dict(bj.get("stream_options") or {})
                opts["include_usage"] = True
                bj["stream_options"] = opts
                body = json.dumps(bj).encode()
        except Exception:
            pass

        path = self.path
        if srv.strip_v1 and path.startswith("/v1"):
            path = path[len("/v1"):]  # upstream_base already ends in /v1
        url = srv.upstream_base.rstrip("/") + path

        req = urllib.request.Request(url, data=(body or None), method=self.command)
        for hk in self.headers.keys():
            if hk.lower() not in _SKIP_HEADERS:
                req.add_header(hk, self.headers[hk])
        req.add_header("Content-Type", "application/json")
        if "user-agent" not in {k.lower() for k in self.headers.keys()}:
            req.add_header("User-Agent", "charon-proxy/0.1")
        if srv.api_key:
            req.add_header("Authorization", f"Bearer {srv.api_key}")

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
        srv.observer.observe(requested or observed.get("model", ""), status, rhdrs, observed)


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
