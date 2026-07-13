"""MODEL-LIFECYCLE — mock-only orchestration tests (the FAIL-ON-REVERT gate).

Everything is driven through injected mock seams — no live gateway, provider,
grader, or subprocess. The suite proves the orchestrator's contract:

  * bootstrap over 2 mock providers discovers → preflights → catalogs + tiers
    ONLY the passing (trusted, non-detained) models;
  * the preflight gate is CAUSAL, not a tautology — the same pipeline differing
    only in a model's verdict tiers it or not (revert the ``verdict != TRUST``
    guard in ``lifecycle._tier_and_catalog`` and ``test_gate_is_causal`` /
    ``test_bootstrap_only_passing_tiered`` go RED);
  * scheduled_refresh is INCREMENTAL (a NEW model preflights just itself; an
    already-screened model is never re-run) and BOUNDED (at most ``budget_k``
    per cycle);
  * a failing preflight → the model is NOT tiered;
  * discovery failure degrades stale-but-usable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from charon import lifecycle
from charon.lifecycle import (
    DETAIN,
    TRUST,
    LifecycleSeams,
    ModelCandidate,
    ProviderSpec,
    bootstrap,
    scheduled_refresh,
    select_batch,
)


@dataclass
class MockWorld:
    """In-memory backing store + call recorder for the injected seams."""

    catalog: dict[str, dict] = field(default_factory=dict)
    tiers: dict[str, list[str]] = field(default_factory=lambda: {"low": [], "med": [], "high": []})
    verdicts: dict[str, str] = field(default_factory=dict)
    verdict_map: dict[str, str] = field(default_factory=dict)   # model -> TRUST/DETAIN to serve
    tier_map: dict[str, str] = field(default_factory=dict)      # model -> authoritative tier
    detained: set[str] = field(default_factory=set)
    provider_models: dict[str, list[dict]] = field(default_factory=dict)
    discover_raises: set[str] = field(default_factory=set)
    linked: list[str] = field(default_factory=list)
    preflight_calls: list[str] = field(default_factory=list)
    scorecard_rows: list[tuple[str, str, str]] = field(default_factory=list)

    def seams(self) -> LifecycleSeams:
        return LifecycleSeams(
            link_provider=self._link,
            discover=self._discover,
            preflight=self._preflight,
            assign_tier=lambda c: self.tier_map.get(c.model_id, "med"),
            estimate_tier=lifecycle._heuristic_tier,
            catalog_put=self._catalog_put,
            set_tier_members=self._set_tiers,
            current_tier_members=lambda: {t: list(v) for t, v in self.tiers.items()},
            is_detained=lambda m: m in self.detained,
            feed_scorecard=self.scorecard_rows.extend,
            load_verdicts=lambda: dict(self.verdicts),
            save_verdicts=self._save_verdicts,
        )

    def _link(self, spec: ProviderSpec) -> None:
        self.linked.append(spec.name)

    def _discover(self, spec: ProviderSpec) -> list[dict]:
        if spec.name in self.discover_raises:
            raise RuntimeError(f"boom: {spec.name}")
        return list(self.provider_models.get(spec.name, []))

    def _preflight(self, model_id: str) -> str:
        self.preflight_calls.append(model_id)
        return self.verdict_map.get(model_id, DETAIN)

    def _catalog_put(self, c: ModelCandidate, cost_rank: int, tier: str) -> None:
        self.catalog[c.model_id] = {"provider": c.provider, "price": dict(c.price),
                                    "cost_rank": cost_rank, "tier": tier}

    def _set_tiers(self, members: dict[str, list[str]]) -> None:
        self.tiers = {t: list(v) for t, v in members.items()}

    def _save_verdicts(self, cache: dict[str, str]) -> None:
        self.verdicts = dict(cache)


def _m(mid: str, **kw) -> dict:
    """A mock /models entry."""
    return {"id": mid, **kw}


def _two_provider_world() -> MockWorld:
    """Fresh install: 2 providers, 3 models, one of which fails preflight."""
    w = MockWorld()
    w.provider_models = {
        "alpha": [_m("good-a", cost_input=1.0), _m("bad-a", cost_input=2.0)],
        "beta": [_m("good-b", cost_input=0.5)],
    }
    w.verdict_map = {"good-a": TRUST, "bad-a": DETAIN, "good-b": TRUST}
    w.tier_map = {"good-a": "high", "good-b": "low"}
    return w


def _providers() -> list[ProviderSpec]:
    return [ProviderSpec("alpha", "https://a.example/v1", "ALPHA_KEY"),
            ProviderSpec("beta", "https://b.example/v1", "BETA_KEY")]


# ── bootstrap ─────────────────────────────────────────────────────────────────


def test_bootstrap_links_and_discovers_both_providers() -> None:
    """Fresh install links both providers and discovers all advertised models."""
    w = _two_provider_world()
    res = bootstrap(_providers(), seams=w.seams())
    assert w.linked == ["alpha", "beta"]
    assert set(res.discovered) == {"good-a", "bad-a", "good-b"}


def test_bootstrap_only_passing_tiered() -> None:
    """Catalog + tiers are populated with ONLY the passing models; the failing one
    is screened but NOT tiered/catalogued. (Revert the gate → bad-a tiered → RED.)"""
    w = _two_provider_world()
    res = bootstrap(_providers(), seams=w.seams())
    tiered_ids = {m for ms in res.tiered.values() for m in ms}
    assert tiered_ids == {"good-a", "good-b"}
    assert "bad-a" not in tiered_ids
    assert set(w.catalog) == {"good-a", "good-b"}
    assert "bad-a" in res.detained
    # tiers persisted to the exact authoritative buckets.
    assert w.tiers["high"] == ["good-a"]
    assert w.tiers["low"] == ["good-b"]


def test_bootstrap_populates_provider_and_costrank() -> None:
    """Catalog entries carry model→provider→price and a cost rank (cheapest=1)."""
    w = _two_provider_world()
    bootstrap(_providers(), seams=w.seams())
    assert w.catalog["good-a"]["provider"] == "alpha"
    assert w.catalog["good-b"]["provider"] == "beta"
    # good-b (0.5) is cheaper than good-a (1.0) → rank 1.
    assert w.catalog["good-b"]["cost_rank"] == 1
    assert w.catalog["good-a"]["cost_rank"] == 2


def test_bootstrap_feeds_scorecard_with_trusted_only() -> None:
    """Only trusted winners are fed to the scorecard."""
    w = _two_provider_world()
    bootstrap(_providers(), seams=w.seams())
    fed = {row[0] for row in w.scorecard_rows}
    assert fed == {"good-a", "good-b"}


# ── FAIL-ON-REVERT: the gate is causal, not a tautology ───────────────────────


@pytest.mark.parametrize("verdict,expect_tiered", [(TRUST, True), (DETAIN, False)])
def test_gate_is_causal(verdict: str, expect_tiered: bool) -> None:
    """The SAME pipeline, differing ONLY in the model's preflight verdict, tiers it
    or not — proving the ``verdict != TRUST`` guard is the load-bearing cause.

    With the guard in place: TRUST → tiered, DETAIN → not. Revert the guard in
    ``lifecycle._tier_and_catalog`` and the DETAIN case would ALSO tier → this
    parametrization's second row goes RED. Not a tautology: the trust row proves the
    pipeline DOES tier when the gate passes."""
    w = MockWorld()
    w.provider_models = {"alpha": [_m("subject", cost_input=1.0)]}
    w.verdict_map = {"subject": verdict}
    w.tier_map = {"subject": "med"}
    res = bootstrap([ProviderSpec("alpha", "https://a.example/v1")], seams=w.seams())
    tiered_ids = {m for ms in res.tiered.values() for m in ms}
    assert ("subject" in tiered_ids) is expect_tiered
    assert ("subject" in w.catalog) is expect_tiered


def test_failing_model_never_reaches_catalog() -> None:
    """A model that fails preflight is screened, cached DETAIN, but not catalogued."""
    w = MockWorld()
    w.provider_models = {"alpha": [_m("flaky")]}
    w.verdict_map = {"flaky": DETAIN}
    res = bootstrap([ProviderSpec("alpha", "https://a.example/v1")], seams=w.seams())
    assert "flaky" in res.screened
    assert w.verdicts["flaky"] == DETAIN
    assert "flaky" not in w.catalog
    assert res.trusted == []


def test_detention_redline_excludes_trusted_model() -> None:
    """A TRUST verdict is still excluded from tiering when DETENTION-REDLINE detains it."""
    w = MockWorld()
    w.provider_models = {"alpha": [_m("blocked")]}
    w.verdict_map = {"blocked": TRUST}
    w.detained = {"blocked"}
    res = bootstrap([ProviderSpec("alpha", "https://a.example/v1")], seams=w.seams())
    assert "blocked" in res.detained
    assert "blocked" not in w.catalog


# ── scheduled_refresh: incremental + bounded + idempotent ─────────────────────


def test_scheduled_refresh_screens_only_new_model() -> None:
    """A scheduled run with a NEW model preflights JUST that one (incremental)."""
    w = _two_provider_world()
    bootstrap(_providers(), seams=w.seams())
    w.preflight_calls.clear()
    # a new model appears on beta.
    w.provider_models["beta"].append(_m("good-c", cost_input=0.2))
    w.verdict_map["good-c"] = TRUST
    w.tier_map["good-c"] = "med"
    res = scheduled_refresh(_providers(), seams=w.seams())
    assert w.preflight_calls == ["good-c"]           # ONLY the new model screened
    assert "good-c" in res.trusted
    assert "good-c" in w.catalog


def test_scheduled_refresh_is_idempotent() -> None:
    """A second scheduled run with no new models screens nothing and re-tiers nothing."""
    w = _two_provider_world()
    bootstrap(_providers(), seams=w.seams())
    w.preflight_calls.clear()
    res = scheduled_refresh(_providers(), seams=w.seams())
    assert w.preflight_calls == []
    assert res.trusted == []
    assert res.screened == []


def test_incremental_cache_never_rescreens() -> None:
    """An already-screened model (verdict cached) is never preflighted again."""
    w = MockWorld()
    w.provider_models = {"alpha": [_m("known"), _m("fresh")]}
    w.verdict_map = {"known": TRUST, "fresh": TRUST}
    w.tier_map = {"known": "med", "fresh": "med"}
    w.verdicts = {"known": TRUST}   # pre-seed: 'known' already has a cached verdict
    scheduled_refresh([ProviderSpec("alpha", "https://a.example/v1")], seams=w.seams())
    assert w.preflight_calls == ["fresh"]


def test_bounded_k_caps_screening_per_cycle() -> None:
    """At most ``budget_k`` models are screened per cycle even with many candidates."""
    w = MockWorld()
    models = [_m(f"model-{i}", cost_input=float(i)) for i in range(10)]
    w.provider_models = {"alpha": models}
    for i in range(10):
        w.verdict_map[f"model-{i}"] = TRUST
        w.tier_map[f"model-{i}"] = "med"
    res = bootstrap([ProviderSpec("alpha", "https://a.example/v1")], seams=w.seams(),
                    budget_k=3)
    assert len(w.preflight_calls) == 3
    assert len(res.pending) == 7                     # the rest wait for a later cycle


# ── SCALE prioritization ──────────────────────────────────────────────────────


def test_operator_selected_screened_first() -> None:
    """Operator-selected models jump the queue regardless of value/cost order."""
    w = MockWorld()
    w.provider_models = {"alpha": [_m("cheap-a", cost_input=0.1),
                                   _m("pick-me", cost_input=9.0)]}
    for mid in ("cheap-a", "pick-me"):
        w.verdict_map[mid] = TRUST
        w.tier_map[mid] = "med"
    bootstrap([ProviderSpec("alpha", "https://a.example/v1")], seams=w.seams(),
              budget_k=1, operator_selected=["pick-me"])
    assert w.preflight_calls == ["pick-me"]


def test_understaffed_tier_prioritized() -> None:
    """With staffed 'high'/'low' but empty 'med', a med-looking candidate is screened
    before a high-looking one when the budget is 1 (tier NEED wins)."""
    w = MockWorld()
    w.tiers = {"low": ["x", "y"], "med": [], "high": ["p", "q"]}
    # 'gpt-5-turbo' → heuristic high (staffed); 'workhorse' → heuristic med (understaffed).
    w.provider_models = {"alpha": [_m("gpt-5-turbo", cost_input=0.1),
                                   _m("workhorse", cost_input=5.0)]}
    for mid in ("gpt-5-turbo", "workhorse"):
        w.verdict_map[mid] = TRUST
        w.tier_map[mid] = "med"
    bootstrap([ProviderSpec("alpha", "https://a.example/v1")], seams=w.seams(),
              budget_k=1, target_per_tier=2)
    assert w.preflight_calls == ["workhorse"]


def test_select_batch_incremental_and_bounded_directly() -> None:
    """Unit: select_batch drops cached ids and caps at budget_k."""
    cands = [ModelCandidate(f"m{i}", "alpha") for i in range(5)]
    batch = select_batch(cands, verdict_cache={"m0": TRUST}, tier_need={},
                         estimate_tier=lambda c: "med", budget_k=2)
    ids = [c.model_id for c in batch]
    assert "m0" not in ids           # cached → skipped
    assert len(ids) == 2             # bounded


# ── stale-but-usable ──────────────────────────────────────────────────────────


def test_scheduled_refresh_stale_but_usable_on_total_failure() -> None:
    """If discovery raises for the only provider, the cycle degrades: existing tiers
    are untouched and the failure is recorded (never an empty roster)."""
    w = _two_provider_world()
    bootstrap(_providers(), seams=w.seams())
    before = {t: list(v) for t, v in w.tiers.items()}
    w.discover_raises = {"alpha", "beta"}
    res = scheduled_refresh(_providers(), seams=w.seams())
    assert w.tiers == before          # roster preserved
    assert res.errors                  # a red was logged
    assert res.trusted == []


def test_per_provider_discovery_failure_is_skipped() -> None:
    """One provider's discovery failure doesn't abort the cycle; the other onboards."""
    w = _two_provider_world()
    w.discover_raises = {"alpha"}
    res = bootstrap(_providers(), seams=w.seams())
    assert "good-b" in res.trusted     # beta still onboarded
    assert any("alpha" in e for e in res.errors)
