"""User-local gateway config (providers / models / pools) in ``config_dir()``.

The single writer shared by the `charon providers`/`charon setup` CLI and the web
setup page, and the config the gateway reads by default — so adding a provider once
(CLI or browser) makes it work with no hand-edited TOML. API keys are NOT stored
here; they live in ``secrets.json`` (see :mod:`charon.secrets`). This file holds only
non-secret config: base URLs, ``key_env`` references, model maps, pools.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from . import secrets


def _validate_base_url(base_url: str) -> None:
    """A provider base URL later receives the real key as a Bearer on forward, so it
    must be http(s) and not a link-local/cloud-metadata host (SSRF / key-exfil guard,
    security review MED) — mirrors `charon providers test`."""
    parts = urlsplit(base_url)
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"base_url must be http(s), got {parts.scheme!r}")
    host = parts.hostname or ""
    if host.startswith("169.254.") or host == "metadata.google.internal":
        raise ValueError(f"refusing link-local / metadata base_url host {host!r}")

# Safe identifier for a provider/model/pool name (provider-prefixed model ids and
# version suffixes are common, so allow ``. / : -`` alongside word chars).
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:-]*$")


def _path(name: str) -> Path:
    return secrets.config_dir() / name


def _load(name: str) -> dict:
    p = _path(name)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(name: str, data: dict) -> Path:
    d = secrets.config_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = _path(name)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)  # atomic
    return p


def load_providers() -> dict:
    return _load("providers.json")


def load_models() -> dict:
    return _load("models.json")


def load_pools() -> dict:
    return _load("pools.json")


def _check_id(kind: str, name: str) -> None:
    if not isinstance(name, str) or not _ID_RE.match(name):
        raise ValueError(f"invalid {kind} name {name!r}")


def add_provider(name: str, *, base_url: str | None = None, key_env: str | None = None,
                 strip_v1: bool | None = None, downgrade_prone: bool | None = None) -> Path:
    """Persist a provider override (base_url/key_env/quirks) to ``providers.json`` so
    a custom provider works without hand-edited config. Merges into any existing
    entry. Stores no secret value."""
    _check_id("provider", name)
    if base_url is not None:
        _validate_base_url(str(base_url))
    if key_env is not None and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(key_env)):
        raise ValueError(f"invalid key-env name {key_env!r}")
    provs = load_providers()
    entry = dict(provs.get(name) or {})
    for k, v in (("base_url", base_url), ("key_env", key_env),
                 ("strip_v1", strip_v1), ("downgrade_prone", downgrade_prone)):
        if v is not None:
            entry[k] = v
    provs[name] = entry
    return _save("providers.json", provs)


def add_model(model_id: str, *, provider: str | None = None, upstream_base: str | None = None,
              upstream_model: str | None = None, key_env: str | None = None,
              free: bool = False, cost_rank: int = 1000) -> Path:
    """Persist a model to ``models.json`` (references a provider, or a direct
    upstream_base)."""
    _check_id("model", model_id)
    if provider is None and upstream_base is None:
        raise ValueError("a model needs either provider= or upstream_base=")
    models = load_models()
    entry: dict = {"free": bool(free), "cost_rank": int(cost_rank)}
    for k, v in (("provider", provider), ("upstream_base", upstream_base),
                 ("upstream_model", upstream_model), ("key_env", key_env)):
        if v is not None:
            entry[k] = v
    models[model_id] = entry
    return _save("models.json", models)


def add_models_bulk(entries: list[dict], *, provider: str) -> tuple[list[str], list[str]]:
    """Add many catalog models for one provider in a SINGLE atomic write (the
    `charon models import` path). Each entry is ``{id, free?, cost_rank?}``; the
    catalog id doubles as the upstream id (no ``upstream_model``). Ids failing
    ``_ID_RE`` are SKIPPED (not raised — an upstream list is untrusted). Returns
    ``(added, skipped)``."""
    _check_id("provider", provider)
    models = load_models()
    added: list[str] = []
    skipped: list[str] = []
    for e in entries:
        mid = e.get("id")
        if not isinstance(mid, str) or not _ID_RE.match(mid):
            skipped.append(str(mid))
            continue
        free = bool(e.get("free"))
        models[mid] = {
            "free": free,
            "cost_rank": int(e.get("cost_rank", 0 if free else 1000)),
            "provider": provider,
        }
        added.append(mid)
    if added:
        _save("models.json", models)
    return added, skipped


def set_pool(vid: str, members: list[str]) -> Path:
    """Define/replace a pool (virtual model id → ordered list of model ids)."""
    _check_id("pool", vid)
    bad = [m for m in members if not isinstance(m, str) or not _ID_RE.match(m)]
    if bad:
        raise ValueError(f"invalid model id(s) in pool: {bad}")
    pools = load_pools()
    pools[vid] = list(members)
    return _save("pools.json", pools)


def remove(kind: str, name: str) -> bool:
    """Remove a provider/model/pool by name. Returns True if it existed."""
    fname = {"provider": "providers.json", "model": "models.json", "pool": "pools.json"}[kind]
    data = _load(fname)
    if name in data:
        del data[name]
        _save(fname, data)
        return True
    return False


def summary() -> dict:
    """A non-secret view for the CLI/console: providers (with key-set state, NOT the
    key), models, pools."""
    secs = secrets.load_secrets()
    provs = {}
    for n, e in load_providers().items():
        ke = e.get("key_env")
        provs[n] = {
            "base_url": e.get("base_url"),
            "key_env": ke,
            "key_set": bool(ke and (os.environ.get(ke) or ke in secs)),
        }
    return {"providers": provs, "models": load_models(), "pools": load_pools()}
