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


def test_energy_kwh_not_booked_as_usd_without_rate(monkeypatch) -> None:
    """MONEY BUG (METER-KWH-USD-FIX): ``energy_kwh`` is a PHYSICAL energy
    quantity (kilowatt-hours), NOT dollars. With no configured $/kWh price it
    must NOT be booked as USD. The old code put ``energy_kwh`` in the USD field
    list, so 5.0 kWh billed $5.00 (1 kWh == $1). Reverting the fix turns this
    RED: the ledger would show 5.0 instead of 0.0."""
    monkeypatch.delenv("CHARON_ENERGY_USD_PER_KWH", raising=False)
    body = {"model": "neuralwatt/energy-model", "energy_kwh": 5.0}

    # Helper must not turn kWh into dollars 1:1.
    assert _extract_non_token_cost(body) is None
    assert _extract_non_token_cost(body) != 5.0

    # ...and the live production path meters nothing rather than mis-charging.
    p = _NonTokenAwareProxy()
    obs = p.observe(
        "neuralwatt/energy-model", 200, body=body, provider="neuralwatt")
    assert obs.usage is None
    assert p.cumulative_usage().cost_usd == 0.0


def test_energy_kwh_converted_via_configured_rate(monkeypatch) -> None:
    """When a real $/kWh price is configured, kWh is converted to USD — proving
    the field is metered by PRICE, not booked 1:1. 5.0 kWh @ $0.12/kWh = $0.60,
    which is not the raw 5.0 the buggy path produced."""
    monkeypatch.setenv("CHARON_ENERGY_USD_PER_KWH", "0.12")
    body = {"model": "neuralwatt/energy-model", "energy_kwh": 5.0}

    assert _extract_non_token_cost(body) == 0.6

    p = _NonTokenAwareProxy()
    obs = p.observe(
        "neuralwatt/energy-model", 200, body=body, provider="neuralwatt")
    assert obs.usage is not None
    assert obs.usage.cost_usd == 0.6
    assert obs.cost_source == "provider"
    assert p.cumulative_usage().cost_usd == 0.6


def test_usd_field_wins_over_kwh(monkeypatch) -> None:
    """If a provider reports both a genuine USD amount and raw kWh, the USD
    amount is authoritative (kWh is not double-counted)."""
    monkeypatch.setenv("CHARON_ENERGY_USD_PER_KWH", "0.12")
    body = {"model": "m", "energy_cost": 0.037, "energy_kwh": 5.0}
    assert _extract_non_token_cost(body) == 0.037
