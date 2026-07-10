"""Unit tests for the response-shape adapter layer (ADR §8, T1)."""
from __future__ import annotations

from charon.response_adapters import (
    IDENTITY,
    ClineAdapter,
    IdentityAdapter,
    ResponseAdapter,
    get_adapter,
)

_CANONICAL = {
    "id": "cmpl-1",
    "object": "chat.completion",
    "model": "glm-5.2",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"},
                 "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
}


def test_cline_unwraps_wrapped_nonstream_body() -> None:
    wrapped = {"data": _CANONICAL, "success": True}
    out = ClineAdapter().normalize_response(wrapped)
    assert out is _CANONICAL  # inner object, unchanged
    assert "choices" in out and "usage" in out


def test_cline_response_idempotent_on_canonical() -> None:
    out = ClineAdapter().normalize_response(_CANONICAL)
    assert out is _CANONICAL  # already-canonical → passthrough (idempotent)


def test_cline_response_guards_are_total_passthrough() -> None:
    a = ClineAdapter()
    # data not a dict, no inner choices, and a bare canonical body all pass through.
    for raw in ({"data": "not-a-dict", "success": True},
                {"data": {}, "success": True},
                {"data": {"foo": 1}, "success": True},
                {"success": True},
                {}):
        assert a.normalize_response(raw) is raw  # never raises, never mutates


def test_cline_error_unwrap_and_idempotent() -> None:
    a = ClineAdapter()
    wrapped = {"data": {"error": {"message": "boom", "type": "x"}}, "success": False}
    assert a.normalize_error(wrapped) == {"error": {"message": "boom", "type": "x"}}
    canonical = {"error": {"message": "boom"}}
    assert a.normalize_error(canonical) is canonical  # idempotent
    assert a.normalize_error({"data": "x"}) == {"data": "x"}  # no inner error → passthrough


def test_cline_stream_chunk_is_passthrough() -> None:
    chunk = {"id": "c", "object": "chat.completion.chunk", "choices": []}
    assert ClineAdapter().normalize_stream_chunk(chunk) is chunk


def test_identity_returns_input_unchanged_all_methods() -> None:
    ident = IdentityAdapter()
    obj = {"anything": 1}
    assert ident.normalize_response(obj) is obj
    assert ident.normalize_stream_chunk(obj) is obj
    assert ident.normalize_error(obj) is obj
    # the module singleton behaves identically
    assert IDENTITY.normalize_response(obj) is obj


def test_get_adapter_registry() -> None:
    assert get_adapter(None) is IDENTITY
    assert get_adapter("") is IDENTITY
    assert get_adapter("unknown") is IDENTITY
    assert isinstance(get_adapter("cline"), ClineAdapter)


def test_adapters_satisfy_protocol() -> None:
    assert isinstance(IDENTITY, ResponseAdapter)
    assert isinstance(ClineAdapter(), ResponseAdapter)
