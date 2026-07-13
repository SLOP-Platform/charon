"""ORCH-ROUTE-PROXY — per-unit observability proxy tests.

Covers: routing proxy forwards requests, reports usage, handles streaming,
handles errors, and is discoverable via printed port line.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

from charon.routing_proxy import RoutingProxyServer

# Absolute repo root / src, so the `python -m charon.routing_proxy` subprocess
# below can import charon irrespective of the ambient CWD or a *relative*
# PYTHONPATH=src that a prior test may have changed (test-isolation fix).
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"


def _hermetic_env() -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    parts = [str(_SRC_DIR), str(_REPO_ROOT)]
    if existing:
        parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def test_routing_proxy_forwards_request(mock_upstream, _post):
    upstream_url, mock_srv, captured = mock_upstream
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
        # P5: upstream POST carries the shared browser-like UA (never urllib default).
        from charon.netutil import BROWSER_UA
        assert captured["ua"] == BROWSER_UA
        assert captured["ua"] != "charon-proxy/0.1"
        assert not (captured["ua"] or "").lower().startswith("python-urllib")
    finally:
        proxy.shutdown()


def test_routing_proxy_usage_counter(mock_upstream, _post):
    upstream_url, mock_srv, _ = mock_upstream
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


def test_routing_proxy_usage_endpoint(mock_upstream, _post):
    upstream_url, mock_srv, _ = mock_upstream
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


def test_routing_proxy_streaming(mock_upstream):
    upstream_url, mock_srv, _ = mock_upstream
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


def test_routing_proxy_upstream_error(_post):
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


def test_routing_proxy_cli_reports_port(mock_upstream, tmp_path: Path):
    """The proxy main() prints the bound port to stdout for caller discovery."""
    upstream_url, mock_srv, _ = mock_upstream
    report = tmp_path / "usage.json"
    p = subprocess.Popen(
        [sys.executable, "-m", "charon.routing_proxy",
         "--target-model", "m",
         "--upstream-base", upstream_url,
         "--report-path", str(report)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        cwd=str(_REPO_ROOT), env=_hermetic_env(),
    )
    try:
        # Read the "proxy:PORT" line
        assert p.stdout is not None
        line = p.stdout.readline()
        if not line.strip().startswith("proxy:"):
            err = p.stderr.read() if p.stderr is not None else ""
            raise AssertionError(
                f"expected 'proxy:PORT' on stdout, got {line!r}; stderr: {err!r}"
            )
        port = int(line.strip().split(":")[1])
        assert port > 0
    finally:
        p.terminate()
        p.wait(timeout=5)
