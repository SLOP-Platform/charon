"""Provider config store — load/save providers + add/remove."""
from __future__ import annotations

import re
from pathlib import Path

from ._store import _check_id, _load, _save, _validate_base_url

_FUNDING_CLASSES = {1, 2, 3, 4}
_FUNDING_CLASS_LABELS: dict[int, str] = {1: "free-recurring", 2: "flat-sub",
                                          3: "drain-then-park", 4: "payg"}


def load_providers(*, config_dir: str | Path | None = None) -> dict:
    return _load("providers.json", config_dir=config_dir)


def add_provider(name: str, *, base_url: str | None = None, key_env: str | None = None,
                 strip_v1: bool | None = None, downgrade_prone: bool | None = None,
                 max_context: int | None = None, max_concurrency: int | None = None,
                 funding_class: int | None = None,
                 starting_balance: float | None = None,
                 mode: str | None = None,  # "poll" | "fixed"
                 balance_base_url: str | None = None,
                 balance_key_env: str | None = None,
                 balance_ttl: int | None = None) -> Path:
    """Persist a provider override (base_url/key_env/quirks) to ``providers.json`` so
    a custom provider works without hand-edited config. Merges into any existing
    entry. Stores no secret value.

    DRAIN-AND-PARK fields (all optional; absent → provider inert):
    * ``funding_class`` — 1=free-recurring, 2=flat-sub, 3=drain-then-park prepaid, 4=PAYG
    * ``starting_balance`` — USD float for fixed-mode drain tracking
    * ``mode`` — ``"poll"`` (balance API) or ``"fixed"`` (starting_balance minus metered spend)
    * ``balance_base_url`` — balance API base URL (poll mode)
    * ``balance_key_env`` — env var holding the balance API key (poll mode)
    * ``balance_ttl`` — poll cache TTL in seconds (default 300)"""
    _check_id("provider", name)
    if base_url is not None:
        _validate_base_url(str(base_url))
    if key_env is not None and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(key_env)):
        raise ValueError(f"invalid key-env name {key_env!r}")
    if funding_class is not None and funding_class not in _FUNDING_CLASSES:
        raise ValueError(
            f"funding_class must be one of {sorted(_FUNDING_CLASSES)}, "
            f"got {funding_class}")
    if mode is not None and mode not in ("poll", "fixed"):
        raise ValueError(f"mode must be 'poll' or 'fixed', got {mode!r}")
    provs = load_providers()
    entry = dict(provs.get(name) or {})
    for k, v in (("base_url", base_url), ("key_env", key_env),
                 ("strip_v1", strip_v1), ("downgrade_prone", downgrade_prone),
                 ("max_context", max_context), ("max_concurrency", max_concurrency)):
        if v is not None:
            entry[k] = v
    # DRAIN-AND-PARK balance fields (scalar writes to avoid union-type inference)
    if funding_class is not None:
        entry["funding_class"] = funding_class
    if starting_balance is not None:
        entry["starting_balance"] = starting_balance
    if mode is not None:
        entry["mode"] = mode
    if balance_base_url is not None:
        entry["balance_base_url"] = balance_base_url
    if balance_key_env is not None:
        entry["balance_key_env"] = balance_key_env
    if balance_ttl is not None:
        entry["balance_ttl"] = balance_ttl
    provs[name] = entry
    return _save("providers.json", provs)
