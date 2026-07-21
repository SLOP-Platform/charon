"""Provider config store — load/save providers + add/remove."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ._store import _check_id, _load, _save, _validate_base_url

_FUNDING_CLASSES = {1, 2, 3, 4}
_FUNDING_CLASS_LABELS: dict[int, str] = {1: "free-recurring", 2: "flat-sub",
                                          3: "drain-then-park", 4: "payg"}

_FREE_TIER_RATE_KEYS = ("rpm", "rpd", "tpm", "tpd")
_FREE_TIER_EXTRA_KEYS = ("weekly_tokens", "monthly_tokens")
_FREE_TIER_RESET_KINDS = ("rolling", "calendar")
_FREE_TIER_KEYS = (
    *_FREE_TIER_RATE_KEYS,
    *_FREE_TIER_EXTRA_KEYS,
    "reset",
    "reset_anchor",
)


def load_providers(*, config_dir: str | Path | None = None) -> dict:
    return _load("providers.json", config_dir=config_dir)


def _check_free_tier_limit(name: str, value: Any) -> int:
    """Return ``value`` as a strictly non-negative int or raise ValueError.

    Rejects bool (Python's bool is an int subclass but never a meaningful
    rate limit), floats, strings, and negatives.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"free_tier.{name} must be a non-negative int, got {value!r}")
    if value < 0:
        raise ValueError(
            f"free_tier.{name} must be a non-negative int, got {value!r}")
    return value


def _validate_reset_anchor(reset: str, anchor: Any) -> dict:
    """Validate the optional ``reset_anchor`` for a given ``reset`` kind.

    * ``rolling`` — anchor is ignored (still permitted but unused).
    * ``calendar`` — anchor may be:
        - a string ``"HH:MM"`` (UTC time of day)
        - a string weekday name (``"mon"``..``"sun"``) for weekly resets
        - an int 1..31 (day-of-month) for monthly resets
      If absent, defaults to UTC midnight (anchor is left unset so downstream
      code treats the reset boundary as 00:00 UTC every day).
    """
    if anchor is None:
        return {}
    if reset == "rolling":
        return {}  # anchors are meaningless for rolling windows
    # calendar: HH:MM, weekday, or day-of-month
    if isinstance(anchor, str):
        if re.match(r"^([01]\d|2[0-3]):[0-5]\d$", anchor):
            return {"time": anchor}
        weekdays = {"mon": 0, "tue": 1, "wed": 2, "thu": 3,
                    "fri": 4, "sat": 5, "sun": 6}
        low = anchor.strip().lower()[:3]
        if low in weekdays:
            return {"weekday": weekdays[low]}
        raise ValueError(
            f"free_tier.reset_anchor for calendar must be 'HH:MM' (UTC), "
            f"a weekday name, or a day-of-month int, got {anchor!r}")
    if isinstance(anchor, bool):
        raise ValueError(
            f"free_tier.reset_anchor must be 'HH:MM', a weekday, or a "
            f"day-of-month int, got {anchor!r}")
    if isinstance(anchor, int) and 1 <= anchor <= 31:
        return {"day_of_month": anchor}
    raise ValueError(
        f"free_tier.reset_anchor must be 'HH:MM' (UTC), a weekday name, or "
        f"a day-of-month int, got {anchor!r}")


def _normalize_free_tier_block(block: Any) -> dict:
    """Validate a ``free_tier`` block and return the normalized dict.

    Accepts a dict (from JSON) and returns a dict with the supported keys
    only, in the schema order. The returned block is the *persisted* shape
    (rpm/rpd/tpm/tpd/weekly_tokens/monthly_tokens/reset/reset_anchor), NOT
    the QuotaTracker-shape subset — use :func:`free_tier_to_quota_limits`
    for the QuotaTracker constructor argument.
    """
    if not isinstance(block, dict):
        raise ValueError(f"free_tier must be a dict, got {type(block).__name__}")

    unknown = set(block) - set(_FREE_TIER_KEYS)
    if unknown:
        raise ValueError(
            f"free_tier has unknown keys {sorted(unknown)!r}; "
            f"allowed: {list(_FREE_TIER_KEYS)}")

    out: dict = {}
    for k in _FREE_TIER_RATE_KEYS:
        if k in block:
            out[k] = _check_free_tier_limit(k, block[k])
    for k in _FREE_TIER_EXTRA_KEYS:
        if k in block:
            out[k] = _check_free_tier_limit(k, block[k])

    if "reset" in block:
        reset = block["reset"]
        if not isinstance(reset, str) or reset not in _FREE_TIER_RESET_KINDS:
            raise ValueError(
                f"free_tier.reset must be one of "
                f"{list(_FREE_TIER_RESET_KINDS)}, got {reset!r}")
        out["reset"] = reset
        # ``calendar`` with no anchor defaults to UTC midnight — we still
        # accept the block and document the default in the docstring; the
        # default is applied at read time by leaving ``reset_anchor`` unset.
        if "reset_anchor" in block:
            anchor_norm = _validate_reset_anchor(reset, block["reset_anchor"])
            if anchor_norm:  # rolling with anchor → anchor is meaningless
                out["reset_anchor"] = anchor_norm
    elif "reset_anchor" in block:
        # anchor without a reset kind is meaningless
        raise ValueError(
            "free_tier.reset_anchor requires free_tier.reset to be set")

    return out


