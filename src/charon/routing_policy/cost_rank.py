"""Cost-rank derivation (SR-6) — moved from ``charon.pools.derived_cost_rank``.

Wave 2 (COST-RANK-AUTO) extended this module with automatic per-provider
cost-rank computation from live pricing data.

DELETE-STATIC-RANK (ADR-0016 step #6): the hand-typed ``cost_rank`` integer
is REMOVED as a config input. Ordering is ALWAYS derived from live/sourced/
meter price — a magnitude a hand-typed scalar could never be trusted to keep
in sync with.  See ``docs/adr/0016-demand-driven-capability-match.md``.
"""
from __future__ import annotations

import warnings

# Order: cheaper funding classes first.  Matches _COST_CLASSES in config.py
# ("free-daily", "expiring", "prepaid", "metered", "premium").
_COST_CLASS_PRIORITY: dict[str, int] = {
    "free-daily": 0,
    "expiring": 1,
    "prepaid": 2,
    "metered": 3,
    "premium": 4,
}

# One-release deprecation window (ADR-0016 Consequences): an external config
# that still stamps ``cost_rank`` is no longer honored, but the validator
# warns so operators see a clean signal during migration.
_DEPRECATION_WINDOW_RELEASES = 1


def _warn_static_cost_rank_deprecated(spec: dict) -> None:
    """Emit a one-release deprecation warning when an external config still
    sets ``cost_rank``. ADR-0016 step #6: the hand-typed integer is no longer
    a config INPUT — ordering derives from live/sourced/meter price only.
    The warning is the migration signal operators see while the .60 deploy
    purges the field from ``models.json``."""
    cr = spec.get("cost_rank")
    if cr is None:
        return
    model_id = spec.get("id") or spec.get("model") or "<unknown>"
    warnings.warn(
        f"cost_rank={cr!r} on model {model_id!r} is deprecated and IGNORED "
        f"(ADR-0016 step #6). Ordering is now derived from "
        f"cost_input/cost_output + the live meter; remove the field from "
        f"models.json to silence this warning.",
        DeprecationWarning,
        stacklevel=3,
    )


def cost_class_priority(spec: dict) -> int:
    """Return the sort priority for *spec*'s ``cost_class``.

    Lower = preferred (cheaper funding class first).  Unknown / missing values
    return the highest priority (``premium``) so unclassified entries sort
    last and never accidentally float above known classes.
    """
    cc = spec.get("cost_class")
    if isinstance(cc, str):
        return _COST_CLASS_PRIORITY.get(cc.strip().lower(), 4)
    return 4


def derived_cost_rank(spec: dict, metered_cost: float | None = None) -> int:
    """SR-6 + R5: derive cost_rank from per-token pricing (3:1 in:out blend).

    ADR-0016 step #6: a hand-typed ``cost_rank`` override is NO LONGER
    honored.  Ordering is ALWAYS derived from live/sourced/meter price — the
    source of truth that a hand-set integer can never be trusted to track.
    An external config that still stamps ``cost_rank`` emits a
    ``DeprecationWarning`` (one-release migration window) but the integer is
    ignored for ordering.

    If *metered_cost* is provided (live per-(model,provider) cost from the R4
    meter), it is used directly as the authoritative cost figure.  When absent
    (no traffic yet), the configured ``cost_input`` / ``cost_output`` pricing
    is used.  Falls back to a neutral 1000 when neither is set.
    """
    if spec.get("cost_rank") is not None:
        _warn_static_cost_rank_deprecated(spec)

    # R5: prefer live metered cost when available
    if metered_cost is not None:
        return max(0, round(float(metered_cost) * 1_000_000 * 100))

    ci = spec.get("cost_input")
    co = spec.get("cost_output")
    if ci is None and co is None:
        return 1000  # missing-pricing fallback: neutral middle rank
    ci = float(ci) if ci is not None else 0.0
    co = float(co) if co is not None else 0.0
    blended = (3.0 * ci + co) / 4.0
    return max(0, round(blended * 1_000_000 * 100))


