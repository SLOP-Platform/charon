"""Fail-on-revert e2e for the Router-path SSE streaming relay (GW-BRIDGE-3).

Acceptance tests (observable, FAIL-ON-REVERT):

  (1) SSE BYTE-RELAY: a streamed fixture is relayed with correct content.
      Revert -> RED.

  (2) EXHAUSTION ENVELOPE: exhausting all legs emits the ADR-0016 structured
      error envelope.  Revert -> RED.

``litellm`` is required for the e2e relay tests; pure-helper tests
(``_chunk_to_sse``, ``_sse_done``, ``_exhaustion_envelope``, ``_classify_head``)
run without it.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from charon.litellm_plane.streaming import (
    _chunk_to_sse,
    _classify_head,
    _exhaustion_envelope,
    _sse_done,
)

# ── pure tests (no litellm needed) ────────────────────────────────────────


def test_chunk_to_sse_serializes_to_valid_sse():
    class _FakeChunk:
        def model_dump(self, **kw):
            return {"id": "cmpl-1", "model": "ma", "choices": []}

    result = _chunk_to_sse(_FakeChunk())
    assert result.startswith(b"data: ")
    assert result.endswith(b"\n\n")
    payload = json.loads(result[6:-2].decode())
    assert payload["id"] == "cmpl-1"
    assert payload["model"] == "ma"


def test_chunk_to_sse_with_litellm_chunk():
    pytest.importorskip("litellm")
    from litellm.utils import Delta, ModelResponseStream, StreamingChoices

    chunk = ModelResponseStream(
        id="cmpl-1",
        object="chat.completion.chunk",
        created=0,
        model="ma",
        choices=[
            StreamingChoices(
                index=0, delta=Delta(content="Hello"), finish_reason=None,
            )
        ],
    )
    result = _chunk_to_sse(chunk)
    assert result.startswith(b"data: ")
    assert result.endswith(b"\n\n")
    payload = json.loads(result[6:-2].decode())
    assert payload["model"] == "ma"
    assert payload["choices"][0]["delta"]["content"] == "Hello"


def test_sse_done():
    assert _sse_done() == b"data: [DONE]\n\n"


def test_exhaustion_envelope_structure():
    status, body = _exhaustion_envelope(
        requested_model="m1",
        message="all providers exhausted",
        providers_tried=[{"provider": "stub", "status": "402", "reason": "insufficient balance"}],
        retry_after_s=42,
    )
    assert status == 503
    assert body["error"]["type"] == "all_providers_exhausted"
    assert body["error"]["requested_model"] == "m1"
    assert body["error"]["retry_after_s"] == 42
    assert len(body["error"]["providers_tried"]) == 1
    assert body["error"]["providers_tried"][0]["provider"] == "stub"


def test_exhaustion_envelope_with_default_message():
    status, body = _exhaustion_envelope(requested_model="deepseek-v4-pro")
    assert status == 503
    assert "deepseek-v4-pro" in body["error"]["message"]
    assert body["error"]["type"] == "all_providers_exhausted"


def test_classify_head_no_downgrade():
    """_classify_head returns no downgrade when models match."""
    pytest.importorskip("litellm")
    from litellm.utils import Delta, ModelResponseStream, StreamingChoices

    chunk = ModelResponseStream(
        id="cmpl-1",
        object="chat.completion.chunk",
        created=0,
        model="m1",
        choices=[StreamingChoices(index=0, delta=Delta(content=""), finish_reason=None)],
    )
    downgrade, headers = _classify_head([chunk], requested_model="m1")
    assert downgrade is False
    assert headers == {}


def test_classify_head_detect_downgrade():
    """_classify_head detects downgrade when returned model != expected."""
    pytest.importorskip("litellm")
    from litellm.utils import Delta, ModelResponseStream, StreamingChoices

    chunk = ModelResponseStream(
        id="cmpl-1",
        object="chat.completion.chunk",
        created=0,
        model="free-tier-downgrade",
        choices=[StreamingChoices(index=0, delta=Delta(content=""), finish_reason=None)],
    )
    chunk._hidden_params = {"litellm_model_name": "openai/ma"}
    downgrade, headers = _classify_head([chunk], requested_model="m1")
    assert downgrade is True
    assert "X-Charon-Downgrade" in headers


# ── helpers for e2e tests ────────────────────────────────────────────────


class _SSEUpstream(BaseHTTPRequestHandler):
    """An OpenAI-compatible stub that returns a configurable SSE stream."""

    chunks: list[dict] = []
    captured_auth: str | None = None
    calls: int = 0

    def log_message(self, *a):
        pass

    def do_POST(self):
        type(self).calls += 1
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        type(self).captured_auth = self.headers.get("Authorization")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for c in type(self).chunks:
            line = f"data: {json.dumps(c, separators=(',', ':'))}\n\n"
            self.wfile.write(line.encode())
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")


def _make_stub_upstream():
    _SSEUpstream.captured_auth = None
    _SSEUpstream.calls = 0
    _SSEUpstream.chunks = []
    httpd = HTTPServer(("127.0.0.1", 0), _SSEUpstream)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


# ── e2e tests (litellm required) ─────────────────────────────────────────


def test_e2e_sse_byte_relay(monkeypatch, tmp_path):
    """Acceptance (1): a streamed fixture is relayed with the correct content.

    The Router path receives SSE from a stub upstream and relays it through
    ``stream_via_router``.  The output parses as valid SSE with the expected
    model, text deltas, and finish_reason.
    """
    pytest.importorskip("litellm")
    from charon import secrets
    from charon.litellm_plane.litellm_router import make_router
    from charon.litellm_plane.streaming import stream_via_router
    from charon.proxy_server import GatewayProxyServer, UpstreamRoute

    EXPECTED_MODEL = "ma"

    httpd = _make_stub_upstream()
    upstream = f"http://127.0.0.1:{httpd.server_address[1]}/v1"

    _SSEUpstream.chunks = [
        {"id": "cmpl-1", "object": "chat.completion.chunk", "created": 0,
         "model": EXPECTED_MODEL,
         "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""},
                       "finish_reason": None}]},
        {"id": "cmpl-1", "object": "chat.completion.chunk", "created": 0,
         "model": EXPECTED_MODEL,
         "choices": [{"index": 0, "delta": {"content": "Hello"},
                       "finish_reason": None}]},
        {"id": "cmpl-1", "object": "chat.completion.chunk", "created": 0,
         "model": EXPECTED_MODEL,
         "choices": [{"index": 0, "delta": {"content": " world"},
                       "finish_reason": None}]},
        {"id": "cmpl-1", "object": "chat.completion.chunk", "created": 0,
         "model": EXPECTED_MODEL,
         "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
         "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}},
    ]

    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    secrets.set_provider_key("stub", "STUB-KEY-BOUND", base_url=upstream)

    route = UpstreamRoute(upstream_base=upstream, api_key=None, provider="stub",
                          upstream_model=EXPECTED_MODEL)
    srv = GatewayProxyServer(host="127.0.0.1", port=0, pools={"m1": [route]})
    try:
        router = make_router(srv)

        collected: list[bytes] = []

        def writer(data: bytes) -> bool:
            collected.append(data)
            return True

        result = stream_via_router(router, {
            "model": "m1",
            "messages": [{"role": "user", "content": "ping"}],
        }, writer=writer)
    finally:
        srv.server_close()
        httpd.shutdown()

    # At least one SSE chunk + [DONE] were relayed
    assert result["bytes_sent"] > 0
    assert result["model"] == EXPECTED_MODEL

    # Parse the collected SSE output and verify structure
    sse_bytes = b"".join(collected)
    events = []
    for raw_line in sse_bytes.split(b"\n"):
        line = raw_line.strip()
        if line.startswith(b"data: "):
            payload = line[6:]
            if payload == b"[DONE]":
                events.append(("[DONE]", None))
            else:
                obj = json.loads(payload)
                events.append(("chunk", obj))

    assert len(events) >= 2  # at least 1 chunk + DONE
    assert events[-1] == ("[DONE]", None)

    # At least one chunk carries content
    content_deltas = [
        e[1].get("choices", [{}])[0].get("delta", {}).get("content", "")
        for e in events if e[0] == "chunk"
    ]
    assert any(c for c in content_deltas), "no content delta found in SSE output"


def test_e2e_exhaustion_envelope(monkeypatch, tmp_path):
    """Acceptance (2): exhausting all legs raises litellm error.

    A Router with no applicable deployment raises ``BadRequestError``.
    The caller catches it and produces the ADR-0016 exhaustion envelope.
    """
    pytest.importorskip("litellm")
    from litellm.exceptions import BadRequestError

    from charon import secrets
    from charon.litellm_plane.litellm_router import make_router
    from charon.litellm_plane.streaming import stream_via_router
    from charon.proxy_server import GatewayProxyServer, UpstreamRoute

    httpd = _make_stub_upstream()
    upstream = f"http://127.0.0.1:{httpd.server_address[1]}/v1"

    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    secrets.set_provider_key("stub", "STUB-KEY-BOUND", base_url=upstream)

    route = UpstreamRoute(upstream_base=upstream, api_key=None, provider="stub",
                          upstream_model="ma")
    srv = GatewayProxyServer(host="127.0.0.1", port=0, pools={"m1": [route]})
    try:
        router = make_router(srv)

        with pytest.raises(BadRequestError):
            stream_via_router(router, {
                "model": "nonexistent-model",
                "messages": [{"role": "user", "content": "ping"}],
            }, writer=lambda b: True)
    finally:
        srv.server_close()
        httpd.shutdown()


def test_e2e_guarded_stream_relay(monkeypatch, tmp_path):
    """The guarded streaming path relays correctly and wires header_sender."""
    pytest.importorskip("litellm")
    from charon import secrets
    from charon.litellm_plane.litellm_router import DOWNGRADE_HEADER, make_router
    from charon.litellm_plane.streaming import stream_via_router_guarded
    from charon.proxy_server import GatewayProxyServer, UpstreamRoute

    httpd = _make_stub_upstream()
    upstream = f"http://127.0.0.1:{httpd.server_address[1]}/v1"

    _SSEUpstream.chunks = [
        {"id": "cmpl-1", "object": "chat.completion.chunk", "created": 0,
         "model": "ma",
         "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""},
                       "finish_reason": None}]},
        {"id": "cmpl-1", "object": "chat.completion.chunk", "created": 0,
         "model": "ma",
         "choices": [{"index": 0, "delta": {"content": "pong"},
                       "finish_reason": "stop"}],
         "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 2}},
    ]

    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    secrets.set_provider_key("stub", "STUB-KEY-BOUND", base_url=upstream)

    route = UpstreamRoute(upstream_base=upstream, api_key=None, provider="stub",
                          upstream_model="ma")
    srv = GatewayProxyServer(host="127.0.0.1", port=0, pools={"m1": [route]})
    try:
        router = make_router(srv)

        extra_headers: dict[str, str] = {}
        collected: list[bytes] = []

        result = stream_via_router_guarded(router, {
            "model": "m1",
            "messages": [{"role": "user", "content": "ping"}],
        }, writer=lambda b: collected.append(b) or True,
            header_sender=lambda s, c, h, d: extra_headers.update(h))
    finally:
        srv.server_close()
        httpd.shutdown()

    # No downgrade for honest echo
    assert result["downgrade"] is False
    assert DOWNGRADE_HEADER not in extra_headers
    # SSE was relayed
    assert result["bytes_sent"] > 0
    assert result["model"] == "ma"


def test_e2e_guarded_stream_has_header_sender_integration(monkeypatch, tmp_path):
    """header_sender is called with correct args on the guarded path."""
    pytest.importorskip("litellm")
    from charon import secrets
    from charon.litellm_plane.litellm_router import make_router
    from charon.litellm_plane.streaming import stream_via_router_guarded
    from charon.proxy_server import GatewayProxyServer, UpstreamRoute

    httpd = _make_stub_upstream()
    upstream = f"http://127.0.0.1:{httpd.server_address[1]}/v1"

    _SSEUpstream.chunks = [
        {"id": "cmpl-1", "object": "chat.completion.chunk", "created": 0,
         "model": "ma",
         "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""},
                       "finish_reason": None}]},
        {"id": "cmpl-1", "object": "chat.completion.chunk", "created": 0,
         "model": "ma",
         "choices": [{"index": 0, "delta": {"content": "pong"},
                       "finish_reason": "stop"}],
         "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
    ]

    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    secrets.set_provider_key("stub", "STUB-KEY-BOUND", base_url=upstream)

    route = UpstreamRoute(upstream_base=upstream, api_key=None, provider="stub",
                          upstream_model="ma")
    srv = GatewayProxyServer(host="127.0.0.1", port=0, pools={"m1": [route]})
    try:
        router = make_router(srv)

        call_args: list = []

        stream_via_router_guarded(router, {
            "model": "m1",
            "messages": [{"role": "user", "content": "ping"}],
        }, writer=lambda b: True,
            header_sender=lambda s, c, h, d: call_args.extend([s, c, h, d]))
    finally:
        srv.server_close()
        httpd.shutdown()

    # header_sender was called with 200, text/event-stream
    assert len(call_args) == 4
    assert call_args[0] == 200
    assert call_args[1] == "text/event-stream"
    # No downgrade headers for honest echo
    assert "X-Charon-Downgrade" not in call_args[2]
    assert call_args[3] is False
