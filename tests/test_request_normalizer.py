"""Tests for request_normalizer module.

Verifies that output-only fields (e.g. ``reasoning_content``) are stripped
from assistant messages before forwarding upstream, while normal bodies and
tool_calls are preserved.
"""
from __future__ import annotations

from charon.request_normalizer import normalize_messages


def test_strips_reasoning_content_from_assistant() -> None:
    """The bug this fixes: an assistant ``reasoning_content`` field echoed by
    one provider (DeepSeek-style) must not be forwarded to another provider
    that rejects it (Groq-style)."""
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello", "reasoning_content": "internal thoughts"},
        {"role": "user", "content": "bye"},
    ]
    result = normalize_messages(messages)
    assert result is not None
    assert result[1] == {"role": "assistant", "content": "hello"}
    assert "reasoning_content" not in result[1]


def test_strips_reasoning_field_from_assistant() -> None:
    """``reasoning`` (Anthropic-style) is also output-only."""
    messages = [
        {"role": "assistant", "content": "ok", "reasoning": "thought"},
    ]
    result = normalize_messages(messages)
    assert result is not None
    assert result[0] == {"role": "assistant", "content": "ok"}


def test_normal_body_is_untouched() -> None:
    """A body with no output-only fields is returned with the same shape."""
    messages = [
        {"role": "system", "content": "be helpful"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
        {"role": "user", "content": "what's up?"},
    ]
    result = normalize_messages(messages)
    assert result is not None
    assert result == messages


def test_tool_calls_preserved() -> None:
    """OpenAI-spec tool_calls on assistant messages must be preserved."""
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city":"SF"}'},
                }
            ],
        }
    ]
    result = normalize_messages(messages)
    assert result is not None
    assert result[0] == messages[0]


def test_tool_calls_preserved_with_reasoning_stripped() -> None:
    """A reasoning_content field is stripped while adjacent tool_calls survive."""
    messages = [
        {
            "role": "assistant",
            "content": None,
            "reasoning_content": "thinking about the weather",
            "tool_calls": [
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": "{}"},
                }
            ],
        }
    ]
    result = normalize_messages(messages)
    assert result is not None
    assert "reasoning_content" not in result[0]
    assert result[0]["tool_calls"] == messages[0]["tool_calls"]


def test_user_messages_with_reasoning_content_untouched() -> None:
    """Non-assistant messages are never touched — only assistant echoes are
    output-only. A user message (unusual but possible) with
    ``reasoning_content`` is preserved verbatim."""
    messages = [
        {"role": "user", "content": "hello", "reasoning_content": "should NOT be stripped"},
    ]
    result = normalize_messages(messages)
    assert result is not None
    assert result[0] == messages[0]


def test_none_input_returns_none() -> None:
    assert normalize_messages(None) is None


def test_empty_list_returns_empty_list() -> None:
    assert normalize_messages([]) == []


def test_idempotent() -> None:
    """Stripping twice == stripping once."""
    messages = [
        {"role": "assistant", "content": "x", "reasoning_content": "y"},
    ]
    once = normalize_messages(messages)
    twice = normalize_messages(once)
    assert twice == once


def test_input_not_mutated() -> None:
    """The function must not mutate its input (defensive copy)."""
    messages = [
        {"role": "assistant", "content": "x", "reasoning_content": "y"},
    ]
    snapshot = [dict(m) for m in messages]
    normalize_messages(messages)
    assert messages == snapshot


def test_non_dict_messages_preserved() -> None:
    """Oddly-shaped entries (non-dict) are passed through without crashing."""
    messages = ["not-a-dict", None, {"role": "assistant", "content": "x", "reasoning_content": "y"}]  # type: ignore[list-item]
    result = normalize_messages(messages)
    assert result is not None
    assert result[0] == "not-a-dict"
    assert result[1] is None
    assert result[2] == {"role": "assistant", "content": "x"}
