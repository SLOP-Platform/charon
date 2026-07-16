"""FORWARDER-RECONCILE (supersedes untracked feat/wire-tool-repair, af8d795) —
tool_repair.py was a written+tested but DEAD safety net (never wired into the
forwarder). CG-critical: tool-calling is fragile/fails for several model pools;
a malformed ``tool_calls[].function.arguments`` string (single-quoted
keys/values, trailing commas — common local/small-model output) must be
repaired on the REAL served-response path, not a parallel helper.

These tests drive ``forward_with_failover`` end-to-end against a real mock
upstream and assert the CLIENT-OBSERVABLE served body.
``test_malformed_tool_call_repaired_end_to_end`` is the FAIL-ON-REVERT guard:
GREEN only while forwarder.py calls ``_repair_tool_call_response`` on the
non-stream 200 path; reverting that one call site makes it RED (the served
``arguments`` stays invalid JSON).

The repair module is injected via the F29 ``modules=`` registry seam
(``modules={"tool_repair": ToolCallRepair()}``) — proxy_server's generic
new-spec loop sets ``srv.tool_repair`` from it, and the forwarder reads it via
``getattr(srv, "tool_repair", None)`` so an unconfigured server stays
byte-identical.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.request
from pathlib import Path

from charon.proxy_server import GatewayProxyServer, UpstreamRoute
from charon.spend_limits import SpendLimiter
from charon.tool_repair import ToolCallRepair
from charon.types import SpendDecision


class _MalformedToolCallUpstream(http.server.BaseHTTPRequestHandler):
    """Mock upstream: 200 with a malformed tool_calls[].function.arguments
    string — single-quoted keys/values + a trailing comma, the kind of
    near-miss-JSON several small/local model pools emit."""

    def log_message(self, *a) -> None:  # silence test noise
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        payload = json.dumps({
            "model": "v",
            "choices": [{"message": {
                "content": None,
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": "{'city': 'Paris', 'days': '3',}",
                    },
                }],
            }}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 5, "cost": 0.0},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _up():
    srv = _Threaded(("127.0.0.1", 0), _MalformedToolCallUpstream)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{srv.server_address[0]}:{srv.server_address[1]}"


class _RecordingLimiter(SpendLimiter):
    def __init__(self, state_dir: Path) -> None:
        super().__init__(monthly_limit_usd=0.0, state_dir=state_dir)

    def check(self, estimated_cost: float) -> SpendDecision:
        return SpendDecision(allowed=True, remaining=float("inf"), reason="")

    def record(self, cost: float) -> None:
        pass


_REQUEST_BODY = {
    "model": "v",
    "messages": [{"role": "user", "content": "weather in Paris?"}],
    "tools": [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "parameters": {
                "properties": {
                    "city": {"type": "string"},
                    "days": {"type": "integer"},
                },
            },
        },
    }],
}


def _drive(tmp_path: Path, *, wire_tool_repair: bool) -> dict:
    up, base = _up()
    kwargs = dict(
        pools={"v": [UpstreamRoute(base, "k")]},
        spend_limiter=_RecordingLimiter(tmp_path),
    )
    if wire_tool_repair:
        kwargs["modules"] = {"tool_repair": ToolCallRepair()}
    gw = GatewayProxyServer(**kwargs)
    gw.serve_in_thread()
    try:
        req = urllib.request.Request(
            gw.url + "/v1/chat/completions",
            data=json.dumps(_REQUEST_BODY).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        resp = urllib.request.urlopen(req, timeout=10)
        served = json.loads(resp.read())
        resp.close()
    finally:
        gw.shutdown()
        up.shutdown()
    # Top-level response contract: the client must observe an OpenAI-shaped
    # envelope -- a top-level `choices` list and `usage` dict -- not a foreign
    # wrapper. A mis-shaped body (e.g. cline's {"data": .., "success": true})
    # has neither and would fail HERE rather than pass unnoticed while the
    # in-`choices` assertions below drill blindly into a self-mirrored mock.
    assert isinstance(served.get("choices"), list) and served["choices"]
    assert isinstance(served.get("usage"), dict) and served["usage"]
    return served


def test_malformed_tool_call_repaired_end_to_end(tmp_path: Path) -> None:
    """FAIL-ON-REVERT: with tool_repair wired in, a malformed upstream
    tool_calls[].function.arguments string is repaired to valid JSON with the
    correct schema-coerced types before it reaches the client.

    If the forwarder's call to ``_repair_tool_call_response`` is reverted, the
    served ``arguments`` stays the raw malformed string and ``json.loads`` below
    raises — this test goes RED.
    """
    served = _drive(tmp_path, wire_tool_repair=True)
    tc = served["choices"][0]["message"]["tool_calls"][0]
    args = json.loads(tc["function"]["arguments"])  # raises if unrepaired
    assert args == {"city": "Paris", "days": 3}  # single quotes fixed, "3" -> int 3


def test_no_tool_repair_configured_leaves_malformed_arguments_untouched(
    tmp_path: Path,
) -> None:
    """Zero-behavior-change guard: when no tool_repair module is configured
    (the default for a directly-constructed GatewayProxyServer, matching
    response_normalizer/guardrails/etc.), the malformed body is relayed
    byte-for-byte — proves the wiring is guarded, not unconditional."""
    served = _drive(tmp_path, wire_tool_repair=False)
    tc = served["choices"][0]["message"]["tool_calls"][0]
    assert tc["function"]["arguments"] == "{'city': 'Paris', 'days': '3',}"


def test_well_formed_tool_call_unchanged_when_repair_wired(tmp_path: Path) -> None:
    """A response that is already well-formed passes through unchanged even with
    tool_repair wired in — the guard is a no-op on good responses, not a
    reformatter."""
    class _WellFormed(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a) -> None:
            pass

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            payload = json.dumps({
                "model": "v",
                "choices": [{"message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1", "type": "function",
                        "function": {"name": "get_weather",
                                     "arguments": '{"city": "Paris", "days": 3}'},
                    }],
                }}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 5, "cost": 0.0},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    up = _Threaded(("127.0.0.1", 0), _WellFormed)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    base = f"http://{str(up.server_address[0])}:{up.server_address[1]}"
    gw = GatewayProxyServer(
        pools={"v": [UpstreamRoute(base, "k")]},
        spend_limiter=_RecordingLimiter(tmp_path),
        modules={"tool_repair": ToolCallRepair()},
    )
    gw.serve_in_thread()
    try:
        req = urllib.request.Request(
            gw.url + "/v1/chat/completions",
            data=json.dumps(_REQUEST_BODY).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        resp = urllib.request.urlopen(req, timeout=10)
        served = json.loads(resp.read())
        resp.close()
    finally:
        gw.shutdown()
        up.shutdown()
    # Top-level response contract (see `_drive`): a foreign envelope with no
    # top-level `choices`/`usage` would fail here, not slip past the in-choices
    # assertion below.
    assert isinstance(served.get("choices"), list) and served["choices"]
    assert isinstance(served.get("usage"), dict) and served["usage"]
    tc = served["choices"][0]["message"]["tool_calls"][0]
    assert tc["function"]["arguments"] == '{"city": "Paris", "days": 3}'
