"""BILLING-EST-COST-FIX — the money path must record a provider's real $0, never
the phantom ``est_cost`` floor.

Regression for the prod ``spend.json`` inflation to the fictional ~$223.28: at both
record sites (``forwarder.py`` non-stream + stream) the old code did
``record(cost if cost > 0 else est_cost)``, so EVERY free/flat completion — which
always reports ``cost==0`` — billed the fabricated pre-flight floor
(``request_bytes/4 · $1.5e-6``) instead of $0.

These tests drive ``forward_with_failover`` end-to-end against a real mock upstream
and assert the CLIENT-OBSERVABLE metering outcome (what the spend limiter records),
not an internal detail. ``test_flat_provider_zero_cost_not_billed_est_floor`` is the
FAIL-ON-REVERT guard: RED with the old floor-substitution, GREEN only with the fix.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.request
from pathlib import Path

from charon.proxy_server import GatewayProxyServer, UpstreamRoute
from charon.response_normalizer import NormalizeMode, ResponseNormalizer
from charon.spend_limits import SpendLimiter
from charon.types import SpendDecision


class _Prog(http.server.BaseHTTPRequestHandler):
    """Mock upstream: 200 with a real ``cost==0`` usage block, streamed or not."""

    def log_message(self, *a) -> None:  # silence test noise
        pass

    def do_POST(self) -> None:
        srv = self.server  # type: ignore[assignment]
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        payload = json.dumps({
            "model": srv.return_model,                       # type: ignore[attr-defined]
            "choices": [{"message": {"content": srv.content}}],  # type: ignore[attr-defined]
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


def _up(return_model="v", content="ok"):  # untyped body (matches sibling harnesses)
    srv = _Threaded(("127.0.0.1", 0), _Prog)
    srv.return_model, srv.content = return_model, content  # type: ignore[attr-defined]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{srv.server_address[0]}:{srv.server_address[1]}"


class _RecordingLimiter(SpendLimiter):
    """Records every ``record`` amount and always allows — so a test asserts the
    exact billed figure without touching real spend.json state."""

    def __init__(self, state_dir: Path) -> None:
        super().__init__(monthly_limit_usd=0.0, state_dir=state_dir)
        self.recorded: list[float] = []

    def check(self, estimated_cost: float) -> SpendDecision:
        return SpendDecision(allowed=True, remaining=float("inf"), reason="")

    def record(self, cost: float) -> None:
        self.recorded.append(cost)


class _RecordingNormalizer(ResponseNormalizer):
    """Captures exactly what the post-hook is handed (must be message content, not
    the JSON envelope) while still applying the real STANDARDIZE_MD transform."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def normalize(self, content: str, mode: NormalizeMode) -> str:  # type: ignore[override]
        self.seen.append(content)
        return ResponseNormalizer.normalize(content, mode)


def _send(url: str, payload: dict) -> None:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    resp = urllib.request.urlopen(req, timeout=10)
    resp.read()
    resp.close()


def _bill_one(tmp_path: Path, pricing: dict, stream: bool) -> list[float]:
    """Drive one request end-to-end through ``forward_with_failover`` and return the
    amounts the spend limiter recorded."""
    up, base = _up()
    limiter = _RecordingLimiter(tmp_path)
    gw = GatewayProxyServer(
        pools={"v": [UpstreamRoute(base, "k")]},
        model_pricing=pricing,
        spend_limiter=limiter,
    )
    gw.serve_in_thread()
    try:
        # A non-trivial body → the est_tokens*1.5e-6 floor is strictly positive, so
        # recording 0.0 is unambiguously distinct from the old floor-substitution.
        _send(gw.url + "/v1/chat/completions",
              {"model": "v", "stream": stream,
               "messages": [{"role": "user", "content": "x" * 400}]})
    finally:
        gw.shutdown()
        up.shutdown()
    return limiter.recorded


def test_flat_provider_zero_cost_not_billed_est_floor(tmp_path: Path) -> None:
    """FAIL-ON-REVERT: a free/flat route reporting ``cost==0`` bills 0.0 on BOTH the
    non-stream and stream paths — never the ``est_cost`` floor.

    A ``free``-flagged model (cost_source ``free``) reports a real $0. The old
    ``cost if cost > 0 else est_cost`` billed the positive floor on every one of
    these — the phantom that produced the prod ~$223; the fix records 0.0. RED with
    the old logic, GREEN only with the fix, RED again if reverted.
    """
    for stream in (False, True):
        recorded = _bill_one(tmp_path, {"v": {"free": True}}, stream)
        assert recorded == [0.0], (
            f"stream={stream}: billed {recorded}, expected [0.0] "
            "(the est_cost floor must NOT be recorded on a real $0)")


def test_unpriced_response_still_records_est_floor(tmp_path: Path) -> None:
    """Surgical boundary (and SR-7 preservation): a GENUINELY unpriced response —
    provider sent a usage block with no cost field and no stored pricing — keeps
    recording the positive ``est_cost`` floor so an uncosted call still advances the
    universal monthly cap. The fix must NOT zero this case out."""
    for stream in (False, True):
        recorded = _bill_one(tmp_path, {}, stream)
        assert len(recorded) == 1 and recorded[0] > 0.0, (
            f"stream={stream}: billed {recorded}, expected a single positive "
            "est_cost floor for a genuinely-unpriced response")


def test_response_normalizer_receives_content_not_whole_body(tmp_path: Path) -> None:
    """The post-hook is handed ``choices[0].message.content`` only — never the full
    JSON envelope — and the served body keeps its envelope intact.

    Guards the latent bug where the whole serialized body was fed to STANDARDIZE_MD,
    letting its regexes rewrite the JSON envelope (ids, punctuation, embedded fences).
    """
    norm = _RecordingNormalizer()
    up, base = _up(content="#Heading\nbody text")
    gw = GatewayProxyServer(
        pools={"v": [UpstreamRoute(base, "k")]},
        response_normalizer=norm,
        spend_limiter=_RecordingLimiter(tmp_path),
    )
    gw.serve_in_thread()
    try:
        req = urllib.request.Request(
            gw.url + "/v1/chat/completions",
            data=json.dumps({"model": "v", "messages": []}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        resp = urllib.request.urlopen(req, timeout=10)
        served = json.loads(resp.read())
        resp.close()
    finally:
        gw.shutdown()
        up.shutdown()

    # The normalizer saw ONLY the assistant content string, not the envelope.
    assert norm.seen == ["#Heading\nbody text"]
    assert all("choices" not in s and "usage" not in s for s in norm.seen)
    # The served envelope is intact JSON, with the content normalized in place
    # (STANDARDIZE_MD inserts the missing space after the heading marker).
    assert served["model"] == "v"
    assert served["usage"]["prompt_tokens"] == 3
    assert served["choices"][0]["message"]["content"].startswith("# Heading")
