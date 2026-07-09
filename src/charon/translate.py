"""Anthropic-wire request enrichment (SR-6 Phase-1).

Pure, stdlib-only helpers that enrich an **already-Anthropic** request body with a
single prompt-cache breakpoint so a long, stable ``tools``+``system`` prefix is
billed at the cache-read (not full-input) price on every turn after the first.

This is an *enrichment* pass, not a format rewrite: it never converts between the
OpenAI and Anthropic wire formats (that risky, bidirectional surface — request +
response + SSE stream translation — is deliberately deferred to SR-6 Phase-2). It
only ever adds at most one ``cache_control`` key to a body that is already shaped
for an Anthropic upstream, and it is a strict no-op for every other input.

The single public entry point is :func:`enrich_anthropic_cache`.
"""
from __future__ import annotations

import copy
import json

# Conservative cacheable-prefix minimum. Anthropic's minimum cacheable prefix is
# 2048 tokens on Sonnet/Haiku-3.5 and 4096 on Opus/Haiku; use the conservative
# 2048 floor so we never add a write premium on a prefix too short to ever cache.
MIN_CACHE_TOKENS = 2048

# Reuse the char/4 token heuristic used by ``request_inspector`` (cheap, stdlib,
# no tokenizer dependency) — good enough to gate the "is this prefix worth
# caching?" decision.
_CHARS_PER_TOKEN = 4

_CACHE_CONTROL = {"type": "ephemeral"}


def _has_cache_control(body: dict) -> bool:
    """True if the client already placed ANY ``cache_control`` on the cacheable
    prefix (a ``system`` block or a ``tools`` def). If so we do nothing — never a
    second breakpoint, never exceed Anthropic's 4-breakpoint cap (idempotent)."""
    system = body.get("system")
    if isinstance(system, list):
        for block in system:
            if isinstance(block, dict) and "cache_control" in block:
                return True
    tools = body.get("tools")
    if isinstance(tools, list):
        for tool in tools:
            if isinstance(tool, dict) and "cache_control" in tool:
                return True
    return False


def _prefix_chars(body: dict) -> int:
    """Serialized-character size of the stable prefix (``tools`` + ``system``),
    which renders before any breakpoint we place. A char/4 proxy for prefix
    tokens — deliberately counts the JSON we would actually cache."""
    total = 0
    system = body.get("system")
    if isinstance(system, str):
        total += len(system)
    elif isinstance(system, list):
        total += len(json.dumps(system, ensure_ascii=False))
    tools = body.get("tools")
    if isinstance(tools, list) and tools:
        total += len(json.dumps(tools, ensure_ascii=False))
    return total


def _is_anthropic_shaped(body: dict) -> bool:
    """A minimally Anthropic-shaped body: a ``messages`` list plus at least one
    cacheable-prefix element (``system`` or a non-empty ``tools`` list). Without a
    prefix element there is nothing worth a breakpoint, so we treat it as not
    enrichable and pass it through untouched."""
    if not isinstance(body.get("messages"), list):
        return False
    system = body.get("system")
    if isinstance(system, str) and system:
        return True
    if isinstance(system, list) and system:
        return True
    tools = body.get("tools")
    return isinstance(tools, list) and bool(tools)


def enrich_anthropic_cache(body: dict) -> dict:
    """Inject exactly ONE ``cache_control:{"type":"ephemeral"}`` breakpoint at the
    end of the stable prefix of an Anthropic-wire request body.

    The breakpoint goes on the **last ``system`` block** (which caches the whole
    ``tools``+``system`` prefix, since both render before it) or, when there is no
    ``system``, on the **last tool definition**. Everything volatile (the latest
    user turn, per-request ids, timestamps) stays in ``messages`` *after* the
    breakpoint, so the cached prefix is byte-identical turn-to-turn as long as the
    client sends a stable system/tools block.

    Returns a NEW dict when it enriches; returns the input object unchanged (same
    identity) when it is a strict no-op. No-op when the body is not Anthropic-
    shaped, its stable prefix is under :data:`MIN_CACHE_TOKENS`, or it already
    carries a ``cache_control`` (idempotent)."""
    if not isinstance(body, dict):
        return body
    if not _is_anthropic_shaped(body):
        return body
    if _has_cache_control(body):
        return body
    if _prefix_chars(body) // _CHARS_PER_TOKEN < MIN_CACHE_TOKENS:
        return body

    new = dict(body)
    system = body.get("system")
    if isinstance(system, str):
        # Promote a plain-string system prompt to the block form so a breakpoint
        # can attach — the only shape change we make, and it is semantically
        # identical to the string form for an Anthropic upstream.
        new["system"] = [{
            "type": "text",
            "text": system,
            "cache_control": dict(_CACHE_CONTROL),
        }]
        return new
    if isinstance(system, list) and system:
        blocks = copy.deepcopy(system)
        last = blocks[-1]
        if isinstance(last, str):
            blocks[-1] = {
                "type": "text",
                "text": last,
                "cache_control": dict(_CACHE_CONTROL),
            }
        elif isinstance(last, dict):
            last["cache_control"] = dict(_CACHE_CONTROL)
        else:
            return body  # unrecognized block shape — leave untouched
        new["system"] = blocks
        return new

    # No system → breakpoint on the last tool definition.
    tools = body.get("tools")
    if isinstance(tools, list) and tools and isinstance(tools[-1], dict):
        new_tools = copy.deepcopy(tools)
        new_tools[-1]["cache_control"] = dict(_CACHE_CONTROL)
        new["tools"] = new_tools
        return new

    return body
