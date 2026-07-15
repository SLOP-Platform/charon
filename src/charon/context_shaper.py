"""Extractive TF / reservoir context compaction — EXPERIMENTAL, OPT-IN, OFF BY DEFAULT.

Small-context free models reject (400) or silently truncate long chats. This module
compresses OLD turns of a request's ``messages`` array into a single token-budgeted
summary so those models can accept the request — with NO extra LLM call. The summary
is produced by a pure stdlib extractive term-frequency (TF) sentence ranker plus a
position bias, greedily packed to a token budget. "Reservoir" mode keeps the last N
turns verbatim and summarizes everything older.

Design stance (READ THIS BEFORE WIRING)
---------------------------------------
Charon is a *transparent proxy*. Compaction MUTATES the user's messages, which
surprises clients and complicates debugging/caching. It is therefore the most cautious
feature in the codebase and is governed by hard, non-negotiable invariants:

* **OFF BY DEFAULT.** :class:`ShaperConfig.enabled` is ``False``. With the feature off
  the messages array passes through byte-for-byte (identity) — see :func:`shape`.
* **OPT-IN only** per-request or per-virtual-key (the caller flips ``enabled``).
* **STATELESS.** Operates in-request on the messages array only. No conversation store,
  no PII at rest. Same input -> same output (deterministic).
* **APPLIED ONLY WHEN OVER BUDGET.** If the request already fits the model's
  ``context_window`` the messages are returned UNCHANGED even when enabled.
* **DISCLOSED.** When compaction is applied, :class:`ShapeResult.applied` is ``True`` and
  :attr:`ShapeResult.disclosure` carries a marker the proxy surfaces as a response header
  (:data:`DISCLOSURE_HEADER`) so a client can tell compaction happened.
* **Stdlib only** — no third-party imports.

Pure function surface (messages in -> :class:`ShapeResult` out) so it is unit-testable
with zero ``proxy_server.py`` dependency.

## Wiring rider (FOLLOW-ON — NOT done in this ticket)
This module ships self-contained and gated; the proxy request-path wiring is a
deliberate follow-on rider, folded into the next ``proxy_server.py`` owner. The call
site goes in the request handler AFTER the model is resolved (so ``context_window`` is
known) and BEFORE the upstream forward, roughly::

    # proxy_server.py, request path, after model resolution:
    cfg = ShaperConfig(enabled=<opt-in flag from request/virtual-key>,
                       reserved_turns=<opt-in N>)
    result = shape(body["messages"], model_meta.context_window, cfg)
    if result.applied:
        body["messages"] = result.messages
        response_headers[DISCLOSURE_HEADER] = result.disclosure

The opt-in flag MUST default off; never enable it globally. Nothing outside that guarded
block may touch ``messages``.
"""
from __future__ import annotations

import dataclasses
import math
import re

# A message is an OpenAI-style chat entry: {"role": str, "content": str | list | ...}.
Message = dict[str, object]

# Response-header name the proxy sets when compaction is applied (disclosure invariant).
DISCLOSURE_HEADER = "X-Charon-Context-Shaped"

# Prefix stamped onto the synthesized summary message so it is self-identifying in logs
# and to downstream models. Not a security control — a transparency marker.
SUMMARY_MARKER = "[charon:compacted-context]"

# Small English stopword set — filler words carry no topical signal for TF ranking.
_STOPWORDS: frozenset[str] = frozenset(
    """a an and are as at be but by for from had has have he her his i if in into is it
    its of on or our she that the their them then there these they this to was we were
    what when where which who will with would you your""".split()
)

