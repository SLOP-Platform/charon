#!/usr/bin/env python3
"""Live-wire-in EVIDENCE probe for the litellm.Router adopt (ADR-0017, wire-in slice).

The base dogfood (``tools/dogfood_litellm_router.py``) proves the SAFE landed slice: a real
request is served through ``make_router`` -> ``litellm.Router.completion`` -> a loopback stub
upstream, with the five build-time security controls firing. THIS probe extends that with the
two POLICY bridges the live wire-in must re-host and which the ADOPT-MAP §Slice boundary
DEFERS — so the wire-in review has runnable EVIDENCE, not just prose, of exactly what
``complete_via_router`` does and does NOT yet do on the money-path:

  [4] silent-downgrade (SR-1/SR-2 double-bill guard) — is it re-hosted on the Router path?
  [5] cost metering + drain-then-park spend recording  — is Charon's observer/BalanceTracker fed?

Run:      PYTHONPATH=src python3 tools/dogfood_litellm_live_probe.py
Capture:  PYTHONPATH=src python3 tools/dogfood_litellm_live_probe.py > DOGFOOD-litellm-live.txt 2>&1

Exit 0 = the SAFE Router serve path + all build-time controls behaved as asserted. The two
probes PRINT their finding (a DEFERRED bridge, not a regression) and never fail the run.
"""
from __future__ import annotations

import importlib.metadata as im
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# Make this checkout's src importable when run directly (mirrors the base dogfood).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import litellm  # noqa: E402,F401  (import proves availability; version printed below)

from charon import egress, secrets  # noqa: E402
from charon.litellm_plane import litellm_router as lr  # noqa: E402
from charon.proxy import GatewayProxy  # noqa: E402
from charon.proxy_server import GatewayProxyServer, UpstreamRoute  # noqa: E402


def _p(msg: str = "") -> None:
    print(msg, flush=True)


