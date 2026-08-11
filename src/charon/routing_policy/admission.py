"""Zen/Go provider admission control (S26).

ZEN is discovery-driven: models known-to-be-free are ALLOWED, everything
else is REFUSED. The free list ROTATES — a previously-free model that
starts charging MUST be blocked, and a new free model MUST be adopted.

GO is a fixed allowlist: exactly two models are permitted.

Both are enforced at pool-build time (``build_routes_and_pools``) so
they fire on EVERY catalog refresh cycle — not seeded once and forgotten.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("charon.admission")

_ZEN_FREE_MODELS_FILE = "zen_free_models.json"

# GO fixed allowlist — operator-defined, does not rotate.
_GO_ALLOWLIST: frozenset[str] = frozenset({"deepseek-v4-flash", "mimo-v2.5"})


class AdmissionViolation(ValueError):
    """Raised loudly when a model violates zen/go admission policy.

    A silent drop makes a broken policy indistinguishable from a broken
    provider. This is raised so the caller can log it AND refuse the
    model — never swallowed.
    """


def _zen_free_models_path(state_dir: str | Path | None = None) -> Path | None:
    if state_dir is None:
        from charon import secrets
        try:
            state_dir = secrets.config_dir()
        except Exception:
            return None
    return Path(state_dir) / _ZEN_FREE_MODELS_FILE


def load_zen_free_models(state_dir: str | Path | None = None) -> frozenset[str]:
    """Return the set of models KNOWN to be free on opencode-zen.

    Loads from ``<state_dir>/zen_free_models.json``. Returns an empty
    frozenset when the file is absent or unreadable — the gateway will
    REFUSE to serve ZEN traffic (fail-closed).

    The file is a simple JSON list::

        ["big-pickle", "deepseek-v4-flash-free", ...]

    This is the operator-auditable list that SHOULD be refreshed from the
    authoritative ZEN pricing page on a cadence.
    """
    p = _zen_free_models_path(state_dir)
    if p is None or not p.exists():
        return frozenset()
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return frozenset()
    if not isinstance(data, dict):
        return frozenset()
    models = data.get("free_models")
    if not isinstance(models, list):
        return frozenset()
    return frozenset(str(m) for m in models)


def save_zen_free_models(
    models: set[str] | frozenset[str],
    state_dir: str | Path | None = None,
) -> bool:
    """Persist the ZEN free-model set to disk. Returns True on success."""
    p = _zen_free_models_path(state_dir)
    if p is None:
        return False
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(
            json.dumps({
                "free_models": sorted(models),
                "updated": "",  # operator fills on next sync
            }, indent=2), encoding="utf-8")
        tmp.replace(p)
        return True
    except OSError:
        return False


def check_zen_admission(model_id: str, spec: dict[str, Any],
                        free_models: frozenset[str] | None = None,
                        state_dir: str | Path | None = None) -> None:
    """Check *model_id* against the ZEN free-only admission policy.

    Matches on the UPSTREAM model name (what the ZEN API serves), not the
    provider-suffixed catalog leg id. ``big-pickle`` in the ZEN catalog
    maps to upstream ``big-pickle``; ``deepseek-v4-flash-free-zen`` would
    map to upstream ``deepseek-v4-flash-free``.

    Raises ``AdmissionViolation`` when the model is NOT in the free set.
    A model IN the free set is silently accepted.

    *free_models* — preloaded frozenset (saves a disk read per model
    during ``build_routes_and_pools``). When None, reads from disk.
    """
    if free_models is None:
        free_models = load_zen_free_models(state_dir)

    if not free_models:
        raise AdmissionViolation(
            f"opencode-zen free-model list is EMPTY — refusing model "
            f"{model_id!r}. Rebuild the list from the ZEN pricing page."
        )

    upstream = spec.get("upstream_model") or model_id
    if upstream not in free_models:
        raise AdmissionViolation(
            f"model {model_id!r} (upstream {upstream!r}) is NOT in the "
            f"opencode-zen free-model list "
            f"(known free: {sorted(free_models)})"
        )


def check_go_admission(model_id: str, spec: dict[str, Any]) -> None:
    """Check *model_id* against the GO fixed allowlist.

    Matches on the UPSTREAM model name (what the GO API serves), not the
    provider-suffixed catalog leg id. ``deepseek-v4-flash-go`` in the
    catalog → ``deepseek-v4-flash`` is the matching upstream key.

    Raises ``AdmissionViolation`` when the model is NOT on the allowlist.
    """
    upstream = spec.get("upstream_model") or model_id
    if upstream not in _GO_ALLOWLIST:
        raise AdmissionViolation(
            f"model {model_id!r} (upstream {upstream!r}) is NOT on the "
            f"opencode-go allowlist (allowed: {sorted(_GO_ALLOWLIST)})"
        )
