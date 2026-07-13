"""MODEL-LIFECYCLE — the self-managing capability lifecycle orchestrator.

ONE orchestrator that composes the four already-standalone components into a
fresh-install auto-onboarding + scheduled keep-fresh loop for the model roster.
It does **not** re-implement any of them — each is reached through a clean,
dependency-injected *seam* so production wires the real component and tests
inject a mock:

    1. LINK    — provider add / key link  (fleet/add-provider.sh → ``config.add_provider``)
    2. DISCOVER— import each provider's models  (``discover``/PROVIDER-CATALOG-REFRESH)
    3. PREFLIGHT — screen NEW models (OOB-graded)  (fleet/benchmark/preflight.sh)
    4. TIER    — rank + persist trusted models  (``recommend`` + ``config.tiers``)

Two entrypoints:

* :func:`bootstrap` — fresh install (`charon setup` extension): link providers →
  discover each provider's models → preflight a PRIORITIZED, BOUNDED batch of the
  NEW models → populate the catalog (model→provider→price + cost-rank) and
  AUTO-ASSIGN tiers **for trusted (non-detained) winners only** → feed the scorecard.

* :func:`scheduled_refresh` — TTL/cron keep-fresh: re-discover → preflight ONLY
  new/changed models (INCREMENTAL — an already-screened verdict is cached and never
  re-run) → refresh the catalog → re-tier. Idempotent, off the hot path,
  stale-but-usable on failure.

SCALE (hard requirement — preflight is EXPENSIVE, ~42 sessions/model, so the roster
is NEVER screened exhaustively). Screening is prioritized+incremental+bounded:

    (1) OPERATOR-SELECTED models are screened first;
    (2) then a PRIORITIZED order — understaffed tiers first (tier NEED), then likely
        value, then cost (cheap models for economy tiers);
    (3) INCREMENTAL — a model whose verdict is already cached is never re-screened;
    (4) BOUNDED — at most ``budget_k`` models are screened per cycle.

THE GATE (the FAIL-ON-REVERT crux, see :func:`_tier_and_catalog`): a model is
tiered/catalogued **only** when its preflight verdict is ``TRUST`` and it is not
detained. Revert that check and a failing model gets tiered — the test goes RED.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("charon.lifecycle")

# ── verdict vocabulary (the preflight runner's ``trust``/``detain`` cards) ──────
TRUST = "trust"
DETAIN = "detain"

CANONICAL_TIERS: tuple[str, ...] = ("low", "med", "high")

# Default screening budget per cycle — a cycle never runs the whole roster.
DEFAULT_BUDGET_K = 8
# Default "fully staffed" member count per tier; a tier under this is understaffed
# and its candidates are prioritized for screening (tier NEED).
DEFAULT_TARGET_PER_TIER = 2


class LifecycleError(RuntimeError):
    """A lifecycle seam is unconfigured or a required component is unreachable."""


# ── data model ─────────────────────────────────────────────────────────────────


@dataclass
class ProviderSpec:
    """A provider to link during bootstrap: name + base URL + how its key is read."""

    name: str
    base_url: str
    key_env: str | None = None
    api_key: str | None = None
    strip_v1: bool = True


@dataclass
class ModelCandidate:
    """A discovered model offered by one provider, pre-screening."""

    model_id: str
    provider: str
    price: dict = field(default_factory=dict)   # cost_input / cost_output
    meta: dict = field(default_factory=dict)    # context_window, reasoning, ...
    free: bool = False

    @property
    def cost(self) -> float:
        """A single cost figure for cheap-first ordering (free → 0)."""
        if self.free:
            return 0.0
        vals = [self.price.get(k) for k in ("cost_input", "cost_output")]
        nums = [float(v) for v in vals if isinstance(v, (int, float))]
        return sum(nums) if nums else 0.0

    @property
    def value(self) -> float:
        """A crude 'likely value' figure for prioritization: context window size."""
        cw = self.meta.get("context_window")
        return float(cw) if isinstance(cw, (int, float)) else 0.0


@dataclass
class LifecycleResult:
    """Outcome of a bootstrap / scheduled_refresh cycle."""

    linked: list[str] = field(default_factory=list)
    discovered: list[str] = field(default_factory=list)
    screened: list[str] = field(default_factory=list)      # models preflighted THIS cycle
    trusted: list[str] = field(default_factory=list)        # verdict==trust & not detained
    detained: list[str] = field(default_factory=list)       # verdict==detain OR detained
    tiered: dict[str, list[str]] = field(default_factory=dict)   # tier -> [model ids] added
    cost_rank: dict[str, int] = field(default_factory=dict)      # model -> cost rank
    pending: list[str] = field(default_factory=list)        # discovered but not yet screened
    errors: list[str] = field(default_factory=list)
    stale: bool = False                                     # degraded to stale-but-usable


# ── seams (each of the four components + persistence, dependency-injected) ──────


@dataclass
class LifecycleSeams:
    """The injected component seams. Production wires the real ones via
    :func:`default_seams`; tests inject mocks. No component is re-implemented here —
    the orchestrator only *calls* these."""

    # 1. LINK — provider add / key link.
    link_provider: Callable[[ProviderSpec], None]
    # 2. DISCOVER — one provider's advertised models (raw ``/models`` dicts).
    discover: Callable[[ProviderSpec], list[dict]]
    # 3. PREFLIGHT — screen one model → ``TRUST`` / ``DETAIN`` (the EXPENSIVE step).
    preflight: Callable[[str], str]
    # 4. TIER — authoritative tier for one screened, trusted model.
    assign_tier: Callable[[ModelCandidate], str]
    # cheap pre-screen tier bucket, used ONLY to prioritize by tier NEED (not authoritative).
    estimate_tier: Callable[[ModelCandidate], str]
    # persist model→provider→price(+cost_rank, tier) into the catalog.
    catalog_put: Callable[[ModelCandidate, int, str], None]
    # persist the full tier→members map (merged) in one write.
    set_tier_members: Callable[[dict[str, list[str]]], None]
    # current tier membership, for tier-NEED accounting and idempotent merges.
    current_tier_members: Callable[[], dict[str, list[str]]]
    # DETENTION-REDLINE predicate (scorecard block-rate). Default: none detained.
    is_detained: Callable[[str], bool]
    # feed the scorecard: rows of (model, work_class, verdict).
    feed_scorecard: Callable[[list[tuple[str, str, str]]], None]
    # incremental verdict cache (persisted across cycles).
    load_verdicts: Callable[[], dict[str, str]]
    save_verdicts: Callable[[dict[str, str]], None]


# ── default (production) seam wiring — composes the REAL components ─────────────


def _unconfigured_preflight(model_id: str) -> str:
    """Fail-closed default: without a real MODEL-PREFLIGHT runner wired, refuse to
    screen (never silently 'trust'). Production injects the rig's ``preflight.sh``
    adapter — see :func:`subprocess_preflight_seam` — or an in-tree screen."""
    raise LifecycleError(
        f"no preflight seam configured — cannot screen {model_id!r}; "
        "wire the MODEL-PREFLIGHT runner (fleet/benchmark/preflight.sh) via "
        "LifecycleSeams.preflight before onboarding models"
    )


def subprocess_preflight_seam(
    script: str | Path,
    *,
    runner: Callable[[list[str]], int] | None = None,
    extra_args: Sequence[str] = (),
) -> Callable[[str], str]:
    """Build a preflight seam that shells out to the rig's ``preflight.sh``.

    Exit-code contract (preflight.sh §Exit codes): 0 → ``TRUST`` (every task cleared
    its threshold), 1 → ``DETAIN`` (>=1 task missed), anything else → the substrate
    was unreachable, which is a *fail-loud* error, NOT a pass. ``runner`` is
    injectable so this factory itself stays unit-testable without a real subprocess.
    """

    def _run(argv: list[str]) -> int:
        import subprocess

        return subprocess.call(argv)

    call = runner or _run

    def _seam(model_id: str) -> str:
        argv = [str(script), model_id, *extra_args]
        rc = call(argv)
        if rc == 0:
            return TRUST
        if rc == 1:
            return DETAIN
        raise LifecycleError(
            f"preflight runner unreachable for {model_id!r} (exit {rc}) — "
            "refusing to treat an unscreened model as trusted"
        )

    return _seam


def default_seams(
    *,
    config_dir: str | Path | None = None,
    preflight: Callable[[str], str] | None = None,
) -> LifecycleSeams:
    """Wire the seams to the real in-tree components.

    ``preflight`` MUST be supplied for a real onboarding run (the OOB grader lives
    outside the product tree); when omitted the seam is fail-closed. Everything else
    composes the shipped modules: ``config.add_provider`` (link), ``discover`` (import),
    ``recommend`` (tier), and ``config.tiers`` / ``config.add_model`` (persist).
    """
    from . import config, discover, recommend

    cd = Path(config_dir) if config_dir is not None else None
    verdict_path_holder: dict[str, Path] = {}

    def _verdict_path() -> Path:
        if "p" not in verdict_path_holder:
            from . import secrets

            base = cd if cd is not None else secrets.config_dir()
            verdict_path_holder["p"] = base / "lifecycle_verdicts.json"
        return verdict_path_holder["p"]

    def _link(spec: ProviderSpec) -> None:
        config.add_provider(spec.name, base_url=spec.base_url,
                            key_env=spec.key_env, strip_v1=spec.strip_v1)

    def _discover(spec: ProviderSpec) -> list[dict]:
        found = discover.discover_provider(spec.base_url, spec.api_key, spec.strip_v1)
        return found or []

    def _assign_tier(c: ModelCandidate) -> str:
        entry = {"id": c.model_id, "free": c.free,
                 "context_window": c.meta.get("context_window")}
        recs = recommend.recommend_tiers(c.provider, [entry], config_dir=cd)
        for r in recs:
            if c.model_id in r.model_ids:
                return r.tier
        return "med"

    def _catalog_put(c: ModelCandidate, cost_rank: int, tier: str) -> None:
        config.add_model(
            c.model_id, provider=c.provider, free=c.free, cost_rank=cost_rank,
            cost_input=_as_float(c.price.get("cost_input")),
            cost_output=_as_float(c.price.get("cost_output")),
            context_window=_as_int(c.meta.get("context_window")),
        )

    def _set_tier_members(members: dict[str, list[str]]) -> None:
        current = config.load_tiers()
        order = current.get("order") or list(CANONICAL_TIERS)
        aliases = current.get("aliases") or {}
        full = {t: list(members.get(t, [])) for t in order}
        config.set_tiers(order, full, aliases)

    def _current_members() -> dict[str, list[str]]:
        return dict(config.load_tiers().get("members") or {})

    def _feed_scorecard(rows: list[tuple[str, str, str]]) -> None:
        _default_feed_scorecard(rows, config_dir=cd)

    def _load_verdicts() -> dict[str, str]:
        p = _verdict_path()
        if not p.exists():
            return {}
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}

    def _save_verdicts(cache: dict[str, str]) -> None:
        p = _verdict_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        tmp.replace(p)

    return LifecycleSeams(
        link_provider=_link,
        discover=_discover,
        preflight=preflight or _unconfigured_preflight,
        assign_tier=_assign_tier,
        estimate_tier=_heuristic_tier,
        catalog_put=_catalog_put,
        set_tier_members=_set_tier_members,
        current_tier_members=_current_members,
        is_detained=lambda _model: False,
        feed_scorecard=_feed_scorecard,
        load_verdicts=_load_verdicts,
        save_verdicts=_save_verdicts,
    )


def _as_float(v: object) -> float | None:
    return float(v) if isinstance(v, (int, float)) else None


def _as_int(v: object) -> int | None:
    return int(v) if isinstance(v, (int, float)) else None


def _default_feed_scorecard(rows: list[tuple[str, str, str]],
                            *, config_dir: Path | None) -> None:
    """Append the cycle's trusted models to the freeze-ring scorecard."""
    if not rows:
        return
    from . import secrets
    from .capability.scorecard import ScorecardArtifact, ScorecardRow, ScorecardStore

    base = config_dir if config_dir is not None else secrets.config_dir()
    store = ScorecardStore(base / "scorecard")
    import time

    next_seq = (store.latest_seq() or 0) + 1
    artifact = ScorecardArtifact(
        seq=next_seq,
        timestamp=time.time(),
        rows=[ScorecardRow(model=m, work_class=wc, score=1.0, samples=1,
                           metadata={"verdict": v}) for m, wc, v in rows],
        metadata={"source": "lifecycle"},
    )
    store.freeze(artifact)


