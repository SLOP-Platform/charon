"""ORCH-ROUTE-PROXY — per-unit observability proxy tests.

Covers: routing proxy forwards requests, reports usage, handles streaming,
handles errors, and is discoverable via printed port line.
"""
from __future__ import annotations

import http.server
import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

from charon.routing_proxy import RoutingProxyServer


def _mock_upstream(port: int = 0) -> tuple[str, http.server.HTTPServer, dict]:
    """Return (url, server) for a mock upstream that echoes back the model
    and body it received."""
    captured: dict = {}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length)
            body = json.loads(raw)
            captured["model"] = body.get("model")
            captured["messages"] = body.get("messages")
            captured["auth"] = self.headers.get("Authorization")

            resp = json.dumps({
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "model": body.get("model", "?"),
                "choices": [{"index": 0, "message": {
                    "role": "assistant", "content": "hello"}}],
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

    srv = http.server.HTTPServer(("127.0.0.1", port), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    host, bound_port = srv.server_address[:2]
    if isinstance(host, bytes):
        host = host.decode()
    return f"http://{host}:{bound_port}/v1", srv, captured


def _post(url: str, body: dict) -> tuple[int, dict]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url + "/chat/completions", data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_routing_proxy_forwards_request():
    upstream_url, mock_srv, captured = _mock_upstream()
    try:
        proxy = RoutingProxyServer(
            "127.0.0.1", 0,
            target_model="deepseek-v4-pro",
            upstream_base=upstream_url,
            api_key="sk-test-key",
        )
        t = threading.Thread(target=proxy.serve_forever, daemon=True)
        t.start()
        try:
            status, resp = _post(proxy.url, {
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "hi"}],
            })
            assert status == 200
            assert resp["model"] == "deepseek-v4-pro"
            assert captured["model"] == "deepseek-v4-pro"  # mutated
            assert captured["auth"] == "Bearer sk-test-key"
        finally:
            proxy.shutdown()
    finally:
        mock_srv.shutdown()


def test_routing_proxy_usage_counter():
    upstream_url, mock_srv, _ = _mock_upstream()
    try:
        proxy = RoutingProxyServer(
            "127.0.0.1", 0,
            target_model="m", upstream_base=upstream_url,
        )
        t = threading.Thread(target=proxy.serve_forever, daemon=True)
        t.start()
        try:
            assert proxy.usage_snapshot()["requests"] == 0
            _post(proxy.url, {"model": "x", "messages": [{"role": "user", "content": "a"}]})
            assert proxy.usage_snapshot()["requests"] == 1
            _post(proxy.url, {"model": "y", "messages": [{"role": "user", "content": "b"}]})
            assert proxy.usage_snapshot()["requests"] == 2
        finally:
            proxy.shutdown()
    finally:
        mock_srv.shutdown()


def test_routing_proxy_usage_endpoint():
    upstream_url, mock_srv, _ = _mock_upstream()
    try:
        proxy = RoutingProxyServer(
            "127.0.0.1", 0,
            target_model="m", upstream_base=upstream_url,
        )
        t = threading.Thread(target=proxy.serve_forever, daemon=True)
        t.start()
        try:
            _post(proxy.url, {"model": "x", "messages": [{"role": "user", "content": "c"}]})
            r = urllib.request.urlopen(proxy.url + "/usage", timeout=5)
            data = json.loads(r.read())
            assert data["requests"] == 1
        finally:
            proxy.shutdown()
    finally:
        mock_srv.shutdown()


def test_routing_proxy_streaming():
    upstream_url, mock_srv, _ = _mock_upstream()
    try:
        proxy = RoutingProxyServer(
            "127.0.0.1", 0,
            target_model="m", upstream_base=upstream_url,
        )
        t = threading.Thread(target=proxy.serve_forever, daemon=True)
        t.start()
        try:
            # The mock doesn't stream, but the proxy handles stream=True correctly
            data = json.dumps({"model": "x", "stream": True,
                               "messages": [{"role": "user", "content": "d"}]}).encode()
            req = urllib.request.Request(
                proxy.url + "/chat/completions", data=data,
                headers={"Content-Type": "application/json"}, method="POST")
            status = urllib.request.urlopen(req, timeout=10).status
            assert status == 200
            assert proxy.usage_snapshot()["requests"] == 1
        finally:
            proxy.shutdown()
    finally:
        mock_srv.shutdown()


def test_routing_proxy_upstream_error():
    proxy = RoutingProxyServer(
        "127.0.0.1", 0,
        target_model="m",
        upstream_base="http://127.0.0.1:1/v1",  # nothing there
    )
    t = threading.Thread(target=proxy.serve_forever, daemon=True)
    t.start()
    try:
        status, resp = _post(proxy.url, {
            "model": "x", "messages": [{"role": "user", "content": "e"}],
        })
        assert status == 502
        assert "unreachable" in resp["error"]["message"]
    finally:
        proxy.shutdown()


def test_routing_proxy_cli_reports_port(tmp_path: Path):
    """The proxy main() prints the bound port to stdout for caller discovery."""
    upstream_url, mock_srv, _ = _mock_upstream()
    try:
        report = tmp_path / "usage.json"
        p = subprocess.Popen(
            [sys.executable, "-m", "charon.routing_proxy",
             "--target-model", "m",
             "--upstream-base", upstream_url,
             "--report-path", str(report)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            # Read the "proxy:PORT" line
            assert p.stdout is not None
            line = p.stdout.readline()
            assert line.strip().startswith("proxy:")
            port = int(line.strip().split(":")[1])
            assert port > 0
        finally:
            p.terminate()
            p.wait(timeout=5)
    finally:
        mock_srv.shutdown()
