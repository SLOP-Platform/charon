"""Provider model discovery — query /v1/models, cross-reference, build cost maps.

Implements PROPOSAL-1 Phase A: discover all models available across configured
providers by querying their /v1/models endpoints in parallel, then cross-reference
model IDs to build a cost map for routing decisions.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from . import config, providers, secrets

_COST_MAP_FILE = "cost_map.json"


def discover_provider(base_url: str, api_key: str | None,
                      strip_v1: bool = True, timeout: float = 10) -> list[dict] | None:
    """Query a single provider's /models endpoint.

    If *strip_v1* is True the base URL already includes the /v1 prefix so /models
    is appended.  If False the base is a bare host and /v1/models is appended.
    Returns a list of raw model dicts (each with at least ``"id"``), or None on
    any error.
    """
    if strip_v1:
        url = base_url.rstrip("/") + "/models"
    else:
        url = base_url.rstrip("/") + "/v1/models"

    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "charon-proxy/0.1")
    if api_key:
        req.add_header("Authorization", "Bearer " + api_key)

    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        raw = resp.read()
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return None

    items = data.get("data") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return None

    result: list[dict] = []
    for it in items:
        if isinstance(it, dict) and isinstance(it.get("id"), str):
            result.append(it)
        elif isinstance(it, str):
            result.append({"id": it})
    return result


def build_cost_map(discoveries: dict[str, list[dict] | None]) -> dict:
    """Cross-reference model IDs across providers into a cost map.

    *discoveries* is ``{provider_name: [model_dict, ...] | None}`` where each
    model dict is a raw /models entry (at minimum ``{"id": str}``).

    Returns ``{model_id: {"providers": [{"provider", "pricing", "free"}]}}``
    grouped case-insensitively by model ID.  A provider whose discovery
    returned ``None`` (failure) is simply skipped.
    """
    _by_key: dict[str, tuple[str, list[dict]]] = {}

    for provider_name, model_list in discoveries.items():
        if not model_list:
            continue
        for m in model_list:
            mid = m.get("id")
            if not isinstance(mid, str):
                continue
            key = mid.casefold()

            entry: dict[str, object] = {"provider": provider_name}

            pricing = m.get("pricing")
            if isinstance(pricing, dict):
                entry["pricing"] = dict(pricing)

            free_val = False
            if mid.endswith(":free"):
                free_val = True
            elif isinstance(pricing, dict):
                try:
                    vals = [float(pricing[k]) for k in ("prompt", "completion")]
                    free_val = bool(vals) and all(v == 0 for v in vals)
                except (KeyError, TypeError, ValueError):
                    pass
            entry["free"] = free_val

            if key not in _by_key:
                _by_key[key] = (mid, [])
            _by_key[key][1].append(entry)

    return {orig_id: {"providers": prov_list} for orig_id, prov_list in _by_key.values()}


def save_cost_map(cost_map: dict, config_dir: str | Path | None = None):
    """Write cost_map.json to *config_dir* (or the default config dir)."""
    d = Path(config_dir) if config_dir is not None else secrets.config_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = d / _COST_MAP_FILE
    p.write_text(json.dumps(cost_map, indent=2), encoding="utf-8")


def load_cost_map(config_dir: str | Path | None = None) -> dict:
    """Read cost_map.json.  Returns ``{}`` when the file is absent or corrupt."""
    d = Path(config_dir) if config_dir is not None else secrets.config_dir()
    p = d / _COST_MAP_FILE
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def discover_models(refresh: bool = False, timeout: int = 10,
                    config_dir: str | Path | None = None) -> dict:
    """Query all configured providers' /v1/models endpoints.

    Loads configured providers from config + built-in presets, resolves API keys
    from env vars or secrets, then queries all providers in parallel via
    ThreadPoolExecutor (max 5 workers).  Saves the resulting cost map to disk and
    returns it.

    *refresh* is reserved for future use (force re-query even if cached).
    """
    prov_cfg = config.load_providers(config_dir=config_dir)
    secs = secrets.load_secrets(cd=config_dir)

    targets: list[tuple[str, str, str | None, bool]] = []
    seen: set[str] = set()

    for name, preset in providers.PRESETS.items():
        override = prov_cfg.get(name) or {}
        base = override.get("base_url", preset.base_url)
        key_env = override.get("key_env", preset.key_env)
        strip = override.get("strip_v1", preset.strip_v1)

        api_key: str | None = None
        if key_env:
            api_key = os.environ.get(key_env) or secs.get(key_env)

        targets.append((name, base, api_key, strip))
        seen.add(name)

    for name, prov in prov_cfg.items():
        if name in seen:
            continue
        base = prov.get("base_url")
        if not isinstance(base, str):
            continue
        key_env = prov.get("key_env")
        api_key = None
        if isinstance(key_env, str):
            api_key = os.environ.get(key_env) or secs.get(key_env)
        strip = prov.get("strip_v1", True)
        targets.append((name, base, api_key, strip))

    discoveries: dict[str, list[dict] | None] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futs: dict[concurrent.futures.Future[list[dict] | None], str] = {}
        for name, base, api_key, strip in targets:
            fut = executor.submit(discover_provider, base, api_key, strip, timeout)
            futs[fut] = name

        for fut in concurrent.futures.as_completed(futs):
            name = futs[fut]
            try:
                discoveries[name] = fut.result()
            except Exception:  # noqa: BLE001
                discoveries[name] = None

    cost_map = build_cost_map(discoveries)
    save_cost_map(cost_map, config_dir=config_dir)
    _update_model_pricing_from_discovery(discoveries, config_dir=config_dir)
    return cost_map


def _update_model_pricing_from_discovery(
    discoveries: dict[str, list[dict] | None],
    config_dir: str | Path | None = None,
) -> None:
    """Persist per-token pricing from discovered models into ``models.json``.

    For each discovered model that matches an existing entry in the model
    registry (case-insensitive), extract ``cost_input`` / ``cost_output``
    via ``providers._extract_pricing`` and write them into the registry so
    served models carry real cost data.
    """
    models = config.load_models(config_dir=config_dir)
    if not models:
        return
    changed = False
    for _provider_name, model_list in discoveries.items():
        if not model_list:
            continue
        for m in model_list:
            mid = m.get("id")
            if not isinstance(mid, str):
                continue
            key = mid.casefold()
            matched = None
            for existing_id in models:
                if existing_id.casefold() == key:
                    matched = existing_id
                    break
            if matched is None:
                continue
            entry: dict[str, object] = {}
            providers._extract_pricing(m, entry)
            if "cost_input" in entry:
                v = entry["cost_input"]
                if isinstance(v, (int, float)):
                    models[matched]["cost_input"] = float(v)
                    changed = True
            if "cost_output" in entry:
                v = entry["cost_output"]
                if isinstance(v, (int, float)):
                    models[matched]["cost_output"] = float(v)
                    changed = True
    if changed:
        config._save("models.json", models)


# ── Phase D: OpenRouter swarm import ────────────────────────────────

_OPENROUTER_API = "https://openrouter.ai/api/v1/models"
_ALIAS_FILE = "model_aliases.json"


def discover_openrouter(timeout: float = 10) -> list[dict] | None:
    """Fetch the OpenRouter model catalogue (no auth needed)."""
    req = urllib.request.Request(_OPENROUTER_API, method="GET")
    req.add_header("User-Agent", "charon-proxy/0.1")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        raw = resp.read()
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return None
    if isinstance(data, list):
        return [m for m in data if isinstance(m, dict) and "id" in m]
    items = data.get("data") if isinstance(data, dict) else None
    if isinstance(items, list):
        return [m for m in items if isinstance(m, dict) and "id" in m]
    return None


def _load_alias_map(config_dir: str | Path | None = None) -> dict:
    d = Path(config_dir) if config_dir is not None else secrets.config_dir()
    p = d / _ALIAS_FILE
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


_KNOWN_PREFIXES = {"openai", "anthropic", "google", "meta-llama", "mistralai",
                   "deepseek", "cohere", "x-ai", "perplexity", "together", "groq"}


def fuzzy_match_model_id(or_id: str, charon_models: list[str],
                         config_dir: str | Path | None = None) -> tuple[str | None, int]:
    """Match an OpenRouter model ID to an existing Charon model.

    Returns ``(charon_id, match_stage)`` where stage is:
        0 — no match
        1 — exact match (case-insensitive)
        2 — prefix-stripped match
        3 — alias-map match

    Stage 1 matches can be auto-imported; stages 2-3 need review.
    """
    key = or_id.casefold()
    alias_map = _load_alias_map(config_dir)
    if key in alias_map:
        return alias_map[key], 3
    for m in charon_models:
        if m.casefold() == key:
            return m, 1
    for prefix in _KNOWN_PREFIXES:
        tag = prefix + "/"
        if or_id.lower().startswith(tag):
            bare = or_id[len(tag):]
            for m in charon_models:
                if m.casefold() == bare.casefold():
                    return m, 2
    return None, 0


def import_openrouter_models(dry_run: bool = False,
                              config_dir: str | Path | None = None) -> dict:
    """Pull OpenRouter catalogue, cross-reference, and bulk-import.

    Returns ``{"imported": N, "fuzzy_review": N, "new": N, "skipped": N}``.
    When *dry_run* is True, nothing is persisted.
    Stage-1 (exact) matches are auto-imported; stage 2-3 matches go to review.
    """
    or_models = discover_openrouter()
    if not or_models:
        return {"imported": 0, "fuzzy_review": 0, "new": 0, "skipped": 0}
    existing = config.load_models(config_dir=config_dir)
    charon_ids = list(existing.keys())
    imported, fuzzy_review, new, skipped = 0, 0, 0, 0
    review: dict[str, list[dict]] = {}
    for m in or_models:
        or_id = m.get("id")
        if not isinstance(or_id, str):
            skipped += 1
            continue
        match, stage = fuzzy_match_model_id(or_id, charon_ids, config_dir=config_dir)
        if match is not None and stage == 1:
            if not dry_run:
                cost_input: float | None = None
                cost_output: float | None = None
                pricing = m.get("pricing")
                if isinstance(pricing, dict):
                    try:
                        prompt_str = pricing.get("prompt", "0")
                        comp_str = pricing.get("completion", "0")
                        cost_input = float(prompt_str) / 1_000_000
                        cost_output = float(comp_str) / 1_000_000
                    except (ValueError, TypeError):
                        pass
                ctx = m.get("context_length")
                context_window: int | None = int(ctx) if isinstance(ctx, (int, float)) else None
                free = or_id.endswith(":free") or (isinstance(pricing, dict) and
                    all(float(str(pricing.get(k, "0"))) == 0 for k in ("prompt", "completion")))
                if free:
                    cost_input = cost_output = 0.0
                config.add_model(match, free=free, context_window=context_window,
                                 cost_input=cost_input, cost_output=cost_output)
            imported += 1
        elif match is not None:
            fuzzy_review += 1
            if not dry_run:
                key = or_id.casefold()
                review.setdefault(key, []).append(m)
        else:
            new += 1
            if not dry_run:
                key = or_id.casefold()
                review.setdefault(key, []).append(m)
    if not dry_run and review:
        d = Path(config_dir) if config_dir is not None else secrets.config_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / "discover_review.json").write_text(
            json.dumps(review, indent=2), encoding="utf-8")
    return {"imported": imported, "fuzzy_review": fuzzy_review,
            "new": new, "skipped": skipped}