def _free_tier_to_quota_limits(free_tier: dict) -> dict:
    """Project a normalized free_tier block to the QuotaTracker inner shape.

    QuotaTracker consumes ``{rpm, tpm, rpd, tpd}`` ints (others ignored
    after the ``_DEFAULT_LIMITS`` merge). Weekly/monthly token budgets and
    reset-kind metadata are NOT part of QuotaTracker's sliding-window model
    and are intentionally dropped from the projection.

    Note: underscore-prefixed because the ``charon.config`` package facade
    is owned by a different ticket. Downstream consumers (FT-WIRE) should
    import directly from this submodule:
        ``from charon.config.providers import _free_tier_to_quota_limits``
    """
    out: dict = {}
    for k in _FREE_TIER_RATE_KEYS:
        if k in free_tier:
            out[k] = free_tier[k]
    return out


def _load_free_tier_limits(*, config_dir: str | Path | None = None) -> dict:
    """Return a ``{provider: {rpm/tpm/rpd/tpd...}}`` dict for QuotaTracker.

    Providers with no ``free_tier`` block (the common case) are omitted.
    A provider with an empty free_tier block (no rate keys) is also omitted
    (no limits == unlimited == no entry). The shape matches
    ``QuotaTracker(limits=...)`` exactly so FT-WIRE can pass the result
    through with no adapter.

    Note: underscore-prefixed because the ``charon.config`` package facade
    is owned by a different ticket. Downstream consumers (FT-WIRE) should
    import directly from this submodule:
        ``from charon.config.providers import _load_free_tier_limits``
    """
    provs = load_providers(config_dir=config_dir)
    out: dict = {}
    for name, entry in provs.items():
        if not isinstance(entry, dict):
            continue
        ft = entry.get("free_tier")
        if not isinstance(ft, dict):
            continue
        projected = _free_tier_to_quota_limits(ft)
        if projected:
            out[name] = projected
    return out


def add_provider(name: str, *, base_url: str | None = None, key_env: str | None = None,
                 strip_v1: bool | None = None, downgrade_prone: bool | None = None,
                 max_context: int | None = None, max_concurrency: int | None = None,
                 funding_class: int | None = None,
                 starting_balance: float | None = None,
                 mode: str | None = None,  # "poll" | "fixed"
                 balance_base_url: str | None = None,
                 balance_key_env: str | None = None,
                 balance_ttl: int | None = None,
                 free_tier: dict | None = None) -> Path:
    """Persist a provider override (base_url/key_env/quirks) to ``providers.json`` so
    a custom provider works without hand-edited config. Merges into any existing
    entry. Stores no secret value.

    DRAIN-AND-PARK fields (all optional; absent → provider inert):
    * ``funding_class`` — 1=free-recurring, 2=flat-sub, 3=drain-then-park prepaid, 4=PAYG
    * ``starting_balance`` — USD float for fixed-mode drain tracking
    * ``mode`` — ``"poll"`` (balance API) or ``"fixed"`` (starting_balance minus metered spend)
    * ``balance_base_url`` — balance API base URL (poll mode)
    * ``balance_key_env`` — env var holding the balance API key (poll mode)
    * ``balance_ttl`` — poll cache TTL in seconds (default 300)

    FREE-TIER block (optional; absent → no limits → QuotaTracker treats the
    provider as unlimited). When present, must be a dict with any of:
    ``rpm, rpd, tpm, tpd`` (non-negative ints), ``weekly_tokens,
    monthly_tokens`` (non-negative ints), ``reset`` (``"rolling"`` or
    ``"calendar"``), and ``reset_anchor`` (optional; for ``calendar`` a
    ``"HH:MM"`` UTC time, a weekday name, or a 1..31 day-of-month int; for
    ``rolling`` ignored). A ``calendar`` reset with no anchor defaults to
    UTC midnight. The persisted block is read back via
    :func:`load_free_tier_limits` and projected to the QuotaTracker
    ``{provider: {rpm/tpm/rpd/tpd}}`` shape — no adapter required.
    """
    _check_id("provider", name)
    if base_url is not None:
        _validate_base_url(str(base_url))
    if key_env is not None and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(key_env)):
        raise ValueError(f"invalid key-env name {key_env!r}")
    # The balance fields are a SECOND key<->base indirection (balance.py polls
    # balance_base_url with the balance_key_env key) and used to be persisted
    # with no validation at all — unlike base_url. Same guards, same reasons.
    if balance_base_url is not None:
        _validate_base_url(str(balance_base_url))
    if balance_key_env is not None and not re.match(
            r"^[A-Za-z_][A-Za-z0-9_]*$", str(balance_key_env)):
        raise ValueError(f"invalid balance key-env name {balance_key_env!r}")
    if funding_class is not None and funding_class not in _FUNDING_CLASSES:
        raise ValueError(
            f"funding_class must be one of {sorted(_FUNDING_CLASSES)}, "
            f"got {funding_class}")
    if mode is not None and mode not in ("poll", "fixed"):
        raise ValueError(f"mode must be 'poll' or 'fixed', got {mode!r}")
    if free_tier is not None:
        # normalize first so validation errors are raised before we touch disk
        free_tier = _normalize_free_tier_block(free_tier)
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
    # FREE-TIER block: write only if the caller provided one. ``None`` is a
    # back-compat no-op (existing providers keep their previous free_tier
    # entry, if any; providers without one stay unconfigured).
    if free_tier is not None:
        entry["free_tier"] = free_tier
    provs[name] = entry
    return _save("providers.json", provs)
