"""Tier model recommendations — LLM-judge tier ranking from a live /v1/models catalog.

Phase B of TIER-RECS: uses already-configured trusted models to rank a
provider's model catalog into Charon's tier vocabulary (low/med/high),
with consensus, anti-hallucination guards, and heuristic fallback.

Failover (DESTIFF-RECOMMEND): the model-invoke is routed through
``failover_loop.invoke_with_failover`` over the FULL ordered trusted pool, so
a transport/auth/limit failure on one provider fails over to the next instead
of zeroing the recommendation. Composes the same primitive
``decompose_planner`` already uses — class-level fix, not a bespoke loop.
Unlike the planner, the tier-voter path is allowed to use Anthropic models
(SG-never-Anthropic is planner-only, see ``decompose_planner``).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .failover_loop import (
    FAILOVER,
    OK,
    RETRY,
    AttemptResult,
    invoke_with_failover,
)
from .netutil import BROWSER_UA  # shared browser-like UA (P5 — Cloudflare 1010)


@dataclass
class TierRecommendation:
    """A single tier's recommendation: canonical name + list of model ids."""
    tier: str          # "low", "med", or "high"
    model_ids: list[str] = field(default_factory=list)


# ----------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _find_trusted_models(config_dir: str | Path) -> list[tuple[str, str, str]]:
    """Find already-configured models that have working API keys.
    Returns list of (model_id, base_url, api_key) tuples."""
    from . import config, providers, secrets
    secrets.apply_to_env()
    models = config.load_models(config_dir=config_dir)
    providers_cfg = config.load_providers(config_dir=config_dir)
    secs = secrets.load_secrets(cd=config_dir)
    trusted: list[tuple[str, str, str]] = []
    for mid, entry in models.items():
        if not isinstance(entry, dict):
            continue
        prov_name = entry.get("provider")
        if not prov_name:
            continue
        prov = providers_cfg.get(prov_name) or {}
        # Resolve base_url/key_env through the preset registry. A provider added
        # from a built-in preset (e.g. ``providers add zai``) persists only its
        # ``key_env`` — its ``base_url`` lives in the preset, NOT in providers.json.
        # Reading the raw entry alone silently dropped EVERY preset-configured
        # provider (returning no trusted models even when keys were present);
        # ``providers.resolve`` is the same lookup ``discover.py`` and the
        # ``providers test`` CLI already use for exactly these providers.
        try:
            resolved = providers.resolve(prov_name, prov)
        except ValueError:
            continue  # unknown provider with no base_url anywhere — cannot route
        base_url = prov.get("base_url") or resolved.base_url
        if not base_url:
            continue
        key_env = prov.get("key_env") or resolved.key_env
        if not key_env:
            continue
        api_key = os.environ.get(key_env) or secs.get(key_env)
        if not api_key:
            continue
        trusted.append((mid, base_url, api_key))
    return trusted


# ----------------------------------------------------------------
# Transport taxonomy (DESTIFF-RECOMMEND — fix the blanket None).
# A 401/403/407 (auth), 402/429 (limit), 5xx/URLError/timeout (infra), or any
# other provider-level fault MUST fail OVER to the next candidate — NOT look
# like an unparseable model reply. The same transport-vs-quality split the
# planner applies (see decompose_planner._post_chat) is used here.
# ----------------------------------------------------------------
_AUTH_STATUSES = frozenset({401, 403, 407})
_LIMIT_STATUSES = frozenset({402, 429})


def _classify_status(code: int) -> str:
    """Map an HTTP status to a provider-level failure class."""
    if code in _AUTH_STATUSES:
        return "auth"
    if code in _LIMIT_STATUSES:
        return "limit"
    return "infra"  # 5xx and any other non-2xx transport-level status


