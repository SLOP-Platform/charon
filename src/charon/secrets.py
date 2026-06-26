"""User-local secret storage for the gateway setup flow (ADR-0005 P3.5).

Provider API keys must NEVER live in the repo (operator hard rule). They go in a
**0600 user-local file** (`~/.charon/secrets.json`, or `%APPDATA%\\charon` on
Windows) and are loaded into the process environment at gateway start — so the
existing `key_env` resolution is unchanged and keys stay out of any config that
could be committed/shared. Nothing here ever prints a key.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_SECRETS_FILE = "secrets.json"


def config_dir() -> Path:
    """The user-local Charon config/secrets directory. Override with ``$CHARON_HOME``;
    on Windows defaults to ``%APPDATA%\\charon``, else ``~/.charon``."""
    override = os.environ.get("CHARON_HOME")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    if appdata and os.name == "nt":
        return Path(appdata) / "charon"
    return Path.home() / ".charon"


def secrets_path() -> Path:
    return config_dir() / _SECRETS_FILE


def load_secrets() -> dict[str, str]:
    """Read ``{key_env: value}`` from the secrets file (empty/absent → ``{}``)."""
    p = secrets_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def set_secret(key_env: str, value: str) -> Path:
    """Store one key under its env-var name, writing the file with 0600 perms (and
    the directory 0700). Returns the secrets path. Never logs the value."""
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass  # best-effort (e.g. Windows ACLs differ)
    secrets = load_secrets()
    secrets[key_env] = value
    p = secrets_path()
    # open with 0600 from the start so the key is never briefly world-readable
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(secrets, f, indent=2)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return p


def apply_to_env() -> None:
    """Load stored secrets into ``os.environ`` without overriding anything already
    set — an explicit environment variable always wins over the stored file."""
    for k, v in load_secrets().items():
        os.environ.setdefault(k, v)
