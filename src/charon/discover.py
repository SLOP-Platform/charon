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
    return cost_map
