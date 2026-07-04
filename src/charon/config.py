"""User-local gateway config (providers / models / pools) in ``config_dir()``.

The single writer shared by the `charon providers`/`charon setup` CLI and the web
setup page, and the config the gateway reads by default — so adding a provider once
(CLI or browser) makes it work with no hand-edited TOML. API keys are NOT stored
here; they live in ``secrets.json`` (see :mod:`charon.secrets`). This file holds only
non-secret config: base URLs, ``key_env`` references, model maps, pools.
"""
from __future__ import annotations

import enum
import json
import os
import re
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from . import secrets


class SandboxPolicy(enum.StrEnum):
    """Worker sandbox posture (D013 / ADR-0010).

    ``hybrid``   — default; host OK for ≤L1, container or loud override required for L2+.
    ``container`` — ALL rungs ≥L1 require the verified container; uncontained override refused.
    ``host``      — host is declared; L0/L1 free; L2+ requires the loud override flag
                    (container flag alone is not sufficient — explicit acknowledgement required).
    """

    HYBRID = "hybrid"
    CONTAINER = "container"
    HOST = "host"


_SANDBOX_ENV = "CHARON_SANDBOX"


def load_sandbox_policy(env: Mapping[str, str] | None = None) -> SandboxPolicy:
    """Read the active sandbox policy from ``CHARON_SANDBOX`` (or ``env``).

    Unknown values fall back to ``hybrid`` so a misconfigured var never silently
    weakens the gate — it reverts to the safe default."""
    e = os.environ if env is None else env
    raw = e.get(_SANDBOX_ENV, SandboxPolicy.HYBRID.value).lower()
    try:
        return SandboxPolicy(raw)
    except ValueError:
        return SandboxPolicy.HYBRID


# --------------------------------------------------------------- auto-land (ADR-0012)
# The opt-in, batch-atomic auto-land surface. Default is OFF: with nothing
# configured, ``load_autoland_config`` returns ``enabled=False`` and the land
# path stays propose-default (a human merges every unit). The switch + allowlist
# are read from OUTSIDE any worktree (this engine-owned config / ``CHARON_AUTOLAND``)
# so a unit can never enable its own auto-land or widen its own allowlist by
# editing a repo file (ADR-0012 D1 / privilege-escalation lens).
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


def _as_str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(v for v in value if isinstance(v, str) and v.strip())


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


def load_providers(*, config_dir: str | Path | None = None) -> dict:
    return _load("providers.json", config_dir=config_dir)


def load_models(*, config_dir: str | Path | None = None) -> dict:
    return _load("models.json", config_dir=config_dir)


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
              free: bool = False, cost_rank: int = 1000,
              context_window: int | None = None, max_tokens: int | None = None,
              reasoning: bool | None = None, vision: bool | None = None,
              audio: bool | None = None,
              cost_input: float | None = None, cost_output: float | None = None) -> Path:
    """Persist a model to ``models.json`` (references a provider, or a direct
    upstream_base). Optional metadata fields (context_window, max_tokens,
    reasoning, vision, audio, cost_input, cost_output) are persisted only when non-None."""
    _check_id("model", model_id)
    if provider is None and upstream_base is None:
        raise ValueError("a model needs either provider= or upstream_base=")
    models = load_models()
    entry: dict = {"free": bool(free), "cost_rank": int(cost_rank)}
    for k, v in (("provider", provider), ("upstream_base", upstream_base),
                 ("upstream_model", upstream_model), ("key_env", key_env)):
        if v is not None:
            entry[k] = v
    for k, mv in (("context_window", context_window), ("max_tokens", max_tokens),
                   ("reasoning", reasoning), ("vision", vision), ("audio", audio),
                   ("cost_input", cost_input), ("cost_output", cost_output)):
        if mv is not None:
            entry[k] = mv
    models[model_id] = entry
    return _save("models.json", models)


def add_models_bulk(entries: list[dict], *, provider: str) -> tuple[list[str], list[str]]:
    """Add many catalog models for one provider in a SINGLE atomic write (the
    `charon models import` path). Each entry is ``{id, free?, cost_rank?}``; the
    catalog id doubles as the upstream id (no ``upstream_model``). Ids failing
    ``_ID_RE`` are SKIPPED (not raised — an upstream list is untrusted). Optional
    metadata fields (context_window, max_tokens, reasoning, vision, audio,
    cost_input, cost_output) are carried through if present. Returns ``(added, skipped)``."""
    _check_id("provider", provider)
    _METADATA_KEYS = ("context_window", "max_tokens", "reasoning", "vision", "audio",
                      "cost_input", "cost_output")
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
        for k in _METADATA_KEYS:
            v = e.get(k)
            if v is not None:
                models[mid][k] = v
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