_HIGH_KEYS = ("claude-3.5", "claude-3-5", "claude-4", "opus", "gpt-4o", "gpt-4.5",
              "gpt-5", "gemini-2.0", "gemini-2.5", "grok-3", "deepseek-r1", "deepseek-v3")
_LOW_KEYS = ("haiku", "flash", "mini", "nano", "tiny", "8b", "7b", "3b", "1b", "0.5b")


def _heuristic_tier(c: ModelCandidate) -> str:
    """Cheap, offline tier bucket for PRIORITIZATION only (name/ctx patterns).

    This is deliberately NOT the authoritative tier decision (that is the injected
    ``assign_tier`` seam, which composes ``recommend``); it only orders candidates by
    likely tier so understaffed tiers get screened first."""
    name = c.model_id.lower()
    if any(k in name for k in _HIGH_KEYS):
        return "high"
    if any(k in name for k in _LOW_KEYS):
        return "low"
    if c.value >= 100_000:
        return "high"
    if c.free:
        return "low"
    return "med"


# ── SCALE: prioritized + incremental + bounded batching ────────────────────────


def _tier_need(current: dict[str, list[str]], target_per_tier: int) -> dict[str, int]:
    """Deficit per tier: how many more members a tier needs to be 'staffed'.
    Larger deficit → more understaffed → higher screening priority."""
    return {t: max(0, target_per_tier - len(current.get(t, [])))
            for t in CANONICAL_TIERS}


