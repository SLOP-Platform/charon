"""File primitives for the config package: _load, _save, and shared utilities."""
from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit

from .. import secrets


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


def _load(name: str, *, config_dir: str | Path | None = None) -> dict:
    d = Path(config_dir) if config_dir is not None else secrets.config_dir()
    p = d / name
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(name: str, data: dict, *, config_dir: str | Path | None = None) -> Path:
    d = Path(config_dir) if config_dir is not None else secrets.config_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)  # atomic
    return p


def _check_id(kind: str, name: str) -> None:
    if not isinstance(name, str) or not _ID_RE.match(name):
        raise ValueError(f"invalid {kind} name {name!r}")


def _as_str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(v for v in value if isinstance(v, str) and v.strip())


def remove(kind: str, name: str) -> bool:
    """Remove a provider/model/pool by name. Returns True if it existed."""
    fname = {"provider": "providers.json", "model": "models.json", "pool": "pools.json"}[kind]
    data = _load(fname)
    if name in data:
        del data[name]
        _save(fname, data)
        return True
    return False
