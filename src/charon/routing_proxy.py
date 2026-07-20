"""Per-unit observability proxy (ORCH-ROUTE-PROXY).

A lightweight, single-upstream HTTP proxy that accepts OpenAI-compatible chat
completion requests, routes them to a configured target (model + apiKey),
records usage telemetry, and passes through the upstream response unchanged.

Runs ephemerally per ``charon work`` run on a random loopback port. The
coordinator starts it before dispatch, reads cumulative usage via
``GET /usage`` between dispatches, and terminates it when the run ends.

Stdlib only — ``http.server`` + ``urllib``. No third-party deps.
"""
from __future__ import annotations

import argparse
import http.server
import json
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from . import netutil  # key-egress choke point (keyed_request/open_keyed)

# Cap the streamed bytes buffered while looking for the response ``model`` id.
_STREAM_HEAD_CAP = 65536

_SKIP_HEADERS = {"host", "authorization", "content-length", "connection",
                 "accept-encoding", "proxy-authorization", "transfer-encoding"}


class RoutingProxyServer(http.server.HTTPServer):
    """Single-upstream routing proxy with per-request telemetry."""

    allow_reuse_address = True

    def __init__(self, host: str, port: int, target_model: str,
                 upstream_base: str, api_key: str | None = None) -> None:
        self.target_model = target_model
        self.upstream_base = upstream_base.rstrip("/")
        self.api_key = api_key
        self.total_requests = 0
        self._lock = threading.Lock()
        super().__init__((host, port), _RoutingHandler)

    @property
    def url(self) -> str:
        host, port = self.server_address[0], self.server_address[1]
        if isinstance(host, bytes):
            host = host.decode()
        return f"http://{host}:{port}"

    def note_request(self, usage: dict | None = None) -> None:
        with self._lock:
            self.total_requests += 1

    def usage_snapshot(self) -> dict:
        with self._lock:
            return {"requests": self.total_requests}


class _RoutingHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:
        pass

    def do_GET(self) -> None:
        srv: RoutingProxyServer = self.server  # type: ignore[assignment]
        if urlsplit(self.path).path.rstrip("/") == "/usage":
            self._json(200, srv.usage_snapshot())
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        srv: RoutingProxyServer = self.server  # type: ignore[assignment]

        length = int(self.headers.get("Content-Length") or 0)
        if length > 10 * 1024 * 1024:
            self._json(413, {"error": "body too large"})
            return
        raw = self.rfile.read(length) if length else b""

        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid JSON"})
            return

        if not isinstance(body, dict):
            self._json(400, {"error": "expected JSON object"})
            return

        body["model"] = srv.target_model
        is_stream = body.get("stream") is True

        req_data = json.dumps(body).encode()
        url = srv.upstream_base + "/chat/completions"
        try:
            # Key-egress choke point: attaches the Bearer, SSRF-validates the base
            # and refuses redirects (urllib does NOT strip Authorization cross-host).
            req = netutil.keyed_request(
                url, api_key=srv.api_key or None, data=req_data, method="POST",
                headers={"Content-Type": "application/json"})
            resp = netutil.open_keyed(req, timeout=300)
        except urllib.error.HTTPError as exc:
            srv.note_request()
            self._relay_error(exc)
            return
        except Exception:  # noqa: BLE001
            srv.note_request()
            self._json(502, {"error": {"message": "upstream unreachable"}})
            return

        ctype = resp.headers.get("Content-Type", "application/json")

        if not is_stream:
            body_bytes = self._drain(resp)
            srv.note_request()
            self._relay(resp.status, ctype, body_bytes)
            return

        # Streaming: relay SSE chunks as received
        srv.note_request()
        self.send_response(resp.status)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

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

    def _relay(self, status: int, ctype: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _relay_error(self, exc: urllib.error.HTTPError) -> None:
        try:
            body = exc.read()
        except Exception:  # noqa: BLE001
            body = b""
        self.send_response(exc.code)
        for hk, hv in exc.headers.items():
            if hk.lower() not in _SKIP_HEADERS:
                self.send_header(hk, hv)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


def _main() -> None:
    p = argparse.ArgumentParser(description="Routing proxy for per-unit LLM telemetry")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--target-model", required=True)
    p.add_argument("--upstream-base", required=True)
    p.add_argument("--api-key", default=None)
    p.add_argument("--report-path", default=None,
                   help="Write usage JSON to this file on shutdown")
    args = p.parse_args()

    srv = RoutingProxyServer(
        host=args.host, port=args.port,
        target_model=args.target_model,
        upstream_base=args.upstream_base,
        api_key=args.api_key,
    )
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()

    # Print the bound port so the caller can discover it
    print(f"proxy:{srv.server_address[1]}", flush=True)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        srv.shutdown()
        if args.report_path:
            try:
                Path(args.report_path).write_text(
                    json.dumps(srv.usage_snapshot()))
            except OSError:
                pass


if __name__ == "__main__":
    _main()
