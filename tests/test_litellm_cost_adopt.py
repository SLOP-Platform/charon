"""LITELLM-COST-ADOPT — wire litellm.model_cost as the pricing source so
derived_cost_rank has real per-token magnitudes instead of the neutral 1000
fallback. RED-PROOF + E2E per the ticket's accept block.

RED-PROOF contract (the two assertions the brief pins):
  1. a model with a KNOWN litellm price MUST get that price (exact per-token USD,
     never adjusted/blended at the source).
  2. an UNMAPPABLE model MUST stay unpriced (price_for returns None) and appear
     by NAME in coverage_report's unmapped list — NEVER defaulted to the neutral
     1000 silently. A wrong mapping silently misprices the money path, which is
     worse than no price.

E2E: cost ordering actually changes for a real pool — before, every unpriced leg
collapsed to cost_rank 1000 (stable sort preserved hand order, cost-first
inoperative); after, litellm-priced legs sort by real per-token cost, with the
unmappable leg left at the neutral fallback and named in the coverage report.

These tests are FAIL-ON-REVERT: reverting the litellm_pricing wiring (or
replacing price_for with a guessed/defaulted value) turns them RED.
"""
from __future__ import annotations

import json

import pytest

pytest.importorskip("litellm")  # [router] extra — skipped (not failed) when absent

from litellm import model_cost  # noqa: E402

from charon.routing_policy import build_routes_and_pools  # noqa: E402
from charon.routing_policy.cost_rank import derived_cost_rank  # noqa: E402
from charon.routing_policy.litellm_pricing import (  # noqa: E402
    coverage_report,
    enrich_registry,
    price_for,
)

# ---------------------------------------------------------------------------
# RED-PROOF (1): a known litellm price is returned EXACTLY — never adjusted.
# ---------------------------------------------------------------------------

def test_known_litellm_price_returned_exactly() -> None:
    """RED-PROOF: openrouter/openai/gpt-5.2 has a litellm price; price_for MUST
    return the exact (input_cost_per_token, output_cost_per_token) per-token USD,
    not a blend, not a round, not a default. Reverting to a guessed/defaulted
    value (e.g. a fixed $0.001) makes this assertion RED."""
    spec = {"provider": "openrouter", "upstream_model": "openai/gpt-5.2"}
    price = price_for("gpt-5.2-or", spec)
    assert price is not None, "gpt-5.2-or is a known litellm key — must be priced"
    expected_ci = model_cost["openrouter/openai/gpt-5.2"]["input_cost_per_token"]
    expected_co = model_cost["openrouter/openai/gpt-5.2"]["output_cost_per_token"]
    assert price == (expected_ci, expected_co), (
        f"price_for returned {price}, expected exact litellm magnitudes "
        f"{(expected_ci, expected_co)} — the pricing source MUST NOT adjust/blend"
    )


def test_deepseek_direct_provider_priced() -> None:
    """RED-PROOF: a deepseek-direct leg (provider=deepseek, no upstream_model)
    maps to litellm's bare/deepseek-prefixed key and returns its real price."""
    spec = {"provider": "deepseek"}
    price = price_for("deepseek-v4-pro-ds", spec)
    assert price is not None
    expected = model_cost["deepseek-v4-pro"]["input_cost_per_token"]
    assert price[0] == expected


# ---------------------------------------------------------------------------
# RED-PROOF (2): an unmappable model stays UNPRICED and is NAMED — never defaulted.
# ---------------------------------------------------------------------------

def test_proprietary_aggregator_never_guessed() -> None:
    """RED-PROOF: nanogpt is a proprietary aggregator litellm does not model.
    Its legs MUST stay unpriced (None) — stamping the underlying provider's
    price would be a GUESS that misprices the money path (worse than no price).
    Reverting price_for to fall back to a bare-key cross-provider lookup makes
    this RED — that is exactly the silent misprice the brief forbids."""
    spec = {"provider": "nanogpt", "upstream_model": "openai/gpt-5.2"}
    assert price_for("gpt-5.2-ng", spec) is None, (
        "nanogpt leg was priced from a different provider's litellm key — "
        "cross-provider guess; the money path is mispriced"
    )


def test_openrouter_model_not_in_litellm_stays_unpriced() -> None:
    """RED-PROOF: glm-5.2-or routes via openrouter but litellm has no
    openrouter/z-ai/glm-5.2 key. It MUST stay unpriced (None) and be REPORTED —
    not defaulted to a guessed price. This is the exact live case the brief cites
    (a glm-5.2 request served via openrouter while cheaper legs were never tried)."""
    spec = {"provider": "openrouter", "upstream_model": "z-ai/glm-5.2"}
    assert price_for("glm-5.2-or", spec) is None, (
        "glm-5.2-or was priced despite no litellm key — a guessed/defaulted price "
        "on the money path is worse than no price"
    )