class _TierTransportError(RuntimeError):
    """A PROVIDER-level transport failure while invoking a tier-voter candidate —
    distinct from a parse/quality failure of a 200 reply. Carries the failure
    class and HTTP status (when known) so the failover loop can attribute it
    and advance to the next candidate. Mirrors ``decompose_planner.PlannerTransportError``
    (stdlib-only seam — never leaks ``urllib`` types to callers)."""

    def __init__(self, failure_class: str, status: int | None, detail: str) -> None:
        self.failure_class = failure_class
        self.status = status
        self.detail = detail
        super().__init__(detail)


def _render_prompt(catalog: list[dict]) -> str:
    """Build the tier-ranking prompt from a live catalog (model lines + instructions)."""
    model_lines = []
    for m in catalog:
        cw = m.get("context_window", "")
        mt = m.get("max_tokens", "")
        extra = ""
        if cw or mt:
            parts = []
            if cw:
                parts.append(f"ctx={cw}")
            if mt:
                parts.append(f"max_tok={mt}")
            extra = f" ({', '.join(parts)})"
        model_lines.append(f"- {m['id']}{extra}")
    model_list = "\n".join(model_lines[:200])

    return (
        "You are ranking LLM models into three tiers for a gateway's failover configuration.\n\n"
        "TIER DEFINITIONS:\n"
        "- high (frontier): most capable, best for complex reasoning/coding; "
        "use for critical tasks\n"
        "- med (strong): good general-purpose models; use for routine work\n"
        "- low (economy): cheapest/fastest models; use for simple tasks or as fallbacks\n\n"
        f"LIVE MODEL CATALOG:\n{model_list}\n\n"
        "Rank EVERY model above into exactly one tier. Reply ONLY with valid JSON:\n"
        '{"low": ["id1","id2"], "med": ["id3","id4"], "high": ["id5","id6"]}\n\n'
        "Rules:\n"
        "- Every model in the catalog MUST appear in exactly one tier.\n"
        "- Prefer higher tiers for models with large context windows, strong reasoning "
        "capability, or known frontier brands (Claude, GPT, Gemini).\n"
        "- Prefer lower tiers for smaller/faster/cheaper models (Haiku, Flash, mini variants).\n"
        "- Respond with ONLY the JSON, no explanation."
    )


