"""GATEWAY-NONTOKEN-METERING: non-token (energy-billed) cost extraction.

Drives the real production path — ``_NonTokenAwareProxy.observe`` calls the
overridden ``classify`` then ``record`` — and reads the metered cost back out
of proxy state. No method under test is mocked.
"""

from __future__ import annotations

from charon.gateway import _extract_non_token_cost, _NonTokenAwareProxy


def test_energy_cost_extracted_when_no_usage_dict() -> None:
    """A provider that bills by energy returns a top-level ``energy_cost`` and
    NO OpenAI-style ``usage`` object. ``_gateway_usage`` yields None, so the old
    guard (``obs.usage is not None``) skipped extraction and billed $0. The real
    energy cost must now be recorded."""
    p = _NonTokenAwareProxy()
    body = {"model": "neuralwatt/energy-model", "energy_cost": 0.037}
    obs = p.observe(
        "neuralwatt/energy-model", 200, body=body, provider="neuralwatt")

    # The observation itself carries the real cost, not $0.
    assert obs.usage is not None
    assert obs.usage.cost_usd == 0.037
    assert obs.cost_source == "provider"

    # ...and it is folded into the metered ledger (global + per-provider).
    assert p.cumulative_usage().cost_usd == 0.037
    costs = p.all_model_provider_costs()
    assert costs[("neuralwatt/energy-model", "neuralwatt")] == 0.037


def test_top_level_total_cost_without_usage_dict() -> None:
    """Same shape via the ``total_cost`` field name, still no usage dict."""
    p = _NonTokenAwareProxy()
    body = {"model": "m", "total_cost": 0.5}
    obs = p.observe("m", 200, body=body, provider="prov")
    assert obs.usage is not None and obs.usage.cost_usd == 0.5
    assert p.cumulative_usage().cost_usd == 0.5


def test_no_cost_field_and_no_usage_stays_zero() -> None:
    """No usage dict and no non-token cost field → nothing to meter (no crash,
    no phantom cost)."""
    p = _NonTokenAwareProxy()
    obs = p.observe("m", 200, body={"model": "m"}, provider="prov")
    assert obs.usage is None
    assert p.cumulative_usage().cost_usd == 0.0


def test_token_billed_zero_cost_case_still_computes() -> None:
    """Existing behavior preserved: a usage dict with cost 0 and no non-token
    field is untouched by the non-token path."""
    p = _NonTokenAwareProxy()
    body = {"model": "m", "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
    obs = p.observe("m", 200, body=body, provider="prov")
    assert obs.usage is not None
    assert obs.usage.tokens_in == 10 and obs.usage.tokens_out == 5
    # No pricing / no non-token field → unpriced, cost stays 0 (not invented).
    assert obs.usage.cost_usd == 0.0


def test_extract_helper_reads_top_level_and_usage() -> None:
    assert _extract_non_token_cost({"energy_cost": 0.037}) == 0.037
    assert _extract_non_token_cost({"usage": {"total_cost": 0.9}}) == 0.9
    assert _extract_non_token_cost({"model": "m"}) is None
    assert _extract_non_token_cost(None) is None