def select_batch(
    candidates: Sequence[ModelCandidate],
    *,
    verdict_cache: dict[str, str],
    tier_need: dict[str, int],
    estimate_tier: Callable[[ModelCandidate], str],
    operator_selected: Iterable[str] = (),
    budget_k: int = DEFAULT_BUDGET_K,
) -> list[ModelCandidate]:
    """Choose which models to preflight THIS cycle, implementing all four SCALE rules.

    (1) operator-selected first; (2) then prioritized by tier NEED → value → cost;
    (3) INCREMENTAL — any model already in ``verdict_cache`` is dropped (never re-run);
    (4) BOUNDED — at most ``budget_k`` models are returned.
    """
    op = list(operator_selected)
    # (3) INCREMENTAL: a cached verdict is never re-screened. De-dup by model id.
    seen: set[str] = set()
    fresh: list[ModelCandidate] = []
    for c in candidates:
        if c.model_id in verdict_cache or c.model_id in seen:
            continue
        seen.add(c.model_id)
        fresh.append(c)

    # (1) operator-selected first (preserving operator order), still incremental.
    op_rank = {mid: i for i, mid in enumerate(op)}
    selected = [c for c in fresh if c.model_id in op_rank]
    selected.sort(key=lambda c: op_rank[c.model_id])

    # (2) prioritize the rest: understaffed tier first, then higher value, then cheaper.
    rest = [c for c in fresh if c.model_id not in op_rank]

    def _priority(c: ModelCandidate) -> tuple[int, float, float, str]:
        deficit = tier_need.get(estimate_tier(c), 0)
        return (-deficit, -c.value, c.cost, c.model_id)

    rest.sort(key=_priority)

    ordered = selected + rest
    # (4) BOUNDED per cycle.
    k = max(0, int(budget_k))
    return ordered[:k]