def test_coverage_report_names_unmapped_models() -> None:
    """RED-PROOF: every unmappable model appears by id in coverage_report's
    unmapped list (with provider + upstream_model + tried candidates) — never a
    silent default. Reverting the report to a bare count hides unmapped models;
    the brief requires they be NAMED."""
    registry = {
        "gpt-5.2-or": {"provider": "openrouter", "upstream_model": "openai/gpt-5.2"},
        "glm-5.2-or": {"provider": "openrouter", "upstream_model": "z-ai/glm-5.2"},
        "gpt-5.2-ng": {"provider": "nanogpt", "upstream_model": "openai/gpt-5.2"},
        "deepseek-v4-pro-ds": {"provider": "deepseek"},
    }
    report = coverage_report(registry)
    unmapped_ids = {e["id"] for e in report["unmapped"]}
    assert "glm-5.2-or" in unmapped_ids, "unmappable glm-5.2-or must be NAMED, not defaulted"
    assert "gpt-5.2-ng" in unmapped_ids, "unmappable gpt-5.2-ng must be NAMED, not defaulted"
    assert "gpt-5.2-or" not in unmapped_ids, "priced model must not appear in unmapped"
    assert "deepseek-v4-pro-ds" not in unmapped_ids
    # per-provider coverage is priced/total per the brief
    pp = report["per_provider"]
    assert pp["openrouter"] == [1, 2], f"openrouter coverage {pp['openrouter']}"
    assert pp["nanogpt"] == [0, 1]
    assert pp["deepseek"] == [1, 1]
    # each unmapped entry carries the candidates tried (evidence, not a bare name)
    glm_entry = next(e for e in report["unmapped"] if e["id"] == "glm-5.2-or")
    assert glm_entry["tried"] == ["openrouter/z-ai/glm-5.2"]


# ---------------------------------------------------------------------------
# enrich_registry: clobber-safe + never guesses
# ---------------------------------------------------------------------------

def test_enrich_registry_clobber_safe_operator_price_wins() -> None:
    """RED-PROOF: an operator-set cost_input/cost_output is NEVER overwritten by
    litellm — even when litellm has a different price. The operator's hand-set
    price is the source of record; litellm only fills the gap (both fields absent)."""
    registry = {
        "gpt-5.2-or": {
            "provider": "openrouter", "upstream_model": "openai/gpt-5.2",
            "cost_input": 9.99e-6, "cost_output": 9.99e-5,  # operator-set, deliberately wrong
        },
    }
    enriched = enrich_registry(registry)
    assert enriched["gpt-5.2-or"]["cost_input"] == 9.99e-6
    assert enriched["gpt-5.2-or"]["cost_output"] == 9.99e-5
    assert enriched["gpt-5.2-or"].get("priced_by") != "litellm", (
        "litellm overwrote an operator price — clobber-safety broken"
    )


def test_enrich_registry_fills_gap_and_stamps_source() -> None:
    """RED-PROOF: an entry with neither cost_input nor cost_output gets the
    litellm price and a priced_by marker; an unmappable entry is left untouched
    (no priced_by, no cost fields — the neutral fallback stands, and it is named
    in the coverage report rather than silently defaulted)."""
    registry = {
        "gpt-5.2-or": {"provider": "openrouter", "upstream_model": "openai/gpt-5.2"},
        "glm-5.2-or": {"provider": "openrouter", "upstream_model": "z-ai/glm-5.2"},
    }
    enriched = enrich_registry(registry)
    assert enriched["gpt-5.2-or"]["priced_by"] == "litellm"
    assert "cost_input" in enriched["gpt-5.2-or"]
    assert "cost_output" in enriched["gpt-5.2-or"]
    # unmappable stays unpriced — NOT defaulted
    assert "cost_input" not in enriched["glm-5.2-or"]
    assert "cost_output" not in enriched["glm-5.2-or"]
    assert "priced_by" not in enriched["glm-5.2-or"]


def test_enrich_registry_does_not_mutate_input() -> None:
    """RED-PROOF: enrich_registry returns a NEW dict; the input registry is not
    mutated, so a caller that re-uses the registry (e.g. a hot-reload) is not
    surprised by in-place stamps."""
    registry = {"gpt-5.2-or": {"provider": "openrouter", "upstream_model": "openai/gpt-5.2"}}
    original = json.dumps(registry, sort_keys=True)
    enrich_registry(registry)
    assert json.dumps(registry, sort_keys=True) == original, "input registry was mutated"


# ---------------------------------------------------------------------------
# E2E: cost ordering actually changes for a real pool (before/after leg order)
# ---------------------------------------------------------------------------

