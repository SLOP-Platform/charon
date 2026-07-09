"""SR-6 Phase-1: Anthropic prompt-cache enrichment (translate.enrich_anthropic_cache).

Covers breakpoint placement, the token-minimum gate, idempotency / the 4-breakpoint
cap, byte-identical prefix across turns, and strict no-op / no-mutation guarantees.
"""
from __future__ import annotations

import copy
import json

from charon import translate

# A system prompt comfortably over the ~2048-token (≈8192-char) cacheable minimum.
_BIG_SYSTEM = "You are a meticulous coding assistant. " * 400  # ≈ 15600 chars
assert len(_BIG_SYSTEM) // 4 >= translate.MIN_CACHE_TOKENS

_EPHEMERAL = {"type": "ephemeral"}


def _base_body(system, tools=None, user="hello"):
    body = {
        "model": "claude-x",
        "messages": [{"role": "user", "content": user}],
    }
    if system is not None:
        body["system"] = system
    if tools is not None:
        body["tools"] = tools
    return body


def test_breakpoint_on_last_system_block() -> None:
    body = _base_body(system=[
        {"type": "text", "text": _BIG_SYSTEM},
        {"type": "text", "text": _BIG_SYSTEM + " part two"},
    ])
    out = translate.enrich_anthropic_cache(body)
    assert out is not body  # new dict on enrichment
    assert out["system"][-1]["cache_control"] == _EPHEMERAL
    # exactly ONE breakpoint across the whole prefix
    n = sum("cache_control" in b for b in out["system"])
    n += sum("cache_control" in t for t in out.get("tools", []))
    assert n == 1
    # earlier block untouched
    assert "cache_control" not in out["system"][0]


def test_string_system_is_promoted_and_marked() -> None:
    body = _base_body(system=_BIG_SYSTEM)
    out = translate.enrich_anthropic_cache(body)
    assert isinstance(out["system"], list)
    assert out["system"][0]["type"] == "text"
    assert out["system"][0]["text"] == _BIG_SYSTEM
    assert out["system"][0]["cache_control"] == _EPHEMERAL


def test_breakpoint_on_last_tool_when_no_system() -> None:
    tools = [
        {"name": "a", "description": "x" * 4000, "input_schema": {}},
        {"name": "b", "description": "y" * 5000, "input_schema": {}},
    ]
    body = _base_body(system=None, tools=tools)
    out = translate.enrich_anthropic_cache(body)
    assert out["tools"][-1]["cache_control"] == _EPHEMERAL
    assert "cache_control" not in out["tools"][0]
    assert "system" not in out


def test_system_marked_even_when_tools_present() -> None:
    # A marker on the last system block caches tools+system together, so the tool
    # gets NO separate breakpoint.
    tools = [{"name": "a", "description": "d", "input_schema": {}}]
    body = _base_body(system=[{"type": "text", "text": _BIG_SYSTEM}], tools=tools)
    out = translate.enrich_anthropic_cache(body)
    assert out["system"][-1]["cache_control"] == _EPHEMERAL
    assert "cache_control" not in out["tools"][0]


def test_skip_under_token_min() -> None:
    body = _base_body(system=[{"type": "text", "text": "short prompt"}])
    out = translate.enrich_anthropic_cache(body)
    assert out is body  # strict no-op (identity)
    assert "cache_control" not in out["system"][0]


def test_idempotent_when_cache_control_already_present() -> None:
    body = _base_body(system=[
        {"type": "text", "text": _BIG_SYSTEM, "cache_control": _EPHEMERAL},
        {"type": "text", "text": _BIG_SYSTEM},
    ])
    out = translate.enrich_anthropic_cache(body)
    assert out is body  # never a 2nd breakpoint, never exceeds Anthropic's 4
    n = sum("cache_control" in b for b in out["system"])
    assert n == 1


def test_idempotent_when_existing_breakpoint_on_tool() -> None:
    tools = [{"name": "a", "description": "x" * 9000, "input_schema": {},
              "cache_control": _EPHEMERAL}]
    body = _base_body(system=None, tools=tools)
    out = translate.enrich_anthropic_cache(body)
    assert out is body


def test_prefix_byte_identical_across_turns() -> None:
    system = [{"type": "text", "text": _BIG_SYSTEM}]
    tools = [{"name": "a", "description": "d", "input_schema": {}}]
    turn1 = translate.enrich_anthropic_cache(
        _base_body(system=copy.deepcopy(system), tools=copy.deepcopy(tools),
                   user="first user turn"))
    turn2 = translate.enrich_anthropic_cache(
        _base_body(system=copy.deepcopy(system), tools=copy.deepcopy(tools),
                   user="a completely different, later user turn"))
    # cached prefix (tools + system) is byte-identical; only the volatile tail differs
    assert json.dumps(turn1["system"]) == json.dumps(turn2["system"])
    assert json.dumps(turn1["tools"]) == json.dumps(turn2["tools"])
    assert turn1["messages"] != turn2["messages"]


def test_not_anthropic_shaped_passthrough() -> None:
    # No system and no tools → nothing worth caching.
    body = {"model": "m", "messages": [{"role": "user", "content": "hi"}]}
    assert translate.enrich_anthropic_cache(body) is body
    # No messages at all.
    body2 = {"model": "m", "system": _BIG_SYSTEM}
    assert translate.enrich_anthropic_cache(body2) is body2


def test_non_dict_passthrough() -> None:
    assert translate.enrich_anthropic_cache(None) is None  # type: ignore[arg-type]
    assert translate.enrich_anthropic_cache("x") == "x"  # type: ignore[arg-type]


def test_input_not_mutated() -> None:
    body = _base_body(system=[{"type": "text", "text": _BIG_SYSTEM}])
    snapshot = copy.deepcopy(body)
    translate.enrich_anthropic_cache(body)
    assert body == snapshot  # original untouched (pure function)