# ── the GATE: only trusted (non-detained) winners are catalogued + tiered ───────


def _tier_and_catalog(
    screened: Sequence[ModelCandidate],
    verdict_cache: dict[str, str],
    seams: LifecycleSeams,
    result: LifecycleResult,
) -> None:
    """Apply THE preflight gate, then catalog + tier the winners.

    A model is catalogued and tiered ONLY when BOTH hold:
        * its cached preflight verdict is ``TRUST``  (the MODEL-PREFLIGHT gate), and
        * it is not detained                          (the DETENTION-REDLINE gate).

    Reverting the ``verdict == TRUST`` guard below lets a failing model through to
    tiering — which is exactly what ``tests/test_lifecycle.py`` asserts must NOT
    happen, so the revert turns the suite RED. This is the load-bearing line.
    """
    winners: list[ModelCandidate] = []
    for c in screened:
        verdict = verdict_cache.get(c.model_id)
        # ── THE GATE (revert this and the FAIL-ON-REVERT test goes RED) ──────────
        if verdict != TRUST:
            result.detained.append(c.model_id)
            continue
        if seams.is_detained(c.model_id):
            result.detained.append(c.model_id)
            continue
        winners.append(c)

    if not winners:
        return

    # cost-rank the winners (cheapest → rank 1); free models sort first.
    for rank, c in enumerate(sorted(winners, key=lambda c: (c.cost, c.model_id)), start=1):
        result.cost_rank[c.model_id] = rank

    # assign an authoritative tier to each winner (composes the tier component).
    additions: dict[str, list[str]] = {t: [] for t in CANONICAL_TIERS}
    for c in winners:
        tier = seams.assign_tier(c)
        if tier not in CANONICAL_TIERS:
            tier = "med"
        seams.catalog_put(c, result.cost_rank[c.model_id], tier)
        additions[tier].append(c.model_id)
        result.trusted.append(c.model_id)

    # merge additions onto the current membership and persist once (idempotent).
    current = seams.current_tier_members()
    merged: dict[str, list[str]] = {}
    for t in CANONICAL_TIERS:
        existing = list(current.get(t, []))
        for mid in additions[t]:
            if mid not in existing:
                existing.append(mid)
        merged[t] = existing
    seams.set_tier_members(merged)
    result.tiered = {t: list(additions[t]) for t in CANONICAL_TIERS if additions[t]}

    # feed the scorecard with the trusted winners.
    seams.feed_scorecard([(c.model_id, "onboard", TRUST) for c in winners])


