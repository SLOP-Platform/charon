"""Pool config store — load/set pools (virtual model id → ordered member list)."""
from __future__ import annotations

from pathlib import Path

from ._store import _ID_RE, _check_id, _load, _save


def load_pools() -> dict:
    return _load("pools.json")


def set_pool(vid: str, members: list[str]) -> Path:
    """Define/replace a pool (virtual model id → ordered list of model ids)."""
    _check_id("pool", vid)
    bad = [m for m in members if not isinstance(m, str) or not _ID_RE.match(m)]
    if bad:
        raise ValueError(f"invalid model id(s) in pool: {bad}")
    pools = load_pools()
    pools[vid] = list(members)
    return _save("pools.json", pools)