def _post_tier_ranking(
    model_id: str, base_url: str, api_key: str, prompt: str, timeout: float = 30.0
) -> dict | None:
    """POST ``prompt`` to ``base_url``'s ``/chat/completions`` and parse the reply as JSON.

    Failure taxonomy (DESTIFF-RECOMMEND — no longer a blanket None):
      * PROVIDER-level fault (auth 401/403/407, limit 402/429, infra 5xx / URLError /
        timeout) → raise ``_TierTransportError`` so the failover loop tries the NEXT
        candidate. A dead/mis-scoped key no longer masquerades as an unparseable
        ranking.
      * 200 but the body/content is not a parseable JSON dict → return ``None`` (a
        parse/quality fault of THIS model → re-prompt the SAME model).

    Stdlib-only; mirrors ``decompose_planner._post_chat`` and the browser-UA /
    no-redirect opener in the original ``recommend._ask_model``.
    """
    raw_base = base_url.rstrip("/")
    body = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 2000,
    }).encode()
    req = urllib.request.Request(raw_base + "/chat/completions", data=body, method="POST")
    req.add_header("User-Agent", BROWSER_UA)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + api_key)
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        resp = opener.open(req, timeout=timeout)
        raw = resp.read(200_000)
    except urllib.error.HTTPError as e:
        # HTTPError is a URLError subclass — catch it first to read the status code.
        raise _TierTransportError(
            _classify_status(e.code), e.code, f"HTTP {e.code} from {model_id}"
        ) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise _TierTransportError(
            "infra", None, f"transport error from {model_id}: {e}"
        ) from e

    # 200 body in hand — a parse failure here is THIS model's answer quality, not a
    # provider fault, so return None (→ re-prompt the same model), never raise.
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
        parsed = json.loads(content)
    except (json.JSONDecodeError, ValueError, KeyError, IndexError, AttributeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _ask_model(model_id: str, base_url: str, api_key: str,
               catalog: list[dict], timeout: float = 30.0) -> dict | None:
    """Per-candidate tier-ranking transport: render the prompt, POST it, return parsed
    JSON dict or ``None`` on parse failure. Raises ``_TierTransportError`` on a
    provider-level transport fault (auth/limit/infra) so the caller can fail over.

    ``recommend_tiers`` itself no longer calls this directly — it routes through
    ``failover_loop.invoke_with_failover`` over the full trusted pool. This thin
    wrapper is kept for the per-candidate test seam and any future direct caller.
    """
    return _post_tier_ranking(
        model_id, base_url, api_key, _render_prompt(catalog), timeout=timeout
    )


def _heuristic_rank(catalog: list[dict]) -> list[TierRecommendation]:
    """Fallback: infer tiers from metadata and name patterns when no model is reachable."""
    low: list[str] = []
    med: list[str] = []
    high: list[str] = []
    for m in catalog:
        mid = m["id"]
        is_free = bool(m.get("free"))
        ctx = m.get("context_window") or 0
        name_lower = mid.lower()
        # Heuristic tier assignment based on model-name keyword patterns —
        # these WILL rot as providers ship new models and deprecate old names.
        # Replace with a data-driven ranking (cost × capability) when available (ATC-013).
        if any(k in name_lower for k in ("claude-3.5", "claude-3-5", "claude-4",
                "gpt-4o", "gpt-4.5", "gpt-4-", "gemini-2.0", "gemini-2-5",
                "gemini-2.5", "grok-3", "deepseek-r1", "deepseek-v3")):
            high.append(mid)
        elif any(k in name_lower for k in ("haiku", "flash", "mini", "nano", "tiny",
                "8b", "7b", "3b", "1b", "0.5b")):
            low.append(mid)
        elif isinstance(ctx, (int, float)) and ctx >= 100000:
            high.append(mid)
        elif is_free:
            low.append(mid)
        else:
            med.append(mid)
    return [
        TierRecommendation("high", high),
        TierRecommendation("med", med),
        TierRecommendation("low", low),
    ]


# ----------------------------------------------------------------
# Public API
# ----------------------------------------------------------------

# Hard cap on how many trusted candidates we walk before giving up. The pool is
# the user's configured set, not a managed ladder — this prevents a misconfigured
# 50-model install from burning the gate when every model is dead. Three
# respondents is plenty for a tier-judge; if the first three all FAIL OVER
# (transport), the rest are overwhelmingly likely to as well.
_MAX_TIER_CANDIDATES = 3


@dataclass(frozen=True)
class _TierCandidate:
    """One tier-voter candidate: (model_id, base_url, api_key). The per-candidate
    transport is ``_post_tier_ranking`` with the rendered prompt; classification
    into RETRY vs FAILOVER is done by ``_classify_tier_attempt``."""
    model_id: str
    base_url: str
    api_key: str


def _classify_tier_attempt(
    model_id: str, base_url: str, api_key: str, prompt: str, feedback: str
) -> AttemptResult[dict]:
    """One tier-voter attempt against one candidate, classified for the failover loop:
    provider-level transport faults → ``FAILOVER`` (try the next model); a 200 whose
    body is unparseable → ``RETRY`` (re-prompt the SAME model with feedback)."""
    from_feedback = (
        f"Retry — your previous answer was not valid JSON. {feedback}".strip()
        if feedback
        else prompt
    )
    try:
        parsed = _post_tier_ranking(model_id, base_url, api_key, from_feedback)
    except _TierTransportError as e:
        status = f" (HTTP {e.status})" if e.status is not None else ""
        return AttemptResult(
            kind=FAILOVER,
            attribution=f"{e.failure_class}{status}: {e.detail}",
        )

    if not isinstance(parsed, dict):
        return AttemptResult(
            kind=RETRY,
            feedback="reply was not a JSON object with low/med/high keys",
            attribution="quality: unparseable 200 reply",
        )
    # Light shape check — if the model returned {} or junk, treat as quality.
    if not any(isinstance(parsed.get(tier), list) for tier in ("low", "med", "high")):
        return AttemptResult(
            kind=RETRY,
            feedback="reply must include low/med/high list keys",
            attribution="quality: missing tier keys",
        )
    return AttemptResult(kind=OK, value=parsed)


def recommend_tiers(provider_name: str, catalog: list[dict], *,
                     config_dir: str | Path | None = None) -> list[TierRecommendation]:
    """Rank a provider's live model catalog into low/med/high tiers.

    Walks the ordered pool of already-configured trusted models via
    ``failover_loop.invoke_with_failover``: a transport/auth/limit failure on one
    candidate fails OVER to the next; a 200-but-unparseable reply is re-prompted
    on the SAME model (up to ``max_reprompts=1`` extra times). The first valid
    ranking wins. The whole pool is exhausted before falling back to heuristic.

    Anti-hallucination: any model id not in the real catalog is dropped. The
    return contract is unchanged — three ``TierRecommendation`` rows in
    high/med/low order.

    Unlike ``decompose_planner``, the tier-voter path is allowed to use Anthropic
    models — there is no SG-never-Anthropic guard here.
    """
    from . import secrets
    valid_ids = {m["id"] for m in catalog if isinstance(m.get("id"), str)}

    if config_dir is None:
        config_dir = secrets.config_dir()
    trusted = list(_find_trusted_models(config_dir))
    if not trusted:
        return _heuristic_rank(catalog)

    pinned = os.environ.get("CHARON_DECOMPOSE_WORKER_MODEL")
    if pinned:
        trusted.sort(key=lambda t: t[0] != pinned)
    else:
        from .config import tiers as tiers_cfg
        high_ids = set(tiers_cfg.tier_members("high"))
        trusted.sort(key=lambda t: t[0] not in high_ids)

    pool: Sequence[_TierCandidate] = [
        _TierCandidate(mid, base_url, api_key)
        for mid, base_url, api_key in trusted[:_MAX_TIER_CANDIDATES]
    ]
    if not pool:
        return _heuristic_rank(catalog)

    prompt = _render_prompt(catalog)

    def _attempt(cand: _TierCandidate, feedback: str) -> AttemptResult[dict]:
        return _classify_tier_attempt(
            cand.model_id, cand.base_url, cand.api_key, prompt, feedback
        )

    try:
        result = invoke_with_failover(
            list(pool),
            _attempt,
            max_retries=1,  # one extra re-prompt per candidate on quality fault
            describe=lambda c: c.model_id,
            recommendation=(
                f"all tier-voter candidates exhausted for provider {provider_name!r} — "
                "configure a working chat-capable model or check provider keys"
            ),
            error=_RecommendError,
        )
    except _RecommendError:
        return _heuristic_rank(catalog)

    if not isinstance(result, dict):
        return _heuristic_rank(catalog)

    # Apply the winner's ranking with anti-hallucination: drop any model id the
    # real catalog doesn't actually have, and bucket the rest by the model's vote.
    model_tiers: dict[str, list[str]] = {"low": [], "med": [], "high": []}
    for tier in ("low", "med", "high"):
        for mid in result.get(tier, []) or []:
            if isinstance(mid, str) and mid in valid_ids:
                model_tiers[tier].append(mid)

    voted: set[str] = set()
    for ids in model_tiers.values():
        voted.update(ids)
    for mid in valid_ids:
        if mid not in voted:
            model_tiers["med"].append(mid)

    return [
        TierRecommendation("high", model_tiers["high"]),
        TierRecommendation("med", model_tiers["med"]),
        TierRecommendation("low", model_tiers["low"]),
    ]


class _RecommendError(RuntimeError):
    """The tier-voter pool is exhausted. Carries a per-candidate failure summary
    ending with the actionable recommendation. Surfaces only inside
    ``recommend_tiers`` (which falls back to heuristic); never leaks to callers
    of the public API."""