# ── discovery helper ───────────────────────────────────────────────────────────


def _discover_candidates(
    providers: Sequence[ProviderSpec],
    seams: LifecycleSeams,
    result: LifecycleResult,
) -> list[ModelCandidate]:
    """Discover every provider's models into candidates. A single provider's failed
    discovery is logged and skipped (stale-but-usable) — it never aborts the cycle."""
    candidates: list[ModelCandidate] = []
    for spec in providers:
        try:
            found = seams.discover(spec)
        except Exception as exc:  # noqa: BLE001 — degrade per provider, never block
            msg = f"discover failed for provider {spec.name!r}: {type(exc).__name__}: {exc}"
            log.error(msg)
            result.errors.append(msg)
            continue
        for m in found or []:
            mid = m.get("id") if isinstance(m, dict) else None
            if not isinstance(mid, str) or not mid:
                continue
            price = {k: m[k] for k in ("cost_input", "cost_output") if k in m}
            meta = {k: m[k] for k in ("context_window", "max_tokens", "reasoning",
                                      "vision", "audio") if k in m}
            free = bool(m.get("free")) or mid.endswith(":free")
            candidates.append(ModelCandidate(mid, spec.name, price, meta, free))
            result.discovered.append(mid)
    return candidates


# ── entrypoints ────────────────────────────────────────────────────────────────


def bootstrap(
    providers: Sequence[ProviderSpec],
    *,
    seams: LifecycleSeams | None = None,
    budget_k: int = DEFAULT_BUDGET_K,
    target_per_tier: int = DEFAULT_TARGET_PER_TIER,
    operator_selected: Iterable[str] = (),
    config_dir: str | Path | None = None,
) -> LifecycleResult:
    """Fresh-install auto-onboarding (`charon setup` extension).

    LINK each provider → DISCOVER every provider's models → PREFLIGHT a prioritized,
    bounded batch of them → catalog + tier the TRUSTED (non-detained) winners → feed
    the scorecard. Screening obeys the SCALE rules (see :func:`select_batch`)."""
    sm = seams or default_seams(config_dir=config_dir)
    result = LifecycleResult()

    # 1. LINK.
    for spec in providers:
        try:
            sm.link_provider(spec)
            result.linked.append(spec.name)
        except Exception as exc:  # noqa: BLE001
            msg = f"link failed for provider {spec.name!r}: {type(exc).__name__}: {exc}"
            log.error(msg)
            result.errors.append(msg)

    # 2. DISCOVER.
    candidates = _discover_candidates(providers, sm, result)

    # 3. SELECT + PREFLIGHT (prioritized + incremental + bounded).
    verdict_cache = dict(sm.load_verdicts())
    tier_need = _tier_need(sm.current_tier_members(), target_per_tier)
    batch = select_batch(candidates, verdict_cache=verdict_cache, tier_need=tier_need,
                         estimate_tier=sm.estimate_tier,
                         operator_selected=operator_selected, budget_k=budget_k)
    _screen(batch, sm, verdict_cache, result)

    # anything discovered but not screened this cycle is pending (future cycles).
    screened_ids = {c.model_id for c in batch}
    result.pending = [c.model_id for c in candidates if c.model_id not in screened_ids
                      and c.model_id not in verdict_cache]

    # 4. GATE → catalog + tier the trusted winners.
    _tier_and_catalog(batch, verdict_cache, sm, result)
    return result


