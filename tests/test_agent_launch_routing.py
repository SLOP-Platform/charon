"""ADR-0014 Ticket A — the wire contract proving agent- & provider-AGNOSTIC tier
routing.

The engine resolves a *tier vid*, builds the per-run gateway with a tier-vid pool
(``gateway._build_routes_and_pools`` → free-first), and the agent requests that
vid. The gateway resolves vid→pool→provider and fails over with ZERO engine-side
selection. These tests pin the vid AT THE WIRE and at the ``AgentLaunch`` seam —
never an opencode-specific config shape, so any renderer honoring the seam passes.

The mock-upstream capture reuses ``tests/test_gateway_failover.py:19-31``
(``received.append(body.get("model"))``).
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.error
import urllib.request

from charon import api
from charon.gateway import _build_routes_and_pools
from charon.ports.agent_launch import (
    _ACP_KEY_PASSTHROUGH,
    _acp_passthrough_env,
    render,
)
from charon.proxy_server import GatewayProxyServer

TIER_VID = "high"  # the canonical tier vid (fleet `opus`) — bare, so it IS the wire id


# --- mock upstream: captures the wire model id (test_gateway_failover.py:19-31) ---
class _Prog(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        srv = self.server  # type: ignore[assignment]
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        srv.received.append(body.get("model"))           # type: ignore[attr-defined]
        if srv.status == 200:                            # type: ignore[attr-defined]
            payload = json.dumps({
                "model": srv.return_model,               # type: ignore[attr-defined]
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0},
            }).encode()
            self.send_response(200)
        else:
            payload = json.dumps(
                {"error": {"metadata": {"error_type": "rate_limit_exceeded"}}}).encode()
            self.send_response(srv.status)               # type: ignore[attr-defined]
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _up(status=200, return_model="m"):
    srv = _Threaded(("127.0.0.1", 0), _Prog)
    srv.status, srv.return_model = status, return_model   # type: ignore[attr-defined]
    srv.received = []                                     # type: ignore[attr-defined]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{srv.server_address[0]}:{srv.server_address[1]}"


def _req(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _registry(free_base, paid_base):
    """Two providers in one tier — a free/low-cost-rank and a paid one, LISTED
    paid-first so a passing free-first assertion proves the compiler re-sorts (not
    that we happened to list them in order). Each carries its own upstream id so
    the per-provider remap (R10b) sends each upstream a distinct wire model."""
    return {
        "paid-model": {"upstream_base": paid_base, "upstream_model": "paid-up",
                       "free": False, "cost_rank": 100},
        "free-model": {"upstream_base": free_base, "upstream_model": "free-up",
                       "free": True, "cost_rank": 0},
    }


def test_tier_pool_is_free_first_ordered():
    free, free_base = _up()
    paid, paid_base = _up()
    try:
        registry = _registry(free_base, paid_base)
        _, pools, ids = _build_routes_and_pools(
            registry, {TIER_VID: ["paid-model", "free-model"]}, {})
        chain = pools[TIER_VID]
        assert [r.upstream_base for r in chain] == [free_base, paid_base]  # free-first (D2)
        assert TIER_VID in ids
    finally:
        free.shutdown()
        paid.shutdown()


def test_agent_launch_pins_vid_at_the_seam_and_excludes_keys(monkeypatch):
    # A real provider key is present in the env; the rendered launch must NOT
    # carry it — the proxy holds the key (ADR-0014 D4 invariant).
    for k in _ACP_KEY_PASSTHROUGH:
        monkeypatch.setenv(k, "SECRET-must-not-leak")
    launch = render("opencode acp", "http://127.0.0.1:9999", TIER_VID)

    assert launch.requested_model == TIER_VID            # the vid IS the wire model
    assert launch.argv == ["opencode", "acp"]
    for k in _ACP_KEY_PASSTHROUGH:                        # include_keys=False invariant
        assert k not in launch.passthrough_env
    # Agnostic check: the per-run proxy URL must reach the agent SOMEHOW (any
    # renderer must wire it) — asserted on the env, not an opencode config shape.
    assert any("http://127.0.0.1:9999" in v for v in launch.passthrough_env.values())


def test_bare_path_forwards_gateway_token_when_set(monkeypatch):
    # WORK-GATEWAY-WIRE: the bare ``charon work`` acp path (include_keys=True) must
    # carry CHARON_GATEWAY_TOKEN so the spawned agent authenticates to the standing
    # Charon gateway it is configured for (else every LLM call 401s).
    monkeypatch.setenv("CHARON_GATEWAY_TOKEN", "gw-bearer-xyz")
    env = _acp_passthrough_env()  # default include_keys=True == the bare path
    assert env.get("CHARON_GATEWAY_TOKEN") == "gw-bearer-xyz"


def test_bare_path_omits_gateway_token_when_unset(monkeypatch):
    # Never inject an empty/placeholder value — absent in the env means absent in
    # the forwarded set.
    monkeypatch.delenv("CHARON_GATEWAY_TOKEN", raising=False)
    assert "CHARON_GATEWAY_TOKEN" not in _acp_passthrough_env()


def test_bare_path_forwards_only_the_gateway_token_no_general_hole(monkeypatch):
    # Security regression guard: forwarding the one gateway bearer opens no general
    # hole. An arbitrary SECRET_* (and any non-whitelisted var) stays absent; only
    # the gateway token plus the pre-existing whitelisted vars/provider keys cross.
    monkeypatch.setenv("CHARON_GATEWAY_TOKEN", "gw-bearer-xyz")
    monkeypatch.setenv("SECRET_AWS", "must-not-leak")
    monkeypatch.setenv("RANDOM_TOKEN", "must-not-leak")
    env = _acp_passthrough_env()
    assert env.get("CHARON_GATEWAY_TOKEN") == "gw-bearer-xyz"
    assert "SECRET_AWS" not in env
    assert "RANDOM_TOKEN" not in env


def test_renderer_path_does_not_force_forward_gateway_token(monkeypatch):
    # Mirrors test_agent_launch_pins_vid_at_the_seam_and_excludes_keys: the
    # renderer / per-run-proxy path (include_keys=False) owns its own credential,
    # so the standing gateway token must NOT bleed into it even when set.
    monkeypatch.setenv("CHARON_GATEWAY_TOKEN", "gw-bearer-xyz")
    launch = render("opencode acp", "http://127.0.0.1:9999", TIER_VID)
    assert "CHARON_GATEWAY_TOKEN" not in launch.passthrough_env


def test_tier_routes_through_gateway_failover_no_engine_selection():
    # The free provider 429s; the paid provider serves. The engine does NO
    # selection — it inherits the gateway's free-first failover.
    free, free_base = _up(status=429)
    paid, paid_base = _up(status=200, return_model="paid-up")
    try:
        registry = _registry(free_base, paid_base)
        _, pools, _ = _build_routes_and_pools(
            registry, {TIER_VID: ["paid-model", "free-model"]}, {})
        gw = GatewayProxyServer(pools={TIER_VID: pools[TIER_VID]}, model_ids=[TIER_VID])
        gw.serve_in_thread()
        try:
            # The agent (stood in by a tiny HTTP client) requests the TIER VID.
            launch = render("opencode acp", gw.url, TIER_VID)
            status, body = _req(gw.url + "/v1/chat/completions",
                                {"model": launch.requested_model})
            assert status == 200 and body["choices"][0]["message"]["content"] == "ok"
            # Free tried FIRST (free-first); paid captured the retry — each got ITS
            # OWN upstream id (R10b). This is the gateway's failover, not the engine.
            assert free.received == ["free-up"]
            assert paid.received == ["paid-up"]
            # B4: the re-homed failover note carries served + skipped provider list.
            note = api._tier_failover_note(gw.status_snapshot(), TIER_VID)
            assert free_base.split("//")[1] in note      # the skipped free provider
            assert paid_base.split("//")[1] in note      # the served paid provider
        finally:
            gw.shutdown()
    finally:
        free.shutdown()
        paid.shutdown()


def test_whole_tier_exhausted_surfaces_skipped_and_terminal_error():
    # Both providers 429 → whole chain exhausted: the gateway synthesizes a terminal
    # "all providers exhausted" 503 (the agent surfaces "exhausted" →
    # OutcomeStatus.EXHAUSTED in acp.py), and the re-homed note still lists the
    # skipped provider (ADR-0014 B4).
    a, ba = _up(status=429)
    b, bb = _up(status=429)
    try:
        registry = {"m-a": {"upstream_base": ba, "free": True, "cost_rank": 0},
                    "m-b": {"upstream_base": bb, "free": False, "cost_rank": 1}}
        _, pools, _ = _build_routes_and_pools(registry, {TIER_VID: ["m-a", "m-b"]}, {})
        gw = GatewayProxyServer(pools={TIER_VID: pools[TIER_VID]}, model_ids=[TIER_VID])
        gw.serve_in_thread()
        try:
            status, body = _req(gw.url + "/v1/chat/completions", {"model": TIER_VID})
            assert status == 503                          # synthesized terminal
            assert body["error"]["type"] == "all_providers_exhausted"
            note = api._tier_failover_note(gw.status_snapshot(), TIER_VID)
            assert ba.split("//")[1] in note              # the skipped first provider
        finally:
            gw.shutdown()
    finally:
        a.shutdown()
        b.shutdown()


def test_dry_tier_note_is_empty():
    # No traffic → no served/skipped providers → no note (the dry-pool exhausted
    # contract is carried by run_task's {status:"exhausted"} early-return, B4).
    gw = GatewayProxyServer(pools={TIER_VID: []}, model_ids=[TIER_VID])
    gw.serve_in_thread()
    try:
        assert api._tier_failover_note(gw.status_snapshot(), TIER_VID) == ""
    finally:
        gw.shutdown()
