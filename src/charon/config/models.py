"""Model config store — load/save models, bulk import, enabled toggle."""
from __future__ import annotations

import re
import warnings
from pathlib import Path

from ._store import _check_id, _load, _save, _validate_base_url

_COST_CLASSES: tuple[str, ...] = (
    "free-daily", "expiring", "prepaid", "metered", "premium",
)


def _normalize_cost_class(value: object) -> str | None:
    if value is None:
        return None
    v = str(value).strip().lower()
    return v if v in _COST_CLASSES else None


def _warn_static_cost_rank_dropped(model_id: str, cost_rank: object) -> None:
    """ADR-0016 step #6: ``cost_rank`` is no longer persisted to ``models.json`` —
    ordering is derived from live/sourced/meter price.  External callers that
    still pass a hand-typed integer get a one-release deprecation warning; the
    field is silently dropped from the entry."""
    warnings.warn(
        f"cost_rank={cost_rank!r} on model {model_id!r} is deprecated and "
        f"IGNORED (ADR-0016 step #6). Ordering is now derived from "
        f"cost_input/cost_output + the live meter; remove the kwarg to "
        f"silence this warning.",
        DeprecationWarning,
        stacklevel=3,
    )


def load_models(*, config_dir: str | Path | None = None) -> dict:
    return _load("models.json", config_dir=config_dir)


def add_model(model_id: str, *, provider: str | None = None, upstream_base: str | None = None,
              upstream_model: str | None = None, key_env: str | None = None,
              free: bool = False, cost_rank: int | None = None,
              context_window: int | None = None, max_tokens: int | None = None,
              reasoning: bool | None = None, vision: bool | None = None,
              audio: bool | None = None,
              cost_input: float | None = None, cost_output: float | None = None,
              cost_class: str | None = None) -> Path:
    """Persist a model to ``models.json`` (references a provider, or a direct
    upstream_base). Optional metadata fields (context_window, max_tokens,
    reasoning, vision, audio, cost_input, cost_output, cost_class) are persisted
    only when non-None. ``cost_class`` is one of ``free-daily | expiring |
    prepaid | metered | premium`` (``premium`` is gated out of default-primary
    routing by the gateway compiler — see SR-6).

    DELETE-STATIC-RANK (ADR-0016 step #6): the ``cost_rank`` kwarg is ACCEPTED
    for backward-compat (some internal callers — e.g. ``lifecycle`` — still
    pass it), but it is NO LONGER PERSISTED and a ``DeprecationWarning`` is
    emitted when set. Ordering is ALWAYS derived from
    ``cost_input``/``cost_output`` and the live meter — see
    ``routing_policy.derived_cost_rank``.
    """
    _check_id("model", model_id)
    if provider is None and upstream_base is None:
        raise ValueError("a model needs either provider= or upstream_base=")
    if upstream_base is not None:
        # A direct entry binds upstream_base + key_env straight onto the forward
        # path (routing_policy._route_from_spec), so it gets the same SSRF/base
        # guard a provider's base_url does — it used to get none.
        _validate_base_url(str(upstream_base))
    if key_env is not None and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(key_env)):
        raise ValueError(f"invalid key-env name {key_env!r}")
    if cost_rank is not None:
        _warn_static_cost_rank_dropped(model_id, cost_rank)
    models = load_models()
    entry: dict = {"free": bool(free)}
    for k, v in (("provider", provider), ("upstream_base", upstream_base),
                 ("upstream_model", upstream_model), ("key_env", key_env)):
        if v is not None:
            entry[k] = v
    for k, mv in (("context_window", context_window), ("max_tokens", max_tokens),
                   ("reasoning", reasoning), ("vision", vision), ("audio", audio),
                   ("cost_input", cost_input), ("cost_output", cost_output)):
        if mv is not None:
            entry[k] = mv
    cc = _normalize_cost_class(cost_class)
    if cc is not None:
        entry["cost_class"] = cc
    models[model_id] = entry
    return _save("models.json", models)


def add_models_bulk(entries: list[dict], *, provider: str) -> tuple[list[str], list[str]]:
    """Add many catalog models for one provider in a SINGLE atomic write (the
    `charon models import` path). Each entry is ``{id, free?, cost_rank?}``; the
    catalog id doubles as the upstream id (no ``upstream_model``). Ids failing
    ``_ID_RE`` are SKIPPED (not raised — an upstream list is untrusted). Optional
    metadata fields (context_window, max_tokens, reasoning, vision, audio,
    cost_input, cost_output) are carried through if present.

    DELETE-STATIC-RANK (ADR-0016 step #6): ``cost_rank`` in an entry is
    ACCEPTED but NOT PERSISTED, with a ``DeprecationWarning`` when present.
    Returns ``(added, skipped)``."""
    _check_id("provider", provider)
    from ._store import _ID_RE
    _METADATA_KEYS = ("context_window", "max_tokens", "reasoning", "vision", "audio",
                      "cost_input", "cost_output", "cost_class")
    models = load_models()
    added: list[str] = []
    skipped: list[str] = []
    for e in entries:
        mid = e.get("id")
        if not isinstance(mid, str) or not _ID_RE.match(mid):
            skipped.append(str(mid))
            continue
        free = bool(e.get("free"))
        cr = e.get("cost_rank")
        if cr is not None:
            _warn_static_cost_rank_dropped(mid, cr)
        entry: dict = {
            "free": free,
            "provider": provider,
        }
        models[mid] = entry
        for k in _METADATA_KEYS:
            v = e.get(k)
            if k == "cost_class":
                v = _normalize_cost_class(v)
            if v is not None:
                models[mid][k] = v
        added.append(mid)
    if added:
        _save("models.json", models)
    return added, skipped


def set_model_enabled(model_id: str, enabled: bool) -> bool:
    """Toggle a model's ``enabled`` flag in ``models.json``. Returns True if the
    model existed."""
    models = load_models()
    if model_id not in models:
        return False
    models[model_id]["enabled"] = enabled
    _save("models.json", models)
    return True