# --------------------------------------------------------------- tiers (DTC tier-abstraction)
# The model-tier store: ONE canonical vocabulary ``low/med/high`` (``types.Tier``);
# ``opus/sonnet/haiku`` + ``frontier/strong/economy`` are ALIASES only. Canonical keys
# are FIXED (so ``capacity.FixedCap`` keys never desync); only ``members`` and ``aliases``
# are operator-editable. The store is a tiny OPTIONAL ``tiers.json`` in ``config_dir()``:
# ``{order:[...], members:{tier:[model_id,...]}, aliases:{name:tier}}`` where members are
# model ids ALREADY in ``models.json`` (reuse the registry — no new schema, no DB, no
# migration runner). Absent file → legacy behavior: ``opus/sonnet/haiku`` mapped to
# ``high/med/low`` with ranks ``opus=3 sonnet=2 haiku=1`` (= 1-based ``order`` index).
_TIERS_FILE = "tiers.json"
CANONICAL_TIERS: tuple[str, ...] = ("low", "med", "high")
# Legacy/synonym name → canonical tier (the backward-compat seam). Seeded into a fresh
# ``tiers.json`` and used as a fallback when a recognized synonym is missing from the file.
_LEGACY_ALIASES: dict[str, str] = {
    "opus": "high", "sonnet": "med", "haiku": "low",
    "frontier": "high", "strong": "med", "economy": "low",
}
# Day-one == today: each tier seeds the single matching Anthropic model.
_LEGACY_MEMBERS: dict[str, list[str]] = {"low": ["haiku"], "med": ["sonnet"], "high": ["opus"]}


def _legacy_tiers() -> dict:
    """The absent-file default: canonical order + legacy aliases + one Anthropic model
    per tier, so behavior matches the pre-abstraction ``opus/sonnet/haiku`` world."""
    return {
        "order": list(CANONICAL_TIERS),
        "members": {t: list(ms) for t, ms in _LEGACY_MEMBERS.items()},
        "aliases": dict(_LEGACY_ALIASES),
    }


def load_tiers() -> dict:
    """Parsed ``tiers.json`` (normalized to canonical keys), or the legacy default when
    the file is absent/empty. Always returns ``{order, members, aliases}`` with ``order``
    a subset of the canonical tiers and ``members`` keyed by every tier in ``order``."""
    data = _load(_TIERS_FILE)
    if not data:
        return _legacy_tiers()
    order = [t for t in data.get("order", []) if t in CANONICAL_TIERS]
    if not order:
        order = list(CANONICAL_TIERS)
    raw_members = data.get("members") or {}
    members = {t: list(_as_str_tuple(raw_members.get(t))) for t in order}
    raw_aliases = data.get("aliases")
    if not isinstance(raw_aliases, Mapping):
        raw_aliases = {}
    aliases = {
        str(name).strip().lower(): tier
        for name, tier in raw_aliases.items()
        if isinstance(tier, str) and tier in CANONICAL_TIERS
    }
    return {"order": order, "members": members, "aliases": aliases}


def set_tiers(order: Sequence[str], members: Mapping[str, Sequence[str]],
              aliases: Mapping[str, str]) -> Path:
    """Atomically persist ``tiers.json`` (reuses the ``_save`` pattern). ``order`` must be
    exactly the canonical tiers ``low/med/high`` (a permutation); member ids must pass
    ``_ID_RE``; alias targets must be canonical. Member existence in ``models.json`` is
    NOT enforced here — the gateway reuses the registry at compile time."""
    order = list(order)
    bad = [t for t in order if t not in CANONICAL_TIERS]
    if bad:
        raise ValueError(f"non-canonical tier(s) in order: {bad}")
    if set(order) != set(CANONICAL_TIERS):
        raise ValueError("order must contain exactly the canonical tiers low/med/high")
    out_members: dict[str, list[str]] = {}
    for t in order:
        ms = list(members.get(t, []))
        invalid = [m for m in ms if not isinstance(m, str) or not _ID_RE.match(m)]
        if invalid:
            raise ValueError(f"invalid model id(s) in tier {t!r}: {invalid}")
        out_members[t] = ms
    out_aliases: dict[str, str] = {}
    for name, tier in aliases.items():
        if tier not in CANONICAL_TIERS:
            raise ValueError(f"alias {name!r} targets non-canonical tier {tier!r}")
        out_aliases[str(name).strip().lower()] = tier
    return _save(_TIERS_FILE, {"order": order, "members": out_members, "aliases": out_aliases})


