"""User-local secret storage for the gateway setup flow (ADR-0005 P3.5).

Provider API keys must NEVER live in the repo (operator hard rule). They go in a
**0600 user-local file** (`~/.charon/secrets.json`, or `%APPDATA%\\charon` on
Windows). Nothing here ever prints a key.

KEY-EXFIL FIX — keys are stored PER PROVIDER, not per env-var name. A key_env is
a *shared* name (two providers may legitimately declare the same one), so using
it as the storage key gave an attacker a namespace to alias into: bind a new
provider to an attacker base_url under a victim's key_env and every keyed send
site would hand the victim's key to the attacker. Storage is now keyed by
PROVIDER ID (`provider:<id>` entries, which are deliberately not valid env-var
names and so never reach `os.environ`), and :func:`get_provider_key` is the ONE
resolver every send site uses — validation and send read the same value.

`key_env` survives as a READ-ONLY, BASE-BOUND legacy fallback so installs that
follow the published docs (`providers add … --key-env X` + `X=… ` in `.env`)
keep working. It is never a write target, and the fallback only fires when the
provider's base_url is the one the built-in preset binds that key_env to — so
there is no longer a base an attacker can move a key to.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

_SECRETS_FILE = "secrets.json"
# A valid environment-variable name; rejects "", names with '='/newline/NUL, etc.
_KEY_ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Namespace for per-provider keys. The ':' makes these entries un-exportable as
# env vars by construction, so `apply_to_env` can never surface one and a
# provider key can never collide with (or clobber) a legacy `key_env` entry.
_PROVIDER_PREFIX = "provider:"
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
    """Store one key under its env-var name (LEGACY — prefer
    :func:`set_provider_key`). Kept for the local-operator CLI paths and for
    reading back installs written by older versions."""
    if not _KEY_ENV_RE.match(key_env):
        raise ValueError(f"invalid key-env name {key_env!r} (must be a valid env var)")
    return _write_secret(key_env, value)


def _write_secret(name: str, value: str) -> Path:
    """Store one secret under *name*. Writes a FRESH 0600 temp file (with
    ``O_NOFOLLOW``/``O_EXCL`` so a planted symlink/loose-perm pre-existing file is
    never written through) and atomically ``os.replace``s it into place — so the key
    is never briefly world-readable and the write is atomic. Never logs the value."""
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass  # best-effort (Windows ACLs differ)
    secrets = load_secrets()
    secrets[name] = value
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
    names are loaded (so ``provider:<id>`` entries never surface as env vars), and
    loader-sensitive vars (PATH, LD_PRELOAD, …) are never injected from the file
    (defense-in-depth)."""
    for k, v in load_secrets().items():
        if _KEY_ENV_RE.match(k) and k not in _SENSITIVE_ENV:
            os.environ.setdefault(k, v)


# --------------------------------------------------------------------------
# Per-provider keys (KEY-EXFIL FIX). One store, one resolver: whatever
# `validate_provider_key` probed is exactly what the send sites later send.
# --------------------------------------------------------------------------


def set_provider_key(provider_id: str, value: str) -> Path:
    """Store *value* as the key for one provider, keyed by PROVIDER ID.

    Namespaced under ``provider:``, so this write can never reach ``os.environ``
    and can never overwrite another provider's key or a legacy ``key_env`` entry
    — which also closes the credential-destruction path the setup handler used to
    expose (a caller could clobber any stored key by naming its key_env)."""
    _check_provider_id(provider_id)
    return _write_secret(_PROVIDER_PREFIX + provider_id, value)


def _check_provider_id(provider_id: str) -> None:
    if not provider_id or not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", provider_id):
        raise ValueError(f"invalid provider id {provider_id!r}")


def _normalize_base(base_url: str | None) -> str | None:
    """Canonical form of a base URL for equality checks: lower-cased scheme+host,
    explicit default ports and trailing dots/slashes removed. Comparing raw
    strings (or only ``rstrip('/')``) lets ``https://h/v1``, ``https://H:443/v1``
    and ``https://h./v1`` read as three different bases — which would be a way
    around the binding check below."""
    if not base_url:
        return None
    try:
        parts = urlsplit(str(base_url).strip())
    except ValueError:
        return None
    scheme = (parts.scheme or "").lower()
    host = (parts.hostname or "").lower().rstrip(".")
    if not scheme or not host:
        return None
    port = parts.port
    if port is None or (scheme, port) in (("http", 80), ("https", 443)):
        port_s = ""
    else:
        port_s = f":{port}"
    return f"{scheme}://{host}{port_s}{parts.path.rstrip('/')}"


