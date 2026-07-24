"""SSE streaming relay for the adopted ``litellm.Router`` path (GW-BRIDGE-3).

Re-hosts the streaming SSE byte-relay that the hand-rolled forwarder
(``forwarder.py``:837-927) provides onto the ``litellm.Router`` path —
additively, preserving the streaming-head downgrade detection
(ADOPT-MAP KEEP-list, forwarder.py:837) and the ADR-0016 exhaustion
envelope.

``litellm`` is imported lazily (inside functions that use it) so this
module imports cleanly with or without litellm installed — the pure-Python
helper functions (``_chunk_to_sse``, ``_sse_done``, ``_exhaustion_envelope``)
run and are testable regardless.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

_STREAM_HEAD_CAP = 65536
_STREAM_HEAD_MAX_CHUNKS = 128


def _chunk_to_sse(chunk: Any) -> bytes:
    """Serialize a litellm streaming chunk to an SSE ``data:`` line."""
    if hasattr(chunk, "model_dump"):
        d = chunk.model_dump(mode="json", exclude_none=True)
    else:
        d = dict(chunk)
    return b"data: " + json.dumps(d, separators=(",", ":")).encode() + b"\n\n"


def _sse_done() -> bytes:
    """The terminal ``[DONE]`` SSE event."""
    return b"data: [DONE]\n\n"


def _exhaustion_envelope(
    requested_model: str,
    message: str = "",
    providers_tried: list[dict] | None = None,
    retry_after_s: int = 30,
) -> tuple[int, dict]:
    """The ADR-0016 structured error envelope for terminal provider exhaustion.

    Returns ``(status, body_dict)``.  The caller sends this as the SSE
    error response (503).
    """
    body = {
        "error": {
            "message": message or f"no capable provider could serve model {requested_model!r}",
            "type": "all_providers_exhausted",
            "requested_model": requested_model,
            "no_provider_reason": None,
            "retry_after_s": retry_after_s,
            "providers_tried": providers_tried or [],
        },
    }
    return (503, body)


def _raw_stream(
    router: Any,
    body: dict,
    *,
    timeout: float = 180.0,
) -> Any:
    """Issue ONE ``Router.completion(stream=True)`` and return the stream iterator.

    Raises ``litellm.exceptions.APIError`` (or subclass) when no deployment
    can serve — the caller should catch this and produce the ADR-0016
    exhaustion envelope.
    """
    model = body.get("model")
    messages = body.get("messages") or []
    passthrough = {
        k: body[k]
        for k in (
            "temperature", "top_p", "max_tokens", "tools", "tool_choice",
            "stop", "response_format",
        ) if k in body
    }
    return router.completion(
        model=model, messages=messages, stream=True,
        stream_options={"include_usage": True}, timeout=timeout, **passthrough,
    )


def _relay_stream(
    stream: Any,
    *,
    writer: Callable[[bytes], bool],
    collected_model: str = "",
) -> dict:
    """Iterate a litellm streaming iterable, relaying each chunk as SSE.

    *writer* receives each SSE ``data:`` event as bytes and returns
    ``True`` to continue or ``False`` to stop (client disconnect).

    Returns ``{model, usage, bytes_sent}``.
    """
    usage = None
    bytes_sent = 0
    for chunk in stream:
        if chunk is None:
            continue
        sse = _chunk_to_sse(chunk)
        if not writer(sse):
            break
        bytes_sent += len(sse)
        if not collected_model:
            collected_model = getattr(chunk, "model", "") or ""
        u = getattr(chunk, "usage", None)
        if u is not None:
            usage = u
    done = _sse_done()
    writer(done)
    bytes_sent += len(done)
    return {"model": collected_model, "usage": usage, "bytes_sent": bytes_sent}


def _classify_head(
    head: list[Any],
    requested_model: str,
    *,
    router: Any = None,
    observer: Any = None,
) -> tuple[bool, dict[str, str]]:
    """Classify the buffered stream head for silent downgrade.

    Returns ``(is_downgrade, extra_headers)``.  When *router* is provided
    the NATIVE upstream model is recovered via ``_selected_upstream_model``.
    """
    from charon.litellm_plane.litellm_router import (
        _DOWNGRADE_HEADER_VALUE,
        DOWNGRADE_HEADER,
        _selected_upstream_model,
    )
    from charon.proxy import GatewayProxy

    head_model = ""
    for chunk in head:
        m = getattr(chunk, "model", "") or ""
        if not head_model and m:
            head_model = m

    expected = None
    if router and head:
        expected = _selected_upstream_model(router, head[0], fallback=head_model or None)

    obs = (observer or GatewayProxy()).classify(
        requested_model=requested_model,
        status=200,
        headers=None,
        body={"model": head_model or ""},
        expected_model=expected,
    )
    downgrade = bool(obs.pseudo_success)
    extra_headers: dict[str, str] = {}
    if downgrade:
        extra_headers[DOWNGRADE_HEADER] = _DOWNGRADE_HEADER_VALUE
    return (downgrade, extra_headers)


def stream_via_router(
    router: Any,
    body: dict,
    *,
    writer: Callable[[bytes], bool],
    timeout: float = 180.0,
) -> dict:
    """Serve ONE streaming request through the Router and relay SSE chunks.

    Wraps :func:`_raw_stream` with the SSE relay loop.  Returns
    ``{model, usage, bytes_sent}``.

    Raises ``litellm.exceptions.APIError`` when no deployment can serve.
    The caller should catch that and emit the ADR-0016 exhaustion envelope.
    """
    stream = _raw_stream(router, body, timeout=timeout)
    return _relay_stream(stream, writer=writer)


def stream_via_router_guarded(
    router: Any,
    body: dict,
    *,
    writer: Callable[[bytes], bool],
    header_sender: Callable[[int, str, dict[str, str], bool], None] | None = None,
    observer: Any = None,
    timeout: float = 180.0,
) -> dict:
    """Stream through the Router with SR-1/SR-2 silent-downgrade guard.

    Buffers the head of the stream until ``model`` is seen (or
    ``_STREAM_HEAD_CAP``), classifies for downgrade using the canonical
    ``proxy.GatewayProxy.classify``, then commits headers and relays
    the rest.

    When *header_sender* is provided, it is called with
    ``(status, content_type, headers_dict, is_downgrade)`` before the
    first SSE byte is written — the caller can emit HTTP headers,
    ``X-Charon-Downgrade``, etc.

    Returns ``{model, usage, bytes_sent, downgrade}`` where *downgrade*
    is ``True`` when the model served differs from the model litellm sent.
    """
    stream = _raw_stream(router, body, timeout=timeout)

    # ---- buffer head until model seen or cap ----
    head: list[Any] = []
    for chunk in stream:
        if chunk is None:
            continue
        head.append(chunk)
        if getattr(chunk, "model", ""):
            break
        if len(head) >= _STREAM_HEAD_MAX_CHUNKS:
            break

    # ---- classify for downgrade ----
    downgrade, extra_headers = _classify_head(
        head, body.get("model", ""), router=router, observer=observer,
    )

    # ---- send headers (if sender wired) then relay buffered head + rest ----
    if header_sender:
        header_sender(200, "text/event-stream", extra_headers, downgrade)

    head_model = getattr(head[0], "model", "") if head else ""
    bytes_sent = 0
    for chunk in head:
        sse = _chunk_to_sse(chunk)
        if not writer(sse):
            return {"model": head_model, "usage": None,
                    "bytes_sent": bytes_sent, "downgrade": downgrade}
        bytes_sent += len(sse)

    result = _relay_stream(stream, writer=writer, collected_model=head_model)
    result["downgrade"] = downgrade
    result["bytes_sent"] = bytes_sent + result.get("bytes_sent", 0)
    return result
