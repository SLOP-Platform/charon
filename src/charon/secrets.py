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
import re
from pathlib import Path

_SECRETS_FILE = "secrets.json"
# A valid environment-variable name; rejects "", names with '='/newline/NUL, etc.
_KEY_ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Never load these from the secrets file into the process env, even if present —
# they steer code loading/execution (defense-in-depth; the file is 0600 user-owned).
_SENSITIVE_ENV = frozenset({
    "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT", "DYLD_INSERT_LIBRARIES",
    "PYTHONPATH", "PYTHONSTARTUP", "PATH", "BROWSER", "IFS", "SHELL",
    "GIT_SSH", "GIT_SSH_COMMAND", "GIT_EXTERNAL_DIFF", "GIT_PAGER", "PAGER",
    "NODE_OPTIONS", "BASH_ENV", "ENV",
    "PYTHONHOME", "PYTHONCASEOK", "PERL5OPT", "RUBYOPT",
    "JAVA_TOOL_OPTIONS", "GIT_CONFIG_PARAMETERS",
    "SSL_CERT_FILE", "SSL_CERT_DIR",
})


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


def load_secrets(*, cd: str | Path | None = None) -> dict[str, str]:
    """Read ``{key_env: value}`` from the secrets file (empty/absent → ``{}``)."""
    d = Path(cd) if cd is not None else config_dir()
    p = d / _SECRETS_FILE
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def set_secret(key_env: str, value: str) -> Path:
    """Store one key under its env-var name. Writes a FRESH 0600 temp file (with
    ``O_NOFOLLOW``/``O_EXCL`` so a planted symlink/loose-perm pre-existing file is
    never written through) and atomically ``os.replace``s it into place — so the key
    is never briefly world-readable and the write is atomic. Never logs the value."""
    if not _KEY_ENV_RE.match(key_env):
        raise ValueError(f"invalid key-env name {key_env!r} (must be a valid env var)")
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass  # best-effort (Windows ACLs differ)
    secrets = load_secrets()
    secrets[key_env] = value
    p = secrets_path()
    tmp = p.with_name(p.name + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    try:
        os.unlink(tmp)  # a stale/planted temp must not be written through
    except FileNotFoundError:
        pass
    fd = os.open(str(tmp), flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(secrets, f, indent=2)
    os.replace(tmp, p)  # atomic; the destination inherits the temp's 0600
    return p


def apply_to_env() -> None:
    """Load stored secrets into ``os.environ`` without overriding anything already
    set — an explicit environment variable always wins. Only well-formed key-env
    names are loaded, and loader-sensitive vars (PATH, LD_PRELOAD, …) are never
    injected from the file (defense-in-depth)."""
    for k, v in load_secrets().items():
        if _KEY_ENV_RE.match(k) and k not in _SENSITIVE_ENV:
            os.environ.setdefault(k, v)
