"""Response extraction + pre-flight pricing helpers for the gateway proxy (seam B).

Module-level pure functions extracted verbatim from proxy_server.py: SSE/JSON
model+usage extraction and pre-flight cost estimation. proxy_server re-exports
_extract and _pre_flight_estimate for the unchanged public import surface.
"""
from __future__ import annotations

import json

from .proxy import _normalize_model_id


def _extract(raw: bytes, content_type: str) -> dict:
    """Pull a ``{model, usage}`` view out of an upstream response — JSON for a
    normal completion, or the SSE ``data:`` chunks for a streamed one (agents like
    OpenCode stream). Returns {} if nothing parseable."""
    text = raw.decode("utf-8", "replace")
    if "text/event-stream" in content_type or text.lstrip().startswith("data:"):
        model = ""
        usage = None
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload in ("", "[DONE]"):
                continue
            try:
                obj = json.loads(payload)
            except Exception:  # noqa: BLE001
                continue
            model = model or obj.get("model", "")
            if obj.get("usage"):
                usage = obj["usage"]  # final SSE chunk carries usage (include_usage)
        out: dict = {}
        if model:
            out["model"] = model
        if usage:
            out["usage"] = usage
        return out
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        return {}


def _pre_flight_estimate(model: str, est_tokens: int,
                         srv: GatewayProxyServer) -> float:
    """Compute the pre-flight spend estimate for ``model`` from its stored per-token
    pricing. Falls back to a nominal floor when pricing is unknown."""
    pricing = _pre_flight_pricing(model, srv)
    ci = pricing.get("cost_input")
    co = pricing.get("cost_output")
    if ci is not None and co is not None:
        rate = max(float(ci), float(co), 0.0000001)
        return est_tokens * rate
    return est_tokens * 0.0000015


def _pre_flight_pricing(model: str, srv: GatewayProxyServer) -> dict:
    """Resolve a model's pricing entry with the same normalization the proxy's
    ``_lookup_pricing`` uses — exact id first, then a normalized final-segment
    match — so a namespaced id (e.g. ``deepseek/deepseek-v4-pro``) doesn't silently
    fall through to the nominal floor (parity with the cost_usd path, SR-5b)."""
    exact = srv.model_pricing.get(model)
    if exact is not None:
        return exact
    cleaned = _normalize_model_id(model)
    for known_id, entry in srv.model_pricing.items():
        if _normalize_model_id(known_id) == cleaned:
            return entry
    return {}
