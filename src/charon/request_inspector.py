"""Request inspector — lightweight pre-flight hints for gateway routing."""
from __future__ import annotations

from charon.types import RequestHints


class RequestInspector:
    """Single-pass inspection of chat messages producing cheap routing hints."""

    @staticmethod
    def inspect(messages: list[dict]) -> RequestHints:
        has_images = False
        has_tools = False
        total_text_len = 0

        for msg in messages:
            if "tool_calls" in msg:
                has_tools = True

            if msg.get("role") == "tool":
                has_tools = True

            content = msg.get("content")
            if content is None:
                continue

            if isinstance(content, str):
                total_text_len += len(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "image_url":
                            has_images = True
                        elif "text" in part:
                            total_text_len += len(str(part["text"]))
                    elif isinstance(part, str):
                        total_text_len += len(part)

        estimated_tokens = total_text_len // 4
        return RequestHints(
            has_images=has_images,
            has_tools=has_tools,
            estimated_tokens=estimated_tokens,
            preferred_context_window=None,
        )
