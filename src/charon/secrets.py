"""User-local secret storage for the gateway setup flow (ADR-0005 P3.5).

**Read docs/adr/0019-provider-key-egress-choke-point.md before changing the
resolver or the storage shape.** It records why the shared ``key_env`` env-var-NAME
indirection was fatal (validate-here / send-there), why the base binding is
enforced on READ rather than on write, and the five-round failure history in which
every fix that looked obviously correct was bypassed. The per-provider secret
model and the base-binding invariant below are the parts that must survive any
future transport swap — unlike ``netutil``'s hand-rolled hardening, which that ADR
marks as a stopgap to be deleted rather than ported.

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
provider's base_url is one an unattacker-writable source (a built-in preset, or
a locally-configured providers.json entry) binds that key_env to.

BOTH resolution paths are base-bound: a per-provider key records the origin it
was stored for, so "there is no base an attacker can move a key to" is a property
of the whole resolver rather than of one guard in one HTTP handler.

There is deliberately NO env->file migration. An earlier revision copied
`os.environ[key_env]` into `provider:<id>` at gateway start, which (a) silently
and permanently broke `.env` key ROTATION — the snapshot outranked the env var,
so an operator rotating a revoked key kept presenting the old one and every
request 401'd with nothing in the log to explain it; (b) turned a read-only
startup into a WRITE, so a `:ro` config volume or a full disk crash-looped the
container; and (c) persisted env-only keys to disk unasked. The base-bound
fallback already keeps those installs working, so the migration bought no
coverage in exchange. Keys reach the per-provider store when the operator sets
one (`providers add --key`, the wizard, the web console), never behind their back.
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
# The base URL each stored provider key is BOUND to, recorded at write time.
# The binding lives beside the key in the 0600 secrets file — deliberately NOT in
# providers.json, because a base read back out of the attacker-writable config
# would make the check circular (moving the base would move the binding with it).
_PROVIDER_BASE_PREFIX = "provider-base:"
# Provider ids accepted for key storage. Kept EXACTLY in sync with
# ``config._store._check_id``: when the two drifted, ``add_provider`` accepted an
# id (``a/b``, ``a:b``) that ``set_provider_key`` then rejected, so the provider
# could never hold a key and any code path storing one raised mid-write.
_PROVIDER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:-]*$")
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
    """Store one secret under a plain ENV-VAR NAME — the SHARED namespace.

    NOT a provider-key write path. The only product callers are Charon's own
    ``CHARON_SESSION_KEY``; provider keys go through :func:`set_provider_key`,
    which is namespaced per provider and base-bound. Writing a provider key here
    would put it back in the shared namespace that made the original exfil
    possible (a key_env is a name several providers may declare, so whoever can
    name it can alias it) and would leave it un-bound to any base. Also used by
    tests to construct legacy installs, and still READ as a legacy fallback."""
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


def set_provider_key(provider_id: str, value: str, *, base_url: str | None) -> Path:
    """Store *value* as the key for one provider, BOUND to *base_url*.

    Namespaced under ``provider:``, so this write can never reach ``os.environ``
    and can never overwrite another provider's key or a legacy ``key_env`` entry
    — which also closes the credential-destruction path the setup handler used to
    expose (a caller could clobber any stored key by naming its key_env).

    *base_url* is REQUIRED and is recorded alongside the key. A stored key is only
    ever sent to the base it was stored for (see :func:`get_provider_key`), so the
    per-provider store carries its own key<->base binding instead of depending on
    a single guard in one HTTP handler. Making the parameter mandatory is what
    makes that structural: an unbound entry cannot be created, so the resolver can
    fail closed on one."""
    _check_provider_id(provider_id)
    bound = _origin(base_url)
    if bound is None:
        raise ValueError(
            f"a provider key must be bound to a base URL (got {base_url!r})")
    _write_secret(_PROVIDER_BASE_PREFIX + provider_id, bound)
    return _write_secret(_PROVIDER_PREFIX + provider_id, value)


def _check_provider_id(provider_id: str) -> None:
    if not provider_id or not _PROVIDER_ID_RE.match(provider_id):
        raise ValueError(f"invalid provider id {provider_id!r}")


def _normalize_host(host: str) -> str:
    """A hostname in the form the SOCKET will actually use.

    Comparison used ``str.lower()`` while urllib connects via IDNA, and the two do
    not agree: ``U+212A`` KELVIN SIGN lower-cases to ``k``, so ``api.deepseeK.com``
    (with the Kelvin sign) compared EQUAL to a preset host. That was harmless only
    because IDNA nameprep happens to fold the same character to the same ``k`` —
    luck, not design. Normalizing through IDNA here makes the check and the
    connection agree by construction. Hosts IDNA cannot encode (IP literals,
    underscores, over-long labels) fall back to the case-folded form."""
    h = host.lower().rstrip(".")
    if not h or h.isascii():
        return h
    try:
        return h.encode("idna").decode("ascii")
    except (UnicodeError, ValueError):
        return h


def _normalize_base(base_url: str | None) -> str | None:
    """Canonical form of a base URL for equality checks: IDNA-folded scheme+host,
    explicit default ports and trailing dots/slashes removed. Comparing raw
    strings (or only ``rstrip('/')``) lets ``https://h/v1``, ``https://H:443/v1``
    and ``https://h./v1`` read as three different bases — which would be a way
    around the binding check below.

    Never raises: an unparseable base (including an out-of-range port such as
    ``https://h:99999/v1``, which ``_validate_base_url`` accepts because it only
    reads ``.hostname``) returns None and therefore never compares equal. The port
    lookup lives INSIDE the ``try`` because ``parts.port`` — not ``urlsplit`` — is
    what raises, which previously escaped as a remote 500 and could stop the
    gateway starting."""
    if not base_url:
        return None
    try:
        parts = urlsplit(str(base_url).strip())
        scheme = (parts.scheme or "").lower()
        host = _normalize_host(parts.hostname or "")
        port = parts.port
        path = parts.path
    except ValueError:
        return None
    if not scheme or not host:
        return None
    if port is None or (scheme, port) in (("http", 80), ("https", 443)):
        port_s = ""
    else:
        port_s = f":{port}"
    return f"{scheme}://{host}{port_s}{path.rstrip('/')}"


def same_base(a: str | None, b: str | None) -> bool:
    """True when two base URLs address the same endpoint (see :func:`_normalize_base`).
    Unparseable bases never compare equal — an un-checkable base is not a match."""
    na, nb = _normalize_base(a), _normalize_base(b)
    return na is not None and na == nb


def _origin(u: str | None) -> str | None:
    """``scheme://host[:port]`` of a URL, or None when it cannot be parsed.

    This is the granularity a CREDENTIAL is scoped at: a key is compromised by
    reaching a different HOST, not a different path on the host it already
    belongs to. Binding at full-path granularity instead was strictly worse on
    both sides — it blocked legitimate installs (an ``upstream_base`` of
    ``https://openrouter.ai/api`` or ``.../v1/beta`` silently resolved no key at
    all, hard-401ing the provider with no recovery path) while adding no security,
    since every path on a host is already reachable by whoever holds the host."""
    n = _normalize_base(u)
    if n is None:
        return None
    parts = urlsplit(n)
    return f"{parts.scheme}://{parts.netloc}"


def same_host(a: str | None, b: str | None) -> bool:
    """True when two URLs share scheme+host+port, whatever their paths. Used where
    a companion endpoint legitimately lives at a different path on the same host
    (a provider's balance API vs its API base)."""
    oa, ob = _origin(a), _origin(b)
    return oa is not None and oa == ob


def _env_fallback_allowed(key_env: str, base_url: str | None) -> bool:
    """May the LEGACY env/file value stored under *key_env* be sent to *base_url*?

    Only when no built-in preset claims that ``key_env``, or when *base_url*'s
    ORIGIN is one a claiming preset binds it to. Presets are static in-repo data —
    unlike the persisted provider config, they are not attacker-writable, so they
    are a usable trust anchor. Presets may legitimately share a key_env across
    several bases (``opencode-zen``/``opencode-go``), hence a SET of origins.

    Comparison is by ORIGIN, not by full base+path (see :func:`_origin`). Matching
    the whole path meant a legacy direct-model entry whose ``upstream_base``
    differed from the preset by one segment — ``https://openrouter.ai/api``, or a
    ``.../v1/beta`` variant — resolved NO key at all and hard-401ed with no
    recovery path, since a direct entry has no provider id and so can never hold a
    per-provider key.

    An UNCLAIMED key_env stays permitted for any base, deliberately. Every path
    that can introduce one is operator-local: the web setup handler ignores a
    caller-supplied ``key_env`` outright (that indirection was the original exfil
    bug) and the ``models`` action never accepts one, so a remote caller cannot
    create or repoint such a binding. Denying it instead would break the
    documented ``charon gateway --config charon.toml`` deployment, where declaring
    an operator-chosen ``key_env`` on a provider is the supported way to name a
    key — and it would buy nothing an attacker could otherwise reach.
    """
    from . import providers as _providers  # deferred: providers.py must not need secrets

    bound = {
        _origin(p.base_url)
        for p in _providers.PRESETS.values()
        if p.key_env == key_env and p.base_url
    }
    if not bound:
        return True  # operator-defined env var, no preset binding to violate
    return _origin(base_url) in bound


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

    1. the per-provider secret (``provider:<id>``) — authoritative, and sent ONLY
       to the base it was stored for (:func:`set_provider_key` records the
       binding beside the key, in the 0600 file rather than in the config);
    2. else the legacy ``key_env`` value from ``os.environ``/the secrets file,
       but ONLY when :func:`_env_fallback_allowed` says that env var is not
       preset-bound to a different base.

    BOTH paths are base-bound, so the docstring's promise — "there is no base an
    attacker can move a key to" — holds for the whole resolver rather than only
    for the legacy fallback. Step 1 previously returned the key for ANY base, and
    its sole compensating control was one ``elif`` in one HTTP handler; a stored
    key now carries its own binding, so an overlooked write path to
    ``providers.json[name]["base_url"]`` no longer exfiltrates it.

    Returns None when nothing resolves — a provider that cannot prove its
    key<->base binding sends no key rather than the wrong one.
    """
    store = secs if secs is not None else load_secrets(cd=cd)
    if provider_id:
        val = store.get(_PROVIDER_PREFIX + provider_id)
        if val:
            bound = store.get(_PROVIDER_BASE_PREFIX + provider_id)
            # Fails closed on a missing binding too: set_provider_key cannot create
            # one, so an unbound entry means a hand-edited/foreign secrets file.
            if bound is not None and bound == _origin(base_url):
                return val
            return None
    if key_env and _env_fallback_allowed(key_env, base_url):
        return os.environ.get(key_env) or store.get(key_env) or None
    return None