_WORD_RE = re.compile(r"[a-z0-9']+")
# Sentence boundary: terminal punctuation followed by whitespace. Deliberately simple
# and deterministic — good enough for extractive ranking, no NLP dependency.
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclasses.dataclass(frozen=True)
class ShaperConfig:
    """Per-request/per-virtual-key compaction config. OFF unless explicitly enabled."""

    enabled: bool = False
    """Master opt-in. When ``False`` (default) :func:`shape` is a pure passthrough."""

    mode: str = "reservoir"
    """Only ``"reservoir"`` is defined today: keep last N turns verbatim, summarize older."""

    reserved_turns: int = 3
    """N — number of most-recent turns kept VERBATIM (the reservoir)."""

    position_bias: float = 0.25
    """Weight (0..1) favouring earlier sentences of the old span in TF ranking."""

    safety_margin_tokens: int = 64
    """Headroom subtracted from ``context_window`` so the packed output leaves slack."""


@dataclasses.dataclass(frozen=True)
class ShapeResult:
    """Outcome of :func:`shape`. ``applied`` gates all disclosure/mutation."""

    messages: list[Message]
    """The (possibly compacted) messages. Identical object graph when not applied."""

    applied: bool
    """True only when compaction actually rewrote the array."""

    disclosure: str
    """Human/machine-readable marker for :data:`DISCLOSURE_HEADER`; empty when not applied."""

    summarized_turns: int = 0
    """How many old turns were folded into the summary (0 when not applied)."""


# ---------------------------------------------------------------------------
# Token estimation (stdlib heuristic — deterministic, provider-agnostic)
# ---------------------------------------------------------------------------

_CHARS_PER_TOKEN = 4
_PER_MESSAGE_OVERHEAD = 4  # role + framing, matches common chat-format accounting.


def estimate_tokens(text: str) -> int:
    """Deterministic ~chars/4 token estimate. Not a real tokenizer — a stable proxy."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / _CHARS_PER_TOKEN))


def _content_text(message: Message) -> str:
    """Best-effort text of a message's content (string, or text parts of a list)."""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(part, str):
                parts.append(part)
        return " ".join(parts)
    return "" if content is None else str(content)


def estimate_message_tokens(message: Message) -> int:
    return _PER_MESSAGE_OVERHEAD + estimate_tokens(_content_text(message))


def estimate_messages_tokens(messages: list[Message]) -> int:
    return sum(estimate_message_tokens(m) for m in messages)


# ---------------------------------------------------------------------------
# Extractive TF summarizer (no LLM call)
# ---------------------------------------------------------------------------


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT_RE.split(text.strip()) if s.strip()]


def _content_words(sentence: str) -> list[str]:
    return [w for w in _WORD_RE.findall(sentence.lower()) if w not in _STOPWORDS]


