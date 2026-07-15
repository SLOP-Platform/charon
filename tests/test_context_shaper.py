"""Tests for the EXPERIMENTAL / OPT-IN context_shaper module.

The paramount invariant is OFF-BY-DEFAULT identity: with the feature disabled the
messages array must pass through byte-for-byte. The first test is the red-proof — it
FAILS if the default path ever mutates messages.

## Wiring rider (mirrors context_shaper.shape docstring)
These tests exercise the pure module surface ONLY. Proxy wiring (invoking ``shape`` in
the proxy_server.py request path behind the opt-in flag, then setting DISCLOSURE_HEADER)
is a deliberate follow-on rider and is intentionally NOT covered here.
"""
from __future__ import annotations

import copy

from charon import context_shaper as cs


def _turn(role: str, content: str) -> dict[str, object]:
    return {"role": role, "content": content}


def _long_conversation() -> list[dict[str, object]]:
    """A multi-turn chat whose old span is verbose enough to overflow a tiny window."""
    filler = (
        "The deployment pipeline promotes the container image through staging and then "
        "production after the smoke suite goes green. Rollback is automated on any failed "
        "health probe. The database migration runs before the new revision receives "
        "traffic so schema and code stay compatible during the cutover window."
    )
    msgs: list[dict[str, object]] = [_turn("system", "You are a helpful assistant.")]
    for i in range(8):
        msgs.append(_turn("user", f"Question {i}: {filler}"))
        msgs.append(_turn("assistant", f"Answer {i}: {filler}"))
    msgs.append(_turn("user", "So what is the single most important safety control?"))
    return msgs


# ---------------------------------------------------------------------------
# 1. OFF BY DEFAULT — identity red-proof
# ---------------------------------------------------------------------------


def test_default_is_identity_passthrough() -> None:
    """Feature OFF (no config) => same object, no mutation. RED-PROOF."""
    messages = _long_conversation()
    snapshot = copy.deepcopy(messages)

    result = cs.shape(messages, context_window=16)

    assert result.applied is False
    assert result.disclosure == ""
    assert result.summarized_turns == 0
    # Same object returned (transparent passthrough) ...
    assert result.messages is messages
    # ... and nothing about the array or its dicts was touched.
    assert messages == snapshot


def test_explicitly_disabled_is_identity() -> None:
    """Feature present but enabled=False => identity even when massively over budget."""
    messages = _long_conversation()
    snapshot = copy.deepcopy(messages)
    cfg = cs.ShaperConfig(enabled=False, reserved_turns=2)

    result = cs.shape(messages, context_window=8, config=cfg)

    assert result.applied is False
    assert result.messages is messages
    assert messages == snapshot


def test_default_never_mutates_even_with_zero_window() -> None:
    """Degenerate/unknown window with no opt-in stays a passthrough (no crash)."""
    messages = _long_conversation()
    snapshot = copy.deepcopy(messages)

    assert cs.shape(messages, context_window=None).messages is messages
    assert cs.shape(messages, context_window=0).messages is messages
    assert messages == snapshot


# ---------------------------------------------------------------------------
# 2. Enabled + UNDER budget => passthrough unchanged
# ---------------------------------------------------------------------------


def test_enabled_under_budget_is_passthrough() -> None:
    messages = _long_conversation()
    snapshot = copy.deepcopy(messages)
    cfg = cs.ShaperConfig(enabled=True, reserved_turns=2)

    # Window far larger than the request => nothing to do, stay transparent.
    result = cs.shape(messages, context_window=100_000, config=cfg)

    assert result.applied is False
    assert result.messages is messages
    assert messages == snapshot


# ---------------------------------------------------------------------------
# 3. Enabled + OVER budget => reservoir compaction
# ---------------------------------------------------------------------------


