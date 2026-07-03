"""P1 — RequestInspector: lightweight pre-flight hints from chat messages."""
from __future__ import annotations

from charon.request_inspector import RequestInspector


def test_plain_text_no_images_no_tools():
    hints = RequestInspector.inspect([
        {"role": "user", "content": "hello world"},
        {"role": "assistant", "content": "hi there"},
    ])
    assert hints.has_images is False
    assert hints.has_tools is False
    assert hints.estimated_tokens == (11 + 8) // 4
    assert hints.preferred_context_window is None


def test_detects_image_url_in_multipart_content():
    hints = RequestInspector.inspect([
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "describe this image"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ],
        },
    ])
    assert hints.has_images is True
    assert hints.has_tools is False


def test_detects_tool_calls_in_assistant_message():
    hints = RequestInspector.inspect([
        {"role": "user", "content": "what is the weather?"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "London"}'},
                }
            ],
        },
    ])
    assert hints.has_tools is True


def test_detects_tool_role_message():
    hints = RequestInspector.inspect([
        {"role": "tool", "tool_call_id": "call_1", "content": "15°C, cloudy"},
    ])
    assert hints.has_tools is True


def test_estimated_tokens_char_div_4():
    text = "x" * 100
    hints = RequestInspector.inspect([
        {"role": "user", "content": text},
    ])
    assert hints.estimated_tokens == 25
    assert hints.has_images is False
    assert hints.has_tools is False


def test_multipart_text_token_estimate():
    hints = RequestInspector.inspect([
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "first part"},
                {"type": "text", "text": "second part"},
            ],
        },
    ])
    total_chars = len("first part") + len("second part")
    assert hints.estimated_tokens == total_chars // 4


def test_empty_messages_returns_defaults():
    hints = RequestInspector.inspect([])
    assert hints.has_images is False
    assert hints.has_tools is False
    assert hints.estimated_tokens == 0
    assert hints.preferred_context_window is None


def test_image_with_no_text():
    hints = RequestInspector.inspect([
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "https://example.com/img.png"}},
            ],
        },
    ])
    assert hints.has_images is True
    assert hints.estimated_tokens == 0
    assert hints.has_tools is False


def test_mixed_content_images_and_tools():
    hints = RequestInspector.inspect([
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "what is this?"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ],
        },
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "t1", "type": "function", "function": {"name": "scan", "arguments": "{}"}}
            ],
        },
    ])
    assert hints.has_images is True
    assert hints.has_tools is True


def test_content_as_string():
    hints = RequestInspector.inspect([
        {"role": "system", "content": "you are helpful"},
        {"role": "user", "content": "hello"},
    ])
    assert hints.estimated_tokens == (len("you are helpful") + len("hello")) // 4
    assert hints.has_images is False
    assert hints.has_tools is False