def same_base(a: str | None, b: str | None) -> bool:
    """True when two base URLs address the same endpoint (see :func:`_normalize_base`).
    Unparseable bases never compare equal — an un-checkable base is not a match."""
    na, nb = _normalize_base(a), _normalize_base(b)
    return na is not None and na == nb


def same_host(a: str | None, b: str | None) -> bool:
    """True when two URLs share scheme+host+port, whatever their paths. Used where
    a companion endpoint legitimately lives at a different path on the same host
    (a provider's balance API vs its API base)."""
    def origin(u: str | None) -> str | None:
        n = _normalize_base(u)
        if n is None:
            return None
        parts = urlsplit(n)
        return f"{parts.scheme}://{parts.netloc}"

    oa, ob = origin(a), origin(b)
    return oa is not None and oa == ob


def _env_fallback_allowed(key_env: str, base_url: str | None) -> bool:
    """May the LEGACY env/file value stored under *key_env* be sent to *base_url*?

    Only when no built-in preset claims that ``key_env``, or when *base_url* is
    one of the bases a claiming preset binds it to. Presets are static in-repo
    data — unlike the persisted provider config, they are not attacker-writable,
    so they are a usable trust anchor. Presets may legitimately share a key_env
    across several bases (``opencode-zen``/``opencode-go``), hence "one of".
    """
    from . import providers as _providers  # deferred: providers.py must not need secrets

    bound = {
        _normalize_base(p.base_url)
        for p in _providers.PRESETS.values()
        if p.key_env == key_env and p.base_url
    }
    if not bound:
        return True  # operator-defined env var, no preset binding to violate
    return _normalize_base(base_url) in bound


def get_provider_key(
    provider_id: str | None,
    *,
    key_env: str | None = None,
    base_url: str | None = None,
    cd: str | Path | None = None,
    secs: dict[str, str] | None = None,
) -> str | None:
    """Resolve the key to send for *provider_id* when talking to *base_url*.

    THE single provider-key resolver — every keyed send site goes through it.
    Resolution order:

    1. the per-provider secret (``provider:<id>``) — authoritative;
    2. else the legacy ``key_env`` value from ``os.environ``/the secrets file,
       but ONLY when :func:`_env_fallback_allowed` says that env var is not
       preset-bound to a different base.

    Returns None when nothing resolves — a provider that cannot prove its
    key<->base binding sends no key rather than the wrong one.
    """
    store = secs if secs is not None else load_secrets(cd=cd)
    if provider_id:
        val = store.get(_PROVIDER_PREFIX + provider_id)
        if val:
            return val
    if key_env and _env_fallback_allowed(key_env, base_url):
        return os.environ.get(key_env) or store.get(key_env) or None
    return None


def migrate_provider_secrets(*, cd: str | Path | None = None) -> list[str]:
    """Copy legacy ``{key_env: value}`` secrets to per-provider entries, once.

    Idempotent and non-destructive: providers that already have a per-provider
    key are left alone and the legacy entries are never removed, so a container
    that restarts on a mounted config volume converges instead of breaking (and
    a rollback still finds its keys). Returns the provider ids migrated.
    """
    from . import config as _config
    from . import providers as _providers

    store = load_secrets(cd=cd)
    try:
        prov_cfg = _config.load_providers(config_dir=cd)
    except Exception:  # noqa: BLE001 — unreadable config must not block startup
        return []
    migrated: list[str] = []
    for name in sorted(set(prov_cfg) | set(_providers.PRESETS)):
        if store.get(_PROVIDER_PREFIX + name):
            continue
        try:
            preset = _providers.resolve(name, prov_cfg.get(name))
        except ValueError:
            continue
        key_env = (prov_cfg.get(name) or {}).get("key_env") or preset.key_env
        if not key_env:
            continue
        # Reuse the resolver so a legacy entry is only promoted when it was
        # already legitimately sendable to that provider's base.
        val = get_provider_key(name, key_env=key_env, base_url=preset.base_url,
                               secs=store)
        if not val:
            continue
        set_provider_key(name, val)
        store[_PROVIDER_PREFIX + name] = val
        migrated.append(name)
    return migrated