def scheduled_refresh(
    providers: Sequence[ProviderSpec],
    *,
    seams: LifecycleSeams | None = None,
    budget_k: int = DEFAULT_BUDGET_K,
    target_per_tier: int = DEFAULT_TARGET_PER_TIER,
    operator_selected: Iterable[str] = (),
    config_dir: str | Path | None = None,
) -> LifecycleResult:
    """TTL/cron keep-fresh cycle.

    Re-discover → preflight ONLY new/changed models (INCREMENTAL: a cached verdict is
    never re-run) → refresh the catalog → re-tier. Idempotent (a cycle with no new
    models mutates nothing), off the hot path, and stale-but-usable — if discovery or
    screening fails wholesale, the existing catalog/tiers are left intact and
    ``result.stale`` is set."""
    sm = seams or default_seams(config_dir=config_dir)
    result = LifecycleResult()

    try:
        candidates = _discover_candidates(providers, sm, result)
        verdict_cache = dict(sm.load_verdicts())
        tier_need = _tier_need(sm.current_tier_members(), target_per_tier)
        # INCREMENTAL is enforced inside select_batch (cached ids dropped); the
        # bounded prioritized batch is the ONLY thing screened this cycle.
        batch = select_batch(candidates, verdict_cache=verdict_cache, tier_need=tier_need,
                             estimate_tier=sm.estimate_tier,
                             operator_selected=operator_selected, budget_k=budget_k)
        _screen(batch, sm, verdict_cache, result)

        screened_ids = {c.model_id for c in batch}
        result.pending = [c.model_id for c in candidates if c.model_id not in screened_ids
                          and c.model_id not in verdict_cache]

        _tier_and_catalog(batch, verdict_cache, sm, result)
    except Exception as exc:  # noqa: BLE001 — keep last-good roster, never blow up cron
        msg = f"scheduled_refresh cycle failed ({type(exc).__name__}: {exc}) — " \
              "keeping last-good catalog/tiers (stale-but-usable)"
        log.error(msg)
        result.errors.append(msg)
        result.stale = True
    return result


def _screen(
    batch: Sequence[ModelCandidate],
    seams: LifecycleSeams,
    verdict_cache: dict[str, str],
    result: LifecycleResult,
) -> None:
    """Run the EXPENSIVE preflight on each selected model, caching every verdict so a
    future cycle never re-screens it (INCREMENTAL). A screen error detains the model
    (fail-closed) — never a silent pass."""
    changed = False
    for c in batch:
        try:
            verdict = seams.preflight(c.model_id)
        except LifecycleError as exc:
            log.error("preflight error for %r: %s", c.model_id, exc)
            result.errors.append(str(exc))
            verdict = DETAIN
        verdict = verdict if verdict in (TRUST, DETAIN) else DETAIN
        verdict_cache[c.model_id] = verdict
        result.screened.append(c.model_id)
        changed = True
    if changed:
        seams.save_verdicts(verdict_cache)


def main(argv: Sequence[str] | None = None) -> int:
    """Thin CLI shim so the module is runnable/wireable.

    NOTE: the full ``charon setup`` / cron wiring is added by the manager (owns
    ``cli.py``); this ``main`` only exposes the entrypoints for a smoke invocation and
    documents the contract. It intentionally does NOT run a real onboarding (that needs
    a live preflight seam) — it prints the wiring contract instead."""
    import argparse

    parser = argparse.ArgumentParser(prog="charon-lifecycle", description=__doc__)
    parser.add_argument("mode", choices=["bootstrap", "refresh", "contract"],
                        nargs="?", default="contract")
    ns = parser.parse_args(argv)
    print(
        "MODEL-LIFECYCLE orchestrator. Wire a real preflight seam via "
        "default_seams(preflight=subprocess_preflight_seam(<preflight.sh>)) and "
        "call bootstrap(...) / scheduled_refresh(...). Mode requested: " + ns.mode
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