def rank_sentences(text: str, position_bias: float = 0.25) -> list[str]:
    """Return the sentences of ``text`` ordered best-first by TF score + position bias.

    Score = mean term-frequency of a sentence's content words (stopwords excluded),
    scaled up for earlier sentences by ``position_bias``. Deterministic: ties break on
    original position (earlier first). Exposed for focused unit testing of the ranker.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return []

    freq: dict[str, int] = {}
    for sent in sentences:
        for word in _content_words(sent):
            freq[word] = freq.get(word, 0) + 1

    n = len(sentences)
    scored: list[tuple[float, int, str]] = []
    for idx, sent in enumerate(sentences):
        words = _content_words(sent)
        base = (sum(freq[w] for w in words) / len(words)) if words else 0.0
        # Earlier sentences get up to (1 + position_bias)x; last gets 1x.
        pos_factor = 1.0 + position_bias * (1.0 - idx / n) if n > 1 else 1.0
        scored.append((base * pos_factor, idx, sent))

    # Sort by score desc, then original position asc (stable, deterministic tie-break).
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [sent for _, _, sent in scored]


def summarize(text: str, token_budget: int, position_bias: float = 0.25) -> str:
    """Greedily pack the highest-TF sentences of ``text`` into ``token_budget`` tokens.

    Selected sentences are re-emitted in their ORIGINAL order (readability), joined by a
    space. Deterministic for fixed input. Returns "" for empty input / non-positive budget.
    """
    if token_budget <= 0 or not text.strip():
        return ""

    sentences = _split_sentences(text)
    if not sentences:
        return ""
    order = {sent: idx for idx, sent in enumerate(sentences)}

    chosen: list[str] = []
    used = 0
    for sent in rank_sentences(text, position_bias):
        cost = estimate_tokens(sent)
        if used + cost > token_budget:
            continue  # skip and keep trying smaller sentences (best-effort fill)
        chosen.append(sent)
        used += cost
    if not chosen:
        return ""

    chosen.sort(key=lambda s: order[s])
    return " ".join(chosen)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _identity(messages: list[Message]) -> ShapeResult:
    return ShapeResult(messages=messages, applied=False, disclosure="", summarized_turns=0)


def shape(
    messages: list[Message],
    context_window: int | None,
    config: ShaperConfig | None = None,
) -> ShapeResult:
    """Compact ``messages`` to fit ``context_window`` — ONLY when opted-in AND over budget.

    Returns the ORIGINAL ``messages`` object unchanged (identity, ``applied=False``) when:
      * ``config`` is ``None`` or ``config.enabled`` is ``False`` (the default), or
      * ``context_window`` is unknown/non-positive, or
      * the request already fits the budget, or
      * there are too few turns to compact (nothing older than the reservoir).

    Otherwise (reservoir mode): keep any leading/older SYSTEM turns verbatim, keep the last
    ``reserved_turns`` turns verbatim, and fold the older non-system turns into one
    extractive-summary system message sized to the remaining budget. Never mutates the
    caller's list or dicts in place — builds a fresh array.
    """
    if config is None or not config.enabled:
        return _identity(messages)
    if context_window is None or context_window <= 0:
        return _identity(messages)
    if estimate_messages_tokens(messages) <= context_window:
        return _identity(messages)

    n = max(0, config.reserved_turns)
    if len(messages) <= n + 1:
        # Not enough old turns to gain anything by summarizing — stay transparent.
        return _identity(messages)

    tail = messages[len(messages) - n :] if n else []
    older = messages[: len(messages) - n] if n else list(messages)

    # Preserve system turns from the old span verbatim (they are instructions, not chat).
    older_system = [m for m in older if m.get("role") == "system"]
    older_chat = [m for m in older if m.get("role") != "system"]
    if not older_chat:
        return _identity(messages)  # nothing summarizable

    # The synthesized summary message carries a self-identifying prefix; its tokens count
    # against the window too, so budget for them explicitly (else a small safety_margin
    # could let the packed output overflow context_window — a real over-budget hazard).
    summary_prefix = f"{SUMMARY_MARKER} Summary of {len(older_chat)} earlier turn(s): "
    prefix_tokens = estimate_tokens(summary_prefix)

    # Budget left for the summary = window minus what we keep verbatim minus prefix/slack.
    overhead = (
        estimate_messages_tokens(older_system)
        + estimate_messages_tokens(tail)
        + _PER_MESSAGE_OVERHEAD  # the summary message's own framing
        + prefix_tokens  # the marker/"Summary of N turns:" prefix is real tokens too
        + config.safety_margin_tokens
    )
    summary_budget = context_window - overhead
    if summary_budget <= 0:
        # Even the reservoir + systems overflow; compaction can't help without dropping
        # user-visible turns. Stay transparent rather than mangle the request.
        return _identity(messages)

    old_text = "\n".join(_content_text(m) for m in older_chat if _content_text(m))
    summary_body = summarize(old_text, summary_budget, config.position_bias)
    if not summary_body:
        return _identity(messages)

    summary_msg: Message = {
        "role": "system",
        "content": f"{summary_prefix}{summary_body}",
    }

    new_messages: list[Message] = [*older_system, summary_msg, *tail]
    disclosure = (
        f"applied; mode={config.mode}; reserved={n}; "
        f"summarized={len(older_chat)}; window={context_window}"
    )
    return ShapeResult(
        messages=new_messages,
        applied=True,
        disclosure=disclosure,
        summarized_turns=len(older_chat),
    )