def resolve_tier(name: str, tiers: Mapping | None = None) -> str:
    """Fold ``name`` (case-insensitive) to a canonical tier. Canonical names pass through;
    file aliases then legacy synonyms map to canonical. Unknown names raise ``ValueError``."""
    t = load_tiers() if tiers is None else tiers
    key = str(name).strip().lower()
    if key in CANONICAL_TIERS:
        return key
    file_aliases = t.get("aliases") or {}
    if key in file_aliases:
        return file_aliases[key]
    if key in _LEGACY_ALIASES:  # safety net even if the file dropped a known synonym
        return _LEGACY_ALIASES[key]
    raise ValueError(f"unknown tier {name!r}")


def tier_members(tier: str, tiers: Mapping | None = None) -> list[str]:
    """The ordered member model ids for a (resolved) tier. Within-tier order is the stored
    member order; the gateway later applies free-first→cost_rank (not this layer's concern)."""
    t = load_tiers() if tiers is None else tiers
    canon = resolve_tier(tier, t)
    return list((t.get("members") or {}).get(canon, []))


def tier_rank(name: str, tiers: Mapping | None = None) -> int:
    """1-based rank of a tier within ``order`` (alias-folded): ``low=1 med=2 high=3``,
    so legacy ``opus=3 sonnet=2 haiku=1`` falls out for free. Unknown names → ``0``."""
    t = load_tiers() if tiers is None else tiers
    try:
        canon = resolve_tier(name, t)
    except ValueError:
        return 0
    order = t.get("order") or list(CANONICAL_TIERS)
    return order.index(canon) + 1 if canon in order else 0


def remove(kind: str, name: str) -> bool:
    """Remove a provider/model/pool by name. Returns True if it existed."""
    fname = {"provider": "providers.json", "model": "models.json", "pool": "pools.json"}[kind]
    data = _load(fname)
    if name in data:
        del data[name]
        _save(fname, data)
        return True
    return False


_VALIDATE_TIMEOUT = 15.0
_VALIDATE_UA = "charon-proxy/0.1"


def validate_provider_key(name: str, base_url: str | None, api_key: str) -> dict:
    """Probe a provider with a real chat-completion request to validate the key.
    Returns ``{valid, message, models_count}`` — never echoes the key. On success
    also returns the number of models available (if /models is reachable).

    Security: non-http(s) bases and link-local/metadata hosts are refused (SSRF
    guard). Redirects are disabled (no cross-host key leak)."""
    parts = urlsplit(base_url or "")
    if parts.scheme not in ("http", "https"):
        return {"valid": False, "message": f"invalid base URL scheme {parts.scheme!r}"}
    host = parts.hostname or ""
    if host.startswith("169.254.") or host == "metadata.google.internal":
        return {"valid": False, "message": "refusing link-local / metadata host"}

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):  # noqa: ANN002, ANN003
            return None

    opener = urllib.request.build_opener(_NoRedirect())
    raw_base = base_url.rstrip("/") if base_url else ""

    # Probe 1: GET /models — cheap, tells us the key works + model count
    models_count = 0
    try:
        req = urllib.request.Request(raw_base + "/models", method="GET")
        req.add_header("User-Agent", _VALIDATE_UA)
        req.add_header("Authorization", "Bearer " + api_key)
        resp = opener.open(req, timeout=_VALIDATE_TIMEOUT)
        raw = resp.read(200_000)
        data = json.loads(raw.decode("utf-8", "replace"))
        items = data.get("data") if isinstance(data, dict) else data
        if isinstance(items, list):
            models_count = len(items)
    except Exception:
        pass  # fall through to the completion probe

    # Probe 2: POST /chat/completions — universal fallback
    try:
        body = json.dumps({
            "model": ".",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
        }).encode()
        req = urllib.request.Request(raw_base + "/chat/completions", data=body, method="POST")
        req.add_header("User-Agent", _VALIDATE_UA)
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + api_key)
        resp = opener.open(req, timeout=_VALIDATE_TIMEOUT)
        resp.read(1024)
        return {"valid": True, "message": "key validated — chat probe succeeded",
                "models_count": models_count}
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return {"valid": False, "message": f"key rejected (HTTP {exc.code})"}
        return {"valid": False, "message": f"probe failed (HTTP {exc.code})"}
    except Exception:  # noqa: BLE001
        if models_count > 0:
            # /models worked but /completions didn't — common for some APIs
            return {"valid": True, "message": "key validated via /models",
                    "models_count": models_count}
        return {"valid": False, "message": "provider unreachable or probe timed out"}