def test_e2e_cost_ordering_changes_with_litellm_pricing() -> None:
    """E2E: a pool of three legs that previously ALL collapsed to cost_rank 1000
    (no configured pricing) now sorts cheapest-first by litellm-sourced price.

    BEFORE (no litellm source): all three legs -> derived_cost_rank 1000 ->
    stable sort preserves the listed hand order:
        [glm-5.2-or, gpt-5.2-or, deepseek-v4-pro-ds]

    AFTER (litellm wired in):
        deepseek-v4-pro-ds ($0.435/$0.87 per 1M)   -> real, cheapest
        gpt-5.2-or        ($1.75/$14 per 1M)        -> real, dearer
        glm-5.2-or        (no litellm key)          -> neutral 1000 (unpriced, named)

    So the chain reorders to [deepseek, gpt-5.2, glm-5.2] — cost-first ordering
    is now OPERATIVE for the two priced legs, and the unmappable leg is honestly
    last with its neutral fallback rather than silently floated by a guess."""
    registry = {
        "glm-5.2-or": {"provider": "openrouter", "upstream_model": "z-ai/glm-5.2"},
        "gpt-5.2-or": {"provider": "openrouter", "upstream_model": "openai/gpt-5.2"},
        "deepseek-v4-pro-ds": {"provider": "deepseek"},
    }
    pool_map = {"coder": ["glm-5.2-or", "gpt-5.2-or", "deepseek-v4-pro-ds"]}
    providers_cfg = {
        "openrouter": {"base_url": "https://openrouter.ai/api/v1"},
        "deepseek": {"base_url": "https://api.deepseek.com/v1"},
    }

    # BEFORE: confirm the gap — with no litellm source (simulated by a registry
    # that has no cost fields AND no enrichment), all three collapse to 1000.
    # (build_routes_and_pools enriches, so we assert the pre-enrichment state
    # directly via derived_cost_rank on the raw specs.)
    for spec in registry.values():
        assert derived_cost_rank(spec) == 1000, (
            "pre-enrichment leg did not collapse to the neutral 1000 — the "
            "before-state assumption is wrong; the E2E before/after is invalid"
        )

    # AFTER: build_routes_and_pools enriches the registry with litellm prices,
    # so derived_cost_rank reads real magnitudes and the chain reorders.
    _, pools, _ = build_routes_and_pools(registry, pool_map, providers_cfg)
    order = [r.model_id for r in pools["coder"]]
    assert order == ["deepseek-v4-pro-ds", "gpt-5.2-or", "glm-5.2-or"], (
        f"cost ordering did not change to cheapest-first: got {order}; the "
        f"litellm pricing source is not wired into the pool compiler"
    )


def test_e2e_unmappable_leg_named_in_coverage_not_defaulted() -> None:
    """E2E companion: the glm-5.2-or leg that sorts last (neutral 1000) is NAMED
    in the coverage report as unmappable — proving it was not silently defaulted
    to a guessed price that could have floated it above the priced legs."""
    registry = {
        "glm-5.2-or": {"provider": "openrouter", "upstream_model": "z-ai/glm-5.2"},
        "gpt-5.2-or": {"provider": "openrouter", "upstream_model": "openai/gpt-5.2"},
        "deepseek-v4-pro-ds": {"provider": "deepseek"},
    }
    report = coverage_report(registry)
    unmapped_ids = {e["id"] for e in report["unmapped"]}
    assert unmapped_ids == {"glm-5.2-or"}, (
        f"expected only glm-5.2-or unmapped, got {unmapped_ids}"
    )
    assert report["priced"] == 2
    assert report["unmapped_count"] == 1


# ---------------------------------------------------------------------------
# :free suffix + non-token entries: edge cases the money path must survive
# ---------------------------------------------------------------------------

def test_free_suffix_stripped_before_lookup() -> None:
    """A ``:free`` upstream id (OpenRouter free-tier) is stripped before the
    litellm lookup so the candidate key matches the priced entry, not a
    nonexistent ``*:free`` key."""
    spec = {"provider": "openrouter", "upstream_model": "openai/gpt-5.2:free"}
    # openrouter/openai/gpt-5.2 exists in litellm; the :free suffix must not break it
    assert price_for("gpt-5.2-free-or", spec) is not None


def test_image_only_entry_not_priced_as_token() -> None:
    """RED-PROOF: a litellm entry that exists but has NO input/output_cost_per_token
    (image/audio-only) is NOT priced as a token model — price_for returns None so
    the neutral fallback stands rather than stamping $0 (which would float it
    first in a free-first sort and corrupt routing)."""
    # Fabricate a registry whose candidate hits an image-only litellm entry by
    # pointing at a known image model's key shape. We cannot rely on a specific
    # image model existing across litellm versions, so instead exercise the
    # guard directly: an entry with neither token cost yields None.
    import charon.routing_policy.litellm_pricing as lp
    orig = lp._get_model_cost
    lp._get_model_cost = lambda: {"openrouter/fake/img": {"output_cost_per_image": 0.04}}  # type: ignore[assignment]
    try:
        result = lp.price_for(
            "img-or", {"provider": "openrouter", "upstream_model": "fake/img"})
        assert result is None
    finally:
        lp._get_model_cost = orig  # type: ignore[assignment]