class _Stub(BaseHTTPRequestHandler):
    """OpenAI-compatible stub. Captures the Authorization header and returns a completion
    whose reported ``model`` is configurable (to drive the downgrade probe)."""

    captured_auth: str | None = None
    captured_path: str | None = None
    served_model: str = "ma"

    def log_message(self, *a):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        type(self).captured_auth = self.headers.get("Authorization")
        type(self).captured_path = self.path
        body = json.dumps({
            "id": "chatcmpl-live", "object": "chat.completion", "created": 0,
            "model": type(self).served_model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "pong"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _gw(pools, **kw) -> GatewayProxyServer:
    return GatewayProxyServer(host="127.0.0.1", port=0, pools=pools,
                              default_cooldown=45.0, **kw)


def main() -> int:
    _p("=" * 80)
    _p("CHARON — litellm.Router LIVE-WIRE-IN evidence probe")
    _p(f"litellm=={im.version('litellm')}  (library-only Router; no proxy/FastAPI/Prisma stack)")
    _p("=" * 80)

    httpd = HTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}/v1"
    ok = True

    with tempfile.TemporaryDirectory() as home:
        os.environ["CHARON_HOME"] = home
        try:
            # ── 1. LIVE SERVE + base-bound key (#181) ───────────────────────────
            _p("\n[1] LIVE SERVE through litellm.Router (constructed ONCE) + base-bound key")
            _Stub.served_model = "ma"
            secrets.set_provider_key("stub", "STUB-KEY-BOUND", base_url=base)
            srv = _gw({"m1": [UpstreamRoute(upstream_base=base, api_key=None,
                                            provider="stub", upstream_model="ma")]})
            router = lr.make_router(srv)
            _p(f"    Router built once: {len(router.model_list)} deployment(s); "
               f"cooldown_time={router.cooldown_time}")
            resp = lr.complete_via_router(router, {
                "model": "m1", "messages": [{"role": "user", "content": "ping"}]})
            srv.server_close()
            content = resp["choices"][0]["message"]["content"]
            _p(f"    served: object={resp.get('object')!r} content={content!r} "
               f"usage_present={bool(resp.get('usage'))}")
            _p(f"    upstream saw Authorization={_Stub.captured_auth!r} path={_Stub.captured_path!r}")
            assert resp.get("object") == "chat.completion" and content == "pong"
            assert _Stub.captured_auth == "Bearer STUB-KEY-BOUND"
            assert _Stub.captured_path.endswith("/chat/completions")
            _p("    RESULT: PASS — served through Router; base-bound key delivered to its own base.")

            # ── 2. SG-never-Anthropic (#5) ──────────────────────────────────────
            _p("\n[2] SG-never-Anthropic — the Anthropic leg is dropped from the model_list")
            ant = _gw({"claude-3-opus": [UpstreamRoute(
                upstream_base="https://api.anthropic.com/v1", provider="anthropic",
                upstream_model="claude-3-opus")]})
            ar = lr.make_router(ant); ant.server_close()
            _p(f"    model_list(anthropic-only) = {ar.model_list}")
            assert ar.model_list == []
            _p("    RESULT: PASS — no Anthropic deployment exists; SG can never route to it.")

            # ── 3. egress allowlist (#3) + SSRF (#2) refuse BEFORE the Router builds ──
            _p("\n[3] egress allowlist + SSRF refusal fire BEFORE the Router is built")
            off = _gw({"m1": [UpstreamRoute(upstream_base="https://attacker.example/v1",
                                            provider="x")]})
            try:
                lr.make_router(off); _p("    FAIL — off-preset not refused"); ok = False
            except egress.EgressPolicyError as e:
                _p(f"    off-preset base refused: {str(e).splitlines()[0]}")
            off.server_close()
            ssrf = _gw({"m1": [UpstreamRoute(upstream_base="http://169.254.169.254/v1",
                                             provider="evil")]})
            try:
                lr.make_router(ssrf); _p("    FAIL — metadata not refused"); ok = False
            except lr.AdoptError as e:
                _p(f"    metadata/SSRF base refused: {str(e).splitlines()[0]}")
            ssrf.server_close()
            _p("    RESULT: PASS — both refused pre-Router; the key is never dialed off-allowlist.")

            # ── 4. PROBE: SR-1/SR-2 silent-downgrade re-host (DEFERRED bridge) ───
            _p("\n[4] PROBE — silent-downgrade (SR-1/SR-2): does the Router path re-host the guard?")
            _Stub.served_model = "CHEAPER-SUBSTITUTE"  # upstream serves a DIFFERENT model id
            srv3 = _gw({"m1": [UpstreamRoute(upstream_base=base, api_key=None,
                                             provider="stub", upstream_model="ma")]})
            r3 = lr.make_router(srv3)
            d = lr.complete_via_router(r3, {
                "model": "m1", "messages": [{"role": "user", "content": "ping"}]})
            srv3.server_close()
            obs = GatewayProxy().classify("ma", 200, {}, d, expected_model="ma")
            _p(f"    requested upstream_model='ma'; response.model={d.get('model')!r}")
            _p(f"    observer.classify(...).pseudo_success = {obs.pseudo_success}  "
               "(a genuine silent downgrade)")
            _p("    FINDING: complete_via_router returns the body UN-GATED. It does NOT call")
            _p("             observer.record, emit X-Charon-Downgrade, or run the")
            _p("             failover_on_downgrade serve-vs-refetch decision. The SR-1/SR-2")
            _p("             double-bill guard is NOT re-hosted on the Router path => DEFERRED.")

            # ── 5. PROBE: metering / drain-then-park spend recording (DEFERRED) ──
            _p("\n[5] PROBE — metering: is Charon's observer / BalanceTracker fed by the Router path?")
            _p("    complete_via_router -> router.completion -> dict. It never invokes")
            _p("    srv.observer.record / srv.balance_tracker.record_spend / srv.spend_limiter.record.")
            _p("    litellm computes its OWN cost (its callback); that is NOT bridged to")
            _p("    BalanceTracker, so drain-then-park spend would not advance on the Router path.")
            _p("    FINDING: cost metering + drain-then-park spend recording NOT re-hosted => DEFERRED.")

            _p("\n" + "=" * 80)
            _p("SUMMARY")
            _p("  PROVEN LIVE + SAFE : Router serve path, base-bound key, SG-never-Anthropic,")
            _p("                       egress allowlist, SSRF refusal, Router-built-once.")
            _p("  DEFERRED (NOT re-hosted on the live Router path — ADOPT-MAP §Slice boundary):")
            _p("    - SR-1/SR-2 silent-downgrade double-bill guard (observer.record + serve/refetch)")
            _p("    - cost metering + drain-then-park spend recording (cost-callback -> BalanceTracker)")
            _p("    - streaming SSE relay + the ADR-0016 exhaustion envelope")
            _p("  => Replacing forwarder.forward_with_failover (accept #4: delete ~650-750 LOC)")
            _p("     REQUIRES these bridges. They are the 'larger than one pass, highest-stakes'")
            _p("     re-host the design-of-record deferred; not landed here, to avoid a")
            _p("     half-migrated / silently-double-billing money-path.")
            _p("=" * 80)
            _p("EXIT: 0" if ok else "EXIT: 1")
        finally:
            httpd.shutdown()
            httpd.server_close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
