"""Request normalizer — strips output-only fields from inbound messages
before forwarding to an upstream provider.

When Charon fails over / continues multi-turn across providers, inbound
messages can carry an assistant ``reasoning_content`` field emitted by one
provider (e.g. DeepSeek).  Another provider (e.g. Groq) then rejects the
request: ``role:assistant ... property 'reasoning_content' is unsupported``.

This module strips those output-only fields from the ``messages`` array
so the forwarded payload conforms to the OpenAI chat request spec.

--- Symmetric to ``response_normalizer.py`` ---
Small, stdlib-only, well-commented.  Stripping is safe-by-default (no
config gate needed — these fields are OUTPUT-only and never part of a
valid client request per the OpenAI spec).

Fields stripped from assistant messages:
  - ``reasoning_content``  (DeepSeek echo)
  - ``reasoning``          (Anthropic-style reasoning in assistant role)

Tool call arrays are preserved (OpenAI-spec ``id``/``type``/``function``).
"""
from __future__ import annotations

import copy

# ---------------------------------------------------------------------------
# Fields that are output-only and NEVER valid in a client request.
# Providers that echo these in the assistant role cause downstream rejections.
# ---------------------------------------------------------------------------
_OUTPUT_ONLY_ASSISTANT_FIELDS: frozenset[str] = frozenset({
    "reasoning_content",
    "reasoning",
})


def _strip_output_only_from_message(msg: dict) -> dict:
    """Strip output-only fields from a single assistant message dict.

    Non-assistant messages and non-dict values are returned unchanged.
    Returns a NEW dict (does not mutate the input).
    """
    if not isinstance(msg, dict):
        return msg

    if msg.get("role") != "assistant":
        return msg

    cleaned: dict = {}
    for key, value in msg.items():
        if key in _OUTPUT_ONLY_ASSISTANT_FIELDS:
            continue
        cleaned[key] = value
    return cleaned


def normalize_messages(messages: list[dict] | None) -> list[dict] | None:
    """Strip output-only fields from every assistant message in *messages*.

    Returns a deep-copied list with stripped messages.  Returns ``None`` if
    *messages* is ``None``.  Idempotent: a body with no output-only fields
    is returned unchanged (same shape, semantically equal).
    """
    if messages is None:
        return None

    return [
        _strip_output_only_from_message(copy.deepcopy(m))
        for m in messages
    ]