# ─────────────────────────────────────────────────────────────────────────────
# PRICED-COMPLETENESS GUARD (ADR-0016 deploy-safety, ADR0016-DEPLOY-PRICED-COMPLETENESS)
#
# DELETE-STATIC-RANK removed the operator's hand-typed ``cost_rank`` escape
# hatch.  With it gone, a model that lacks ``cost_input`` / ``cost_output``
# silently collapses to the fixed ``1000`` fallback (see above) — a
# deterministic but unbounded neutral middle rank.  In a pool where a priced
# model also derives to ~1000 (or is genuinely expensive), the stable sort
# tie-breaks on config-insertion order, which can route to the unpriced (and
# potentially PRICIER at the upstream) provider.  The operator override that
# previously could correct a bad derived order was removed
# (routing_policy/__init__.py), and nothing guaranteed priced-completeness.
#
# The preflight is the guard that prevents the unsafe deploy state: any model
# that is enabled and not free MUST carry per-token pricing.  The guard names
# every offender so the operator can fix the data (price it / disable it /
# mark it free) and holds the ``cost_rank`` purge from going live on .60
# until the catalog is clean.  See
# ``docs/review-log/ADR0016-DEPLOY-PRICED-COMPLETENESS.md``.
# ─────────────────────────────────────────────────────────────────────────────


class PricedCompletenessError(RuntimeError):
    """Raised when a live catalog has enabled, non-free models missing
    ``cost_input`` / ``cost_output``.

    The purge of ``cost_rank`` from ``/data/models.json`` (DELETE-STATIC-RANK
    deploy step) must not ship a routing table where an unpriced model
    silently collapses to the 1000 fallback.  The error message lists every
    offender; the deploy is held until the catalog is clean.
    """


def _is_unpriced(spec: dict) -> bool:
    """True iff *spec* is enabled, not free, and has no per-token pricing.

    A disabled model (``enabled: false``) is exempt — operators explicitly
    staged it out of the routing table.  A ``free: true`` model is exempt
    — the router sorts it first regardless of cost.  Everything else must
    carry at least one of ``cost_input`` / ``cost_output`` (a model with
    only one side is priced from the missing side's zero).
    """
    if not isinstance(spec, dict):
        return False
    if spec.get("enabled") is False:
        return False
    if bool(spec.get("free", False)):
        return False
    ci = spec.get("cost_input")
    co = spec.get("cost_output")
    return ci is None and co is None


def find_unpriced_models(registry: dict) -> list[str]:
    """Return the model ids in *registry* that are unpriced per the guard
    contract (enabled, not free, and missing both ``cost_input`` and
    ``cost_output``).  Order is the registry's iteration order — stable so
    the error message is reproducible across runs."""
    if not isinstance(registry, dict):
        return []
    return [mid for mid, spec in registry.items() if _is_unpriced(spec)]


def assert_priced_completeness(registry: dict) -> None:
    """Loud preflight: raise :class:`PricedCompletenessError` naming every
    unpriced model in *registry*.

    This is the deploy-safety guard for the DELETE-STATIC-RANK ``cost_rank``
    purge.  It MUST be run before purging ``cost_rank`` from
    ``/data/models.json`` so no enabled, non-free model can silently
    collapse to the 1000 fallback.  Disabled and free models are exempt.

    The error message names each offender and the three deploy-safe
    remediations (price it, mark it free, or disable it).  The deploy
    pipeline should treat this as a hard preflight failure.
    """
    offenders = find_unpriced_models(registry)
    if not offenders:
        return
    listed = ", ".join(sorted(offenders))
    raise PricedCompletenessError(
        f"PRICED-COMPLETENESS preflight FAILED: {len(offenders)} live model(s) "
        f"lack cost_input/cost_output and would silently collapse to the "
        f"fixed 1000 cost_rank fallback (DELETE-STATIC-RANK removed the "
        f"hand-typed cost_rank override that previously could correct a "
        f"bad derived order). Offenders: {listed}. "
        f"Remediation: (a) set cost_input + cost_output from a sourced "
        f"price table (see pricing_limits_checker), or (b) set "
        f"free: true if the model is genuinely zero-cost, or (c) set "
        f"enabled: false to remove it from the routing table. Do NOT "
        f"purge cost_rank from /data/models.json until this is clean."
    )
