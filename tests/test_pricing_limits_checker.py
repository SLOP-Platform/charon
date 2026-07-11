"""Tests for charon.pricing_limits_checker — R17 drift detection.

We seed a mismatch in a temporary canonical file and verify the checker
raises a red finding; reverting the mismatch makes the finding disappear.
"""
from __future__ import annotations

from pathlib import Path

from charon import config
from charon import pricing_limits_checker as plc
from charon.pricing_limits_checker import (
    CheckerConfig,
    ModelPriceSpec,
    NonTokenPricing,
    ProviderCanonical,
    ProviderLimitSpec,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_canonical(cfg: CheckerConfig, tmp_path: Path) -> None:
    plc.save_canonical(cfg, config_dir=tmp_path)


def _seed_models(tmp_path: Path) -> None:
    """Seed a minimal models.json + providers.json in tmp_path."""
    # Patch config_dir temporarily via monkeypatch in test body
    pass


# ---------------------------------------------------------------------------
# Core fail-on-revert tests
# ---------------------------------------------------------------------------


def test_detects_price_drift_and_passes_when_consistent(monkeypatch, tmp_path):
    """FAIL-ON-REVERT: seed a price mismatch → red finding; revert → green."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))

    # 1. Configure a model with cost_input=0.001
    config.add_provider("openrouter", base_url="https://openrouter.ai/api/v1", key_env="OR_KEY")
    config.add_model("gpt-4o", provider="openrouter", cost_input=0.001, cost_output=0.003)

    # 2. Canonical says cost_input should be 0.002 (100 % drift)
    canonical = CheckerConfig(
        providers={
            "openrouter": ProviderCanonical(
                pricing={
                    "gpt-4o": ModelPriceSpec(cost_input=0.002, cost_output=0.003),
                },
            ),
        },
        threshold_pct=5.0,
    )
    _write_canonical(canonical, tmp_path)

    # 3. Checker should flag the drift
    findings = plc.run_check(config_dir=tmp_path, threshold_pct=5.0)
    drift_findings = [f for f in findings if f.category == "price_drift" and f.model == "gpt-4o"]
    assert len(drift_findings) == 1, f"Expected 1 drift finding, got {drift_findings}"
    assert drift_findings[0].severity == "red"
    assert "cost_input drift" in drift_findings[0].message

    # 4. Revert the configured price to match canonical → no drift finding
    config.add_model("gpt-4o", provider="openrouter", cost_input=0.002, cost_output=0.003)
    findings2 = plc.run_check(config_dir=tmp_path, threshold_pct=5.0)
    drift_findings2 = [f for f in findings2 if f.category == "price_drift" and f.model == "gpt-4o"]
    assert len(drift_findings2) == 0, (
        f"Expected 0 drift findings after revert, got {drift_findings2}"
    )


def test_detects_missing_model_and_passes_when_added(monkeypatch, tmp_path):
    """FAIL-ON-REVERT: canonical has a model not in config → red; add it → green."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))

    config.add_provider("deepseek", base_url="https://api.deepseek.com/v1", key_env="DS_KEY")
    config.add_model("deepseek-chat", provider="deepseek", cost_input=0.0001, cost_output=0.0002)

    canonical = CheckerConfig(
        providers={
            "deepseek": ProviderCanonical(
                pricing={
                    "deepseek-chat": ModelPriceSpec(cost_input=0.0001, cost_output=0.0002),
                    "deepseek-coder": ModelPriceSpec(cost_input=0.0001, cost_output=0.0002),
                },
            ),
        },
    )
    _write_canonical(canonical, tmp_path)

    findings = plc.run_check(config_dir=tmp_path)
    missing = [f for f in findings if f.category == "missing" and f.model == "deepseek-coder"]
    assert len(missing) == 1
    assert missing[0].severity == "red"

    # Add missing model
    config.add_model("deepseek-coder", provider="deepseek", cost_input=0.0001, cost_output=0.0002)
    findings2 = plc.run_check(config_dir=tmp_path)
    missing2 = [f for f in findings2 if f.category == "missing" and f.model == "deepseek-coder"]
    assert len(missing2) == 0


def test_detects_stale_model_in_config(monkeypatch, tmp_path):
    """A configured model whose provider is NOT in canonical is flagged stale."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))

    config.add_provider("legacy", base_url="http://old.example/v1", key_env="OLD_KEY")
    config.add_model("old-model", provider="legacy", cost_input=0.001, cost_output=0.002)

    canonical = CheckerConfig(providers={})
    _write_canonical(canonical, tmp_path)

    findings = plc.run_check(config_dir=tmp_path)
    stale = [f for f in findings if f.category == "stale" and f.provider == "legacy"]
    assert len(stale) == 1
    assert stale[0].severity == "yellow"


def test_detects_limit_change(monkeypatch, tmp_path):
    """Canonical defines limits → advisory yellow finding (no runtime limit store yet)."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))

    config.add_provider("groq", base_url="https://api.groq.com/openai/v1", key_env="GROQ_KEY")
    config.add_model("llama3-8b", provider="groq", cost_input=0.0, cost_output=0.0, free=True)

    canonical = CheckerConfig(
        providers={
            "groq": ProviderCanonical(
                limits=ProviderLimitSpec(rpm=500, tpm=100_000),
            ),
        },
    )
    _write_canonical(canonical, tmp_path)

    findings = plc.run_check(config_dir=tmp_path)
    limit_findings = [f for f in findings if f.category == "limit_change" and f.provider == "groq"]
    assert len(limit_findings) == 1
    assert limit_findings[0].severity == "yellow"


def test_detects_non_token_pricing(monkeypatch, tmp_path):
    """NeuralWatt-style non-token pricing is flagged so downstream cost-rank can handle it."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))

    config.add_provider("neuralwatt", base_url="https://api.neuralwatt.com/v1", key_env="NW_KEY")
    config.add_model("nw-moe", provider="neuralwatt", cost_input=0.0, cost_output=0.0)

    canonical = CheckerConfig(
        providers={
            "neuralwatt": ProviderCanonical(
                non_token=NonTokenPricing(
                    type="energy_kwh",
                    rate=10.0,
                    unit="kWh",
                    included_monthly=6.0,
                    subscription_usd=20.0,
                    overflow_rate=10.0,
                ),
            ),
        },
    )
    _write_canonical(canonical, tmp_path)

    findings = plc.run_check(config_dir=tmp_path)
    nt = [f for f in findings if f.category == "non_token" and f.provider == "neuralwatt"]
    assert len(nt) == 1
    assert nt[0].severity == "yellow"
    assert "bills by ENERGY" in nt[0].message


def test_marginal_cost_helper_energy():
    """Non-token energy rate can be approximately converted to a per-token signal."""
    nt = NonTokenPricing(type="energy_kwh", rate=10.0, unit="kWh")
    approx = plc.marginal_cost_per_token(
        nt, avg_tokens_per_request=1_000_000, avg_kwh_per_request=0.019
    )
    assert approx is not None
    # 0.019 kWh * $10/kWh = $0.19 per 1M tokens
    assert abs(approx - 0.19) < 0.01


def test_marginal_cost_helper_request_cap():
    nt = NonTokenPricing(type="request_cap", rate=0.001, unit="request")
    approx = plc.marginal_cost_per_token(nt, avg_tokens_per_request=1000)
    assert approx is not None
    assert abs(approx - 1e-6) < 1e-9


def test_save_and_load_canonical_roundtrip(tmp_path):
    canonical = CheckerConfig(
        providers={
            "p1": ProviderCanonical(
                limits=ProviderLimitSpec(rpm=100),
                pricing={"m1": ModelPriceSpec(cost_input=0.001, cost_output=0.002, free=False)},
                non_token=NonTokenPricing(type="subscription", rate=15.0, unit="mo"),
                plan="pro",
                source_url="https://example.com/pricing",
                last_verified="2026-07-10",
            ),
        },
        threshold_pct=3.0,
        last_updated="2026-07-10",
        sources={"p1": "https://example.com/pricing"},
    )
    p = plc.save_canonical(canonical, config_dir=tmp_path)
    assert p.exists()
    loaded = plc.load_canonical(config_dir=tmp_path)
    assert loaded.threshold_pct == 3.0
    assert "p1" in loaded.providers
    p1 = loaded.providers["p1"]
    assert p1.limits.rpm == 100
    assert p1.pricing["m1"].cost_input == 0.001
    assert p1.non_token is not None
    assert p1.non_token.type == "subscription"
    assert p1.plan == "pro"


def test_findings_to_dicts():
    f = plc.Finding(
        severity="red",
        category="price_drift",
        provider="openrouter",
        model="gpt-4o",
        message="drift",
        canonical_value=0.002,
        configured_value=0.001,
    )
    d = plc.findings_to_dicts([f])[0]
    assert d["severity"] == "red"
    assert d["provider"] == "openrouter"
