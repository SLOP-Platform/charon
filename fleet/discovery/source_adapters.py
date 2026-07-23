#!/usr/bin/env python3
"""Source adapters: pull community source feeds into uniform list[RawOffer].

_SOURCE_ADAPTERS registry (KS29 shape, one row per source). Each adapter is a
() -> list[RawOffer] function off the hot path. Mirror catalog_refresh's
ListModelsFn injection shape + the _POLL_ADAPTERS registry pattern from
balance.py so a new source = one new dict row.

Sources
-------
1. models.dev  api.json  — ADOPT (MIT JSON, clean, no scraping)
2. OpenRouter  /api/v1/models  — REUSE the same endpoint Charon already polls
3. cheahjs/free-llm-api-resources  src/data.py  — SIGNAL only, no vendoring
"""

import ast
import json
import urllib.request
from dataclasses import dataclass, field
from typing import Callable


_MODELS_DEV_URL = "https://models.dev/api.json"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
_CHEAHJS_URL = "https://raw.githubusercontent.com/cheahjs/free-llm-api-resources/main/src/data.py"

_TIMEOUT = 20.0
_MAX_BYTES = 5 * 1024 * 1024
_BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/127.0.0.0 Safari/537.36"


@dataclass
class RawOffer:
    source: str
    provider: str
    model_id: str
    name: str | None = None
    cost_input: float | None = None
    cost_output: float | None = None
    context_limit: int | None = None
    output_limit: int | None = None
    open_weights: bool | None = None
    free: bool = False
    raw: dict = field(default_factory=dict)


def _fetch_json(url: str) -> object:
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": _BROWSER_UA})
    resp = urllib.request.urlopen(req, timeout=_TIMEOUT)
    raw = resp.read(_MAX_BYTES)
    return json.loads(raw.decode("utf-8", "replace"))


def _fetch_text(url: str) -> str:
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": _BROWSER_UA})
    resp = urllib.request.urlopen(req, timeout=_TIMEOUT)
    raw = resp.read(_MAX_BYTES)
    return raw.decode("utf-8", "replace")


def _pull_models_dev() -> list[RawOffer]:
    payload = _fetch_json(_MODELS_DEV_URL)
    if not isinstance(payload, dict):
        return []
    offers: list[RawOffer] = []
    for prov_key, prov_val in payload.items():
        if not isinstance(prov_val, dict):
            continue
        provider_id = prov_val.get("id") or prov_val.get("name") or prov_key
        models = prov_val.get("models")
        if not isinstance(models, dict):
            continue
        for model_key, model_val in models.items():
            if not isinstance(model_val, dict):
                continue
            cost = model_val.get("cost", {})
            if isinstance(cost, dict):
                cost_input = cost.get("input")
                cost_output = cost.get("output")
            else:
                cost_input = cost_output = None
            limit = model_val.get("limit", {})
            if isinstance(limit, dict):
                ctx = limit.get("context")
                out = limit.get("output")
            else:
                ctx = out = None
            is_free = (
                isinstance(cost_input, (int, float))
                and isinstance(cost_output, (int, float))
                and cost_input == 0
                and cost_output == 0
            )
            offers.append(RawOffer(
                source="models_dev",
                provider=provider_id,
                model_id=model_val.get("id") or model_key,
                name=model_val.get("name"),
                cost_input=cost_input,
                cost_output=cost_output,
                context_limit=ctx,
                output_limit=out,
                open_weights=model_val.get("open_weights"),
                free=is_free,
                raw=model_val,
            ))
    return offers


def _pull_openrouter() -> list[RawOffer]:
    payload = _fetch_json(_OPENROUTER_URL)
    data = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(data, list):
        return []
    offers: list[RawOffer] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id", "")
        pricing = item.get("pricing", {}) or {}
        prompt_raw = pricing.get("prompt", "0")
        completion_raw = pricing.get("completion", "0")
        try:
            prompt_cost = float(prompt_raw) if prompt_raw not in (None, "", "0") else 0.0
        except (ValueError, TypeError):
            prompt_cost = 0.0
        try:
            completion_cost = float(completion_raw) if completion_raw not in (None, "", "0") else 0.0
        except (ValueError, TypeError):
            completion_cost = 0.0
        is_free = (prompt_cost == 0.0 and completion_cost == 0.0)
        top = item.get("top_provider") or {}
        offers.append(RawOffer(
            source="openrouter",
            provider="openrouter",
            model_id=model_id,
            name=item.get("name"),
            cost_input=prompt_cost if not is_free else None,
            cost_output=completion_cost if not is_free else None,
            context_limit=item.get("context_length") or top.get("context_length"),
            output_limit=top.get("max_completion_tokens"),
            open_weights=None,
            free=is_free,
            raw=item,
        ))
    return offers


def _pull_cheahjs() -> list[RawOffer]:
    text = _fetch_text(_CHEAHJS_URL)
    tree = ast.parse(text)
    mapping: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "MODEL_TO_NAME_MAPPING":
                    if isinstance(node.value, (ast.Dict, ast.Call)):
                        try:
                            val = ast.literal_eval(node.value)
                            if isinstance(val, dict):
                                mapping = val
                        except (ValueError, SyntaxError):
                            pass
    offers: list[RawOffer] = []
    for model_id, name in mapping.items():
        offers.append(RawOffer(
            source="cheahjs",
            provider="cheahjs",
            model_id=model_id,
            name=name,
            free=True,
            raw={},
        ))
    return offers


_SOURCE_ADAPTERS: dict[str, Callable[[], list[RawOffer]]] = {
    "models_dev": _pull_models_dev,
    "openrouter": _pull_openrouter,
    "cheahjs": _pull_cheahjs,
}


def pull_all() -> dict[str, list[RawOffer]]:
    result: dict[str, list[RawOffer]] = {}
    for name, adapter in _SOURCE_ADAPTERS.items():
        try:
            result[name] = adapter()
        except Exception:
            result[name] = []
    return result


if __name__ == "__main__":
    import sys
    results = pull_all()
    total = sum(len(v) for v in results.values())
    for src, offers in results.items():
        print(f"{src}: {len(offers)} offers")
    print(f"total: {total}")
    sys.exit(0)