def set_model_enabled(model_id: str, enabled: bool) -> bool:
    """Toggle a model's ``enabled`` flag in ``models.json``. Returns True if the
    model existed."""
    models = load_models()
    if model_id not in models:
        return False
    models[model_id]["enabled"] = enabled
    _save("models.json", models)
    return True


_FALLBACK_FILE = "fallback.json"


def load_fallback_providers() -> list[str]:
    """Read the ordered fallback provider list from ``fallback.json``.
    Returns an empty list when the file is absent or malformed."""
    data = _load(_FALLBACK_FILE)
    fallback = data.get("providers")
    if isinstance(fallback, list):
        return [str(p).strip() for p in fallback if isinstance(p, str) and str(p).strip()]
    return []


def set_fallback_providers(providers: list[str]) -> Path:
    """Persist the ordered fallback provider list to ``fallback.json``."""
    cleaned = [str(p).strip() for p in providers if isinstance(p, str) and str(p).strip()]
    return _save(_FALLBACK_FILE, {"providers": cleaned})


def _unknown_pricing_models(models: dict) -> list[str]:
    """Models that have neither ``cost_input`` nor ``cost_output`` (and are not
    marked as free — free models are genuinely free and should not be flagged)."""
    unknown: list[str] = []
    for mid, entry in models.items():
        if entry.get("free"):
            continue
        if "cost_input" not in entry and "cost_output" not in entry:
            unknown.append(mid)
    return unknown


_FALLBACK_PRICING_FILE = "fallback_pricing.json"


def load_fallback_pricing() -> dict:
    """Read fallback per-token pricing from ``fallback_pricing.json``.
    Returns ``{}`` when the file is absent or malformed."""
    data = _load(_FALLBACK_PRICING_FILE)
    result: dict[str, float] = {}
    for k in ("cost_input", "cost_output"):
        v = data.get(k)
        if isinstance(v, (int, float)):
            result[k] = float(v)
    return result


def set_fallback_pricing(cost_input: float, cost_output: float) -> Path:
    """Persist the fallback per-token pricing to ``fallback_pricing.json``."""
    cost_input = float(cost_input)
    cost_output = float(cost_output)
    if cost_input < 0 or cost_output < 0:
        raise ValueError("fallback pricing must be non-negative")
    return _save(_FALLBACK_PRICING_FILE, {
        "cost_input": cost_input,
        "cost_output": cost_output,
    })


def summary() -> dict:
    """A non-secret view for the CLI/console: providers (with key-set state, NOT the
    key), models, pools, failover chain health, unknown-pricing models, and optional
    fallback pricing."""
    from typing import Any
    secs = secrets.load_secrets()
    provs = {}
    for n, e in load_providers().items():
        ke = e.get("key_env")
        provs[n] = {
            "base_url": e.get("base_url"),
            "key_env": ke,
            "key_set": bool(ke and (os.environ.get(ke) or ke in secs)),
        }
    models = load_models()
    result: dict[str, Any] = {"providers": provs, "models": models, "pools": load_pools()}
    result["unknown_pricing"] = _unknown_pricing_models(models)
    fallback = load_fallback_providers()
    if fallback:
        result["fallback"] = fallback
    fallback_pricing = load_fallback_pricing()
    if fallback_pricing:
        result["fallback_pricing"] = fallback_pricing
    result["failover_chain_health"] = failover_chain_health()
    return result


def failover_chain_health() -> dict:
    """Return a summary dict of failover readiness: whether pools, fallback, or
    providers are configured, and whether any failover chain exists."""
    pools = load_pools()
    fallback = load_fallback_providers()
    provs = load_providers()
    has_pools = bool(pools)
    has_fallback = bool(fallback)
    has_providers = bool(provs)
    return {
        "has_pools": has_pools,
        "has_fallback": has_fallback,
        "has_providers": has_providers,
        "pools_count": len(pools),
        "fallback_provider_count": len(fallback),
        "provider_count": len(provs),
    }