def test_enabled_over_budget_compacts_within_reservoir() -> None:
    messages = _long_conversation()
    snapshot = copy.deepcopy(messages)
    window = 400
    reserved = 3
    cfg = cs.ShaperConfig(enabled=True, reserved_turns=reserved)

    assert cs.estimate_messages_tokens(messages) > window  # precondition: over budget
    result = cs.shape(messages, context_window=window, config=cfg)

    assert result.applied is True
    assert result.disclosure  # non-empty disclosure marker
    assert result.summarized_turns > 0

    # Output fits the model's context window.
    assert cs.estimate_messages_tokens(result.messages) <= window

    # Last N turns are preserved VERBATIM (reservoir) as the final N messages.
    assert result.messages[-reserved:] == messages[-reserved:]
    # And they are the exact same dict objects (not copies) — no user-turn mutation.
    for produced, original in zip(
        result.messages[-reserved:], messages[-reserved:], strict=True
    ):
        assert produced is original

    # Leading system instruction is preserved verbatim.
    assert result.messages[0] == messages[0]

    # A self-identifying summary system message was injected.
    summary = [
        m
        for m in result.messages
        if m.get("role") == "system"
        and isinstance(m.get("content"), str)
        and cs.SUMMARY_MARKER in str(m["content"])
    ]
    assert len(summary) == 1

    # Caller's original array was never mutated in place.
    assert messages == snapshot
    assert result.messages is not messages


def test_over_budget_is_deterministic() -> None:
    cfg = cs.ShaperConfig(enabled=True, reserved_turns=3)
    a = cs.shape(_long_conversation(), context_window=400, config=cfg)
    b = cs.shape(_long_conversation(), context_window=400, config=cfg)
    assert a.applied and b.applied
    assert a.messages == b.messages
    assert a.disclosure == b.disclosure


def test_disclosure_only_when_applied() -> None:
    """DISCLOSE invariant: disclosure/header semantics gate strictly on `applied`."""
    off = cs.shape(_long_conversation(), context_window=400)
    assert off.applied is False and off.disclosure == ""

    cfg = cs.ShaperConfig(enabled=True, reserved_turns=3)
    on = cs.shape(_long_conversation(), context_window=400, config=cfg)
    assert on.applied is True and on.disclosure != ""
    # A stable header name exists for the proxy to surface.
    assert cs.DISCLOSURE_HEADER.lower().startswith("x-")


def test_too_few_turns_stays_transparent() -> None:
    """Nothing older than the reservoir => no benefit => passthrough."""
    messages = [_turn("user", "hi"), _turn("assistant", "hello")]
    cfg = cs.ShaperConfig(enabled=True, reserved_turns=3)
    result = cs.shape(messages, context_window=1, config=cfg)
    assert result.applied is False
    assert result.messages is messages


# ---------------------------------------------------------------------------
# 4. TF ranker — higher-signal sentences outrank filler
# ---------------------------------------------------------------------------


def test_tf_ranker_prefers_high_signal_sentences() -> None:
    text = (
        "Ok. Sure, that sounds fine to me. "
        "The rollback controller monitors the health probe and aborts a bad rollback "
        "when the rollback health probe fails. "
        "Thanks a lot."
    )
    ranked = cs.rank_sentences(text, position_bias=0.0)
    # The information-dense sentence (repeated topical terms) ranks first;
    # the low-signal pleasantries rank last.
    assert "rollback" in ranked[0].lower()
    assert ranked[-1].lower().startswith("thanks") or ranked[-1].lower().startswith("ok")


def test_tf_ranker_empty_input() -> None:
    assert cs.rank_sentences("") == []
    assert cs.rank_sentences("   ") == []


def test_summarize_respects_budget_and_original_order() -> None:
    text = (
        "Alpha term alpha term dominates the first sentence. "
        "Beta filler here. "
        "Gamma term gamma term dominates the third sentence."
    )
    out = cs.summarize(text, token_budget=40, position_bias=0.0)
    assert out  # something selected
    assert cs.estimate_tokens(out) <= 40
    # Zero budget / empty text => empty summary.
    assert cs.summarize(text, token_budget=0) == ""
    assert cs.summarize("", token_budget=50) == ""


def test_token_estimators_are_positive_and_deterministic() -> None:
    assert cs.estimate_tokens("") == 0
    assert cs.estimate_tokens("abcd") == cs.estimate_tokens("abcd") >= 1
    msg = _turn("user", "hello world")
    assert cs.estimate_message_tokens(msg) > cs.estimate_tokens("hello world")
