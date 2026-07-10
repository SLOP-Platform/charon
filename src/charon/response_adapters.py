"""Response-shape adapters (ADR: universal per-provider response adapter).

A *response adapter* maps ONE provider's non-OpenAI response *shape* into the
canonical OpenAI Chat Completions shape, so the forwarder can relay every upstream
verbatim through a single blind call. This is **envelope/shape** normalization
(does the body have a top-level ``choices``/``usage``?), distinct from
``response_normalizer.py``, which is **content** normalization (markdown/JSON
cleanup *inside* ``choices[0].message.content``). The shape adapter runs FIRST
(produce a canonical envelope), then the content normalizer runs on that body.

Every already-compatible provider resolves to :data:`IDENTITY` — a byte-identical
passthrough — so nothing changes for them; the vendor knowledge lives in the
provider config (``adapter="cline"``), never sniffed from the response at runtime.
This mirrors the existing ``wire`` field precedent exactly.

Stdlib-only, deterministic, no network. Every method is TOTAL: on an
unrecognized / already-canonical input it MUST return the input unchanged
(idempotent) and never raise.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ResponseAdapter(Protocol):
    """Maps ONE provider's non-OpenAI response shape into canonical OpenAI Chat
    Completions shape. Pure/deterministic; stdlib only. All methods are total — on
    an unrecognized/already-canonical input they MUST return the input unchanged
    (idempotent), never raise."""

    def normalize_response(self, raw: dict) -> dict:
        """Non-streaming JSON body (already ``json.loads``'d) -> canonical OpenAI
        completion with a top-level ``choices`` list and (when recoverable) a
        top-level ``usage`` dict. Idempotent on already-canonical input.

        Invariant (see ADR §6): if ``usage`` cannot be recovered from the raw body
        the adapter MUST leave it absent (never fabricate zeros) so the existing
        "unknown pricing → nominal floor" estimate path still applies instead of a
        false zero."""
        ...

    def normalize_stream_chunk(self, chunk: dict) -> dict:
        """ONE parsed SSE data-event object -> canonical OpenAI streaming chunk.
        Operates on a SINGLE already-parsed event; SSE framing (the ``data:``
        prefix, ``[DONE]``, chunk boundaries) is the caller's concern, NOT here.
        Idempotent on canonical input."""
        ...

    def normalize_error(self, raw: dict) -> dict:
        """Non-200 body -> canonical OpenAI error envelope ``{error:{...}}``.
        Idempotent on canonical input."""
        ...


class IdentityAdapter:
    """The default for every provider: byte-identical passthrough on all shapes."""

    def normalize_response(self, raw: dict) -> dict:
        return raw

    def normalize_stream_chunk(self, chunk: dict) -> dict:
        return chunk

    def normalize_error(self, raw: dict) -> dict:
        return raw


IDENTITY: ResponseAdapter = IdentityAdapter()  # module singleton; every provider's default


class ClineAdapter:
    """cline-pass wraps its NON-streaming body as ``{"data": <openai obj>,
    "success": bool}``. Its streaming (SSE) responses are already canonical, so the
    stream method is passthrough today. Unwrap is guarded + idempotent + total."""

    def normalize_response(self, raw: dict) -> dict:
        if (isinstance(raw, dict) and "choices" not in raw
                and isinstance(raw.get("data"), dict) and "success" in raw):
            inner = raw["data"]
            if "choices" in inner:  # only unwrap a real OpenAI object
                return inner
        return raw  # already-canonical / unrecognized -> passthrough

    def normalize_stream_chunk(self, chunk: dict) -> dict:
        return chunk  # Cline SSE is already canonical (verified live)

    def normalize_error(self, raw: dict) -> dict:
        # Cline may wrap errors as {"data":{"error":...},"success":false}; unwrap to
        # a top-level {"error":...} if present, else passthrough (shape unverified —
        # ADR Q2, conservative guarded unwrap).
        if isinstance(raw, dict) and "error" not in raw:
            inner = raw.get("data")
            if isinstance(inner, dict) and "error" in inner:
                return {"error": inner["error"]}
        return raw


# Closed set of shipped adapters — a name→instance registry (declare, don't detect).
_ADAPTERS: dict[str, ResponseAdapter] = {"cline": ClineAdapter()}


def get_adapter(name: str | None) -> ResponseAdapter:
    """Resolve a provider's declared adapter key to its instance. An unknown or
    absent key resolves to :data:`IDENTITY` (the passthrough default)."""
    return _ADAPTERS.get(name or "", IDENTITY)
