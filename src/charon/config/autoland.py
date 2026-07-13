"""Auto-land config (ADR-0012) — engine-owned, outside any worktree."""
from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ._store import _as_str_tuple, _load, _save

_AUTOLAND_ENV = "CHARON_AUTOLAND"
_AUTOLAND_FILE = "autoland.json"
_TRUTHY = {"1", "true", "yes", "on", "enable", "enabled"}


@dataclass(frozen=True)
class AutoLandConfig:
    """Opt-in auto-land settings (ADR-0012). Default = OFF (propose-default).

    ``enabled``        — master switch; auto-land does nothing (HOLD, no git
                         mutation) unless this is explicitly True.
    ``allowlist``      — path prefixes that MAY auto-land; a changed file must be
                         both in its unit's ``owned_paths`` and on this list, else
                         it HOLDS. Empty (the default) lands nothing — fail-closed.
    ``extra_sensitive``— additional always-hold path prefixes layered ON TOP of the
                         built-in sensitive set (``land.is_sensitive``); the set can
                         only be widened, never shrunk.
    ``base_branch``    — the branch a clean batch fast-forwards (default ``master``).
    """

    enabled: bool = False
    allowlist: tuple[str, ...] = ()
    extra_sensitive: tuple[str, ...] = ()
    base_branch: str = "master"


def _truthy(raw: object) -> bool:
    if isinstance(raw, bool):
        return raw
    return isinstance(raw, str) and raw.strip().lower() in _TRUTHY


def load_autoland_config(env: Mapping[str, str] | None = None) -> AutoLandConfig:
    """Resolve the auto-land config from engine-owned sources (NOT the worktree).

    Precedence, fail-closed: the master switch is on only if EITHER the persisted
    ``autoland.json`` says ``enabled`` OR ``CHARON_AUTOLAND`` is truthy — but the
    env var alone never *implies* an allowlist, so an enabled-but-empty-allowlist
    config lands nothing. Any malformed field degrades to the safe default (off /
    empty), never to a wider grant."""
    e = os.environ if env is None else env
    data = _load(_AUTOLAND_FILE)
    enabled = _truthy(data.get("enabled")) or _truthy(e.get(_AUTOLAND_ENV, ""))
    base = data.get("base_branch")
    return AutoLandConfig(
        enabled=enabled,
        allowlist=_as_str_tuple(data.get("allowlist")),
        extra_sensitive=_as_str_tuple(data.get("sensitive_paths")),
        base_branch=base if isinstance(base, str) and base.strip() else "master",
    )


def save_autoland_config(
    *,
    enabled: bool,
    allowlist: Sequence[str] = (),
    extra_sensitive: Sequence[str] = (),
    base_branch: str = "master",
) -> Path:
    """Persist the engine-owned auto-land config to ``autoland.json`` in
    ``config_dir()`` (outside any worktree). Operator-only surface: this is the
    single place the opt-in is granted."""
    data = {
        "enabled": bool(enabled),
        "allowlist": list(_as_str_tuple(list(allowlist))),
        "sensitive_paths": list(_as_str_tuple(list(extra_sensitive))),
        "base_branch": base_branch if base_branch.strip() else "master",
    }
    return _save(_AUTOLAND_FILE, data)
