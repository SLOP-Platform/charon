"""Provider-response contract — kills the self-mirroring-mock blind spot.

Every wired ``ProviderPreset`` must yield an OpenAI-shaped CLIENT response
(top-level ``choices`` list + top-level ``usage`` dict) through the proxy.
Unlike ``tests/conftest.py``'s shared ``mock_upstream`` (which always emits the
canonical shape, so it can never challenge the product's shape assumption),
each case here drives a mock upstream that returns THAT preset's own declared
raw wire shape and asserts on the CLIENT-observable envelope — never on
content *inside* ``choices``.

A preset with no declared raw-shape fixture below fails the parametrization
LOUDLY (an ``AssertionError`` from the test body), not a silent skip — see
``_shape_fixture_for``. This is the Q4 mechanization from the test-gap audit
(``fleet/scratch/test-gap-audit.md``): "does the proxy speak OpenAI to the
client?" becomes a per-provider invariant a revert can't pass.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.error
import urllib.request
from collections.abc import Callable

import pytest

from charon import providers
from charon.proxy_server import GatewayProxyServer, UpstreamRoute


def _canonical_shape(model: str) -> dict:
    """The genuine wire shape of every currently-wired preset: they are all
    real OpenAI-compatible chat-completions APIs (that's the whole point of
    ``strip_v1``/``base_url`` in providers.py), so mocking this shape for them
    is representative, not a self-mirroring assumption."""
    return {
        "id": "chatcmpl-contract-1",
        "object": "chat.completion",
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }


def _cline_wrapped_shape(model: str) -> dict:
    """cline-pass's real non-stream envelope: the OpenAI-shaped body is
    nested under ``data`` alongside a ``success`` flag -- NOT itself
    OpenAI-shaped at the top level (fleet/ADR-UNIVERSAL-RESPONSE-ADAPTER.md).
    """
    return {"success": True, "data": _canonical_shape(model)}


# Explicit, hand-maintained registry of presets known to speak the plain
# OpenAI shape today (they are genuine OpenAI-compatible APIs; there is no
# response-adapter mechanism in the forwarder yet, so EVERY currently-wired
# preset is an identity passthrough). Deliberately NOT derived from
# `providers.PRESETS.keys()` -- a preset landing without an entry here must
# fail loudly (see `_shape_fixture_for`), not silently inherit one.
_OPENAI_SHAPE_PRESETS = frozenset({
    "anthropic", "opencode-zen", "opencode-go", "openrouter", "nanogpt", "zai",
    "deepseek", "chutes", "groq", "together", "mistral", "fireworks", "sambanova",
    "replicate", "xai", "cohere", "openai", "huggingface", "neuralwatt",
    "perplexity", "lmstudio", "jan", "ollama", "vllm", "local",
})

# cline-pass ships a non-OpenAI wrapper (ADR-UNIVERSAL-RESPONSE-ADAPTER.md) and
# is NOT yet a registered ProviderPreset -- that preset + the `adapter` field
# on ProviderPreset/UpstreamRoute land with the (separate) RESPONSE-ADAPTER-
# UNIVERSAL ticket. It's added to the parametrization by hand below and marked
# xfail(strict=False): today the forwarder has no adapter hook, so the wrapped
# body is relayed verbatim (no top-level `choices`) -- once the adapter lands
# and this test is updated to set `adapter="cline"`, it will simply xpass.
_CLINE_PRESET_NAME = "cline-pass"


def _shape_fixture_for(name: str) -> Callable[[str], dict]:
    if name == _CLINE_PRESET_NAME:
        return _cline_wrapped_shape
    if name in _OPENAI_SHAPE_PRESETS:
        return _canonical_shape
    raise AssertionError(
        f"provider preset {name!r} has no declared raw-shape fixture in "
        "tests/test_provider_response_contract.py -- a new preset (or a new "
        "adapter) must declare its known wire shape here so this contract "
        "test actually exercises it, instead of silently passing/skipping."
    )


def _make_upstream_handler(shape_fn: Callable[[str], dict]) -> type:
    class _Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a: object) -> None:
            pass

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            payload = json.dumps(shape_fn(body.get("model", "?"))).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return _Handler


class _Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _post(url: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


_PARAMS = [pytest.param(name, id=name) for name in sorted(providers.PRESETS.keys())] + [
    pytest.param(
        _CLINE_PRESET_NAME, id=_CLINE_PRESET_NAME,
        marks=pytest.mark.xfail(
            reason="cline non-stream envelope unwrapped by RESPONSE-ADAPTER-UNIVERSAL",
            strict=False,
        ),
    ),
]


@pytest.mark.parametrize("preset_name", _PARAMS)
def test_provider_response_has_top_level_choices_and_usage(preset_name: str) -> None:
    """The CLIENT must see top-level `choices` + `usage`, given THAT preset's
    own raw wire shape -- not a mock that mirrors the code's assumption."""
    shape_fn = _shape_fixture_for(preset_name)

    upstream = _Threaded(("127.0.0.1", 0), _make_upstream_handler(shape_fn))
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    up_host, up_port = upstream.server_address[0], upstream.server_address[1]
    if isinstance(up_host, bytes):
        up_host = up_host.decode()

    route_kwargs: dict = {
        "upstream_base": f"http://{up_host}:{up_port}",
        "provider": preset_name,
    }
    if preset_name == _CLINE_PRESET_NAME:
        # Not yet a field on UpstreamRoute -- raises TypeError until the
        # (separate) adapter ticket lands, caught by xfail(strict=False) above.
        route_kwargs["adapter"] = "cline"

    try:
        route = UpstreamRoute(**route_kwargs)
        proxy = GatewayProxyServer(routes={preset_name: route})
        proxy.serve_in_thread()
        try:
            status, body = _post(
                proxy.url + "/v1/chat/completions", {"model": preset_name})
            assert status == 200
            assert isinstance(body.get("choices"), list) and body["choices"], (
                f"{preset_name}: no top-level `choices` list in client response")
            assert isinstance(body.get("usage"), dict) and body["usage"], (
                f"{preset_name}: no top-level `usage` dict in client response")
        finally:
            proxy.shutdown()
    finally:
        upstream.shutdown()


def test_every_preset_has_a_declared_shape_fixture() -> None:
    """Fails loudly (rather than skip) if a preset ships with no entry in
    `_OPENAI_SHAPE_PRESETS` above -- the mechanism `_shape_fixture_for` relies
    on for every real (non-cline) parametrized case."""
    undeclared = set(providers.PRESETS.keys()) - _OPENAI_SHAPE_PRESETS
    assert not undeclared, (
        f"preset(s) {sorted(undeclared)} have no declared raw-shape fixture -- "
        "add them to _OPENAI_SHAPE_PRESETS (or a dedicated adapter case) in "
        "tests/test_provider_response_contract.py"
    )
