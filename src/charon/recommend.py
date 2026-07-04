"""Tier model recommendations — LLM-judge tier ranking from a live /v1/models catalog.

Phase B of TIER-RECS: uses already-configured trusted models to rank a
provider's model catalog into Charon's tier vocabulary (low/med/high),
with consensus, anti-hallucination guards, and heuristic fallback.
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


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
    from . import config, secrets
    secrets.apply_to_env()
    models = config.load_models(config_dir=config_dir)
    providers = config.load_providers(config_dir=config_dir)
    secs = secrets.load_secrets(cd=config_dir)
    trusted: list[tuple[str, str, str]] = []
    for mid, entry in models.items():
        if not isinstance(entry, dict):
            continue
        prov_name = entry.get("provider")
        if not prov_name:
            continue
        prov = providers.get(prov_name)
        if not prov:
            continue
        base_url = prov.get("base_url")
        if not base_url:
            continue
        key_env = prov.get("key_env")
        if not key_env:
            continue
        api_key = os.environ.get(key_env) or secs.get(key_env)
        if not api_key:
            continue
        trusted.append((mid, base_url, api_key))
    return trusted


def _ask_model(model_id: str, base_url: str, api_key: str,
               catalog: list[dict], timeout: float = 30.0) -> dict | None:
    """Ask one model to rank a catalog into low/med/high. Returns parsed JSON dict
    with tier keys, or None on failure."""
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

    prompt = (
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

    raw_base = base_url.rstrip("/")
    body = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 2000,
    }).encode()
    try:
        req = urllib.request.Request(raw_base + "/chat/completions", data=body, method="POST")
        req.add_header("User-Agent", "charon-proxy/0.1")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + api_key)
        opener = urllib.request.build_opener(_NoRedirect())
        resp = opener.open(req, timeout=timeout)
        raw = resp.read(200_000)
        data = json.loads(raw.decode("utf-8", "replace"))
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
        return json.loads(content)  # type: ignore[no-any-return]
    except (urllib.error.HTTPError, urllib.error.URLError,
            json.JSONDecodeError, ValueError, KeyError):
        return None


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

def recommend_tiers(provider_name: str, catalog: list[dict], *,
                     config_dir: str | Path | None = None) -> list[TierRecommendation]:
    """Rank a provider's live model catalog into low/med/high tiers.

    Uses 1–3 already-configured trusted models (with consensus) to rank the
    catalog. Anti-hallucination: drops any model id not in the real catalog.
    Falls back to heuristic ranking if no trusted model responds.

    Returns three TierRecommendations (one per tier), each with an ordered list
    of model ids.
    """
    from . import secrets
    valid_ids = {m["id"] for m in catalog if isinstance(m.get("id"), str)}

    if config_dir is None:
        config_dir = secrets.config_dir()
    trusted = _find_trusted_models(config_dir)
    if not trusted:
        return _heuristic_rank(catalog)

    votes: dict[str, dict[str, int]] = {"low": {}, "med": {}, "high": {}}
    respondents = 0
    for model_id, base_url, api_key in trusted[:3]:
        result = _ask_model(model_id, base_url, api_key, catalog)
        if result and isinstance(result, dict):
            respondents += 1
            for tier in ("low", "med", "high"):
                tier_models = result.get(tier, [])
                if isinstance(tier_models, list):
                    for mid in tier_models:
                        if isinstance(mid, str) and mid in valid_ids:
                            vt = votes[tier]
                            vt[mid] = vt.get(mid, 0) + 1

    if respondents == 0:
        return _heuristic_rank(catalog)

    all_voted: set[str] = set()
    for vt in votes.values():
        all_voted.update(vt.keys())

    model_tiers: dict[str, list[str]] = {"low": [], "med": [], "high": []}
    for mid in all_voted:
        best_tier = "med"
        best_count = 0
        for tier in ("low", "med", "high"):
            count = votes[tier].get(mid, 0)
            if count > best_count:
                best_count = count
                best_tier = tier
        model_tiers[best_tier].append(mid)

    for mid in valid_ids:
        if mid not in all_voted:
            model_tiers["med"].append(mid)

    return [
        TierRecommendation("high", model_tiers["high"]),
        TierRecommendation("med", model_tiers["med"]),
        TierRecommendation("low", model_tiers["low"]),
    ]
