#!/usr/bin/env python3
"""Dogfood the adopted litellm.Router money-path (ADR-0017 / ADOPT-MAP.md).

Runs a REAL request end-to-end through the adopted commodity plane and prints a proof:

    gateway config (a real GatewayProxyServer) -> litellm_plane.make_router
    -> litellm.Router.completion -> httpx send to a local stub upstream -> served response

It also proves the preserved money-path controls fire on that live path:
  * the stub upstream receives exactly the key stored BOUND to its base (#181 base-bound read)
  * a cloud-metadata base is refused (SSRF)
  * an off-preset (attacker) base is refused by the fail-closed egress allowlist (egress.py)
  * an Anthropic-only model has no deployment (SG-never-Anthropic)

Run it (litellm must be installed):

    PYTHONPATH=src python3 tools/dogfood_litellm_router.py

Self-contained — the "upstream" is a local stub so no provider key or network egress is
needed — but it exercises the exact gateway->router->send code a live request takes.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# Make this checkout's src importable when run as `python3 tools/dogfood_litellm_router.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from charon import egress, secrets  # noqa: E402
from charon.litellm_plane import litellm_router as lr  # noqa: E402
from charon.proxy_server import GatewayProxyServer, UpstreamRoute  # noqa: E402


class _Stub(BaseHTTPRequestHandler):
    captured_auth = None

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        type(self).captured_auth = self.headers.get("Authorization")
        body = json.dumps({
            "id": "chatcmpl-dogfood", "object": "chat.completion", "created": 0, "model": "ma",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "pong"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    httpd = HTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}/v1"

    with tempfile.TemporaryDirectory() as home:
        os.environ["CHARON_HOME"] = home
        secrets.set_provider_key("stub", "DOGFOOD-KEY", base_url=base)

        print("== charon litellm.Router dogfood ==")
        print(f"upstream base : {base}  (loopback — egress-allowed local provider)")

        # 1) real served request through the adopted router
        srv = GatewayProxyServer(host="127.0.0.1", port=0, default_cooldown=45.0, pools={
            "charon/cheapest": [UpstreamRoute(upstream_base=base, api_key=None,
                                              provider="stub", upstream_model="ma")]})
        router = lr.make_router(srv)
        resp = lr.complete_via_router(router, {
            "model": "charon/cheapest",
            "messages": [{"role": "user", "content": "ping"}]})
        srv.server_close()
        content = resp["choices"][0]["message"]["content"]
        print("request model : charon/cheapest")
        print(f"served content: {content!r}")
        print(f"upstream saw  : {_Stub.captured_auth!r}  (base-bound #181 key delivered)")
        assert content == "pong"
        assert _Stub.captured_auth == "Bearer DOGFOOD-KEY"

        # 2) SSRF: a cloud-metadata base is refused before the Router builds
        meta = GatewayProxyServer(host="127.0.0.1", port=0, pools={
            "m": [UpstreamRoute(upstream_base="http://169.254.169.254/v1", provider="evil")]})
        try:
            lr.make_router(meta)
            ssrf_ok = False
        except lr.AdoptError as exc:
            ssrf_ok = True
            print(f"ssrf refused  : {exc}")
        finally:
            meta.server_close()
        assert ssrf_ok

        # 3) egress allowlist: an off-preset (attacker) base is refused (fail-closed)
        off = GatewayProxyServer(host="127.0.0.1", port=0, pools={
            "m": [UpstreamRoute(upstream_base="https://attacker.example/v1", provider="x")]})
        try:
            lr.make_router(off)
            egress_ok = False
        except egress.EgressPolicyError as exc:
            egress_ok = True
            print(f"egress refused: {str(exc).splitlines()[0]}")
        finally:
            off.server_close()
        assert egress_ok

        # 4) SG-never-Anthropic: no deployment for an anthropic-only model
        ant = GatewayProxyServer(host="127.0.0.1", port=0, pools={
            "claude-3": [UpstreamRoute(upstream_base="https://api.anthropic.com/v1",
                                       provider="anthropic")]})
        anthropic_router = lr.make_router(ant)
        ant.server_close()
        print(f"anthropic legs: {anthropic_router.model_list}  (SG-never-Anthropic: dropped)")
        assert anthropic_router.model_list == []

    httpd.shutdown()
    print("== DOGFOOD OK: served through adopted litellm.Router; all 4 controls fired ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
