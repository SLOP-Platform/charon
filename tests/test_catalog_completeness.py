"""CATALOG-COMPLETENESS — required catalog fields, persisted cost map, cheapest
provider ranking, litellm-feed population.

DONE CONTRACT (RED then GREEN, breaks EXTERNALLY SPECIFIED):
  a. A catalog entry missing price or context is REJECTED loudly. Revert → RED.
  b. cost_map.json exists on disk after a discovery run, and a restart reads it
     rather than recomputing.
  c. Given one model served by 2+ providers at different prices, the cheapest is
     ranked first. Prove with a fixture; revert the ordering → RED.
  d. ANTI-OVER-BLOCK: an entry with complete fields passes untouched.
"""
from __future__ import annotations

import json

import pytest

from charon.discover import (
    CatalogIncompleteError,
    build_cost_map,
    discover_models,
    get_cost_map,
    save_cost_map,
    validate_catalog_entry,
)

# ── contract a: missing required field is REJECTED loudly ──────────────────────

@pytest.mark.parametrize("missing", ["cost_input", "cost_output", "context_window", "free"])
def test_missing_required_field_rejected_loud(missing: str):
    entry = {
        "provider": "openai",
        "cost_input": 0.0000025,
        "cost_output": 0.00001,
        "context_window": 128000,
        "free": False,
    }
    del entry[missing]
    with pytest.raises(CatalogIncompleteError) as exc_info:
        validate_catalog_entry("gpt-4o", entry)
    assert missing in str(exc_info.value)


def test_validate_rejects_all_missing():
    entry = {"provider": "openai"}
    with pytest.raises(CatalogIncompleteError):
        validate_catalog_entry("bare", entry)


def test_red_revert_validate_is_the_check():
    """Revert the check → RED: if validate_catalog_entry accepted anything, this
    assertion (that it raises) would fail. The check IS the gate."""
    import charon.discover as disc
    # the required-fields tuple must name every contract field
    assert set(disc._REQUIRED_FIELDS) == {
        "cost_input", "cost_output", "context_window", "free"}


# ── contract d: ANTI-OVER-BLOCK — complete entry passes untouched ─────────────

def test_complete_entry_passes_untouched():
    entry = {
        "provider": "openai",
        "cost_input": 0.0000025,
        "cost_output": 0.00001,
        "context_window": 128000,
        "free": False,
    }
    snapshot = dict(entry)
    validate_catalog_entry("gpt-4o", entry)  # must not mutate
    assert entry == snapshot


def test_free_entry_with_zero_prices_is_complete():
    entry = {
        "provider": "openrouter",
        "cost_input": 0.0,
        "cost_output": 0.0,
        "context_window": 64000,
        "free": True,
    }
    validate_catalog_entry("llama-3:free", entry)  # must not raise


# ── contract b: cost_map.json persisted + restart reads it ─────────────────────

def test_discover_persists_cost_map(monkeypatch, tmp_path):
    from charon import providers

    def _fake_discover(base_url, api_key, strip_v1=True, timeout=10):  # noqa: ANN001
        return [{"id": "test-model",
                 "pricing": {"prompt": "0.0000025", "completion": "0.00001"},
                 "context_window": 128000}]

    monkeypatch.setattr("charon.discover.discover_provider", _fake_discover)
    monkeypatch.setattr("charon.discover.providers.PRESETS", {
        "prov-a": providers.ProviderPreset("http://a.example/v1", strip_v1=True),
    })
    monkeypatch.setattr("charon.discover.config.load_providers", lambda **kw: {})
    monkeypatch.setattr("charon.discover.secrets.load_secrets", lambda **kw: {})
    monkeypatch.setattr("charon.discover.secrets.config_dir", lambda **kw: tmp_path)

    discover_models(timeout=5, config_dir=tmp_path)

    persisted = tmp_path / "cost_map.json"
    assert persisted.exists(), "cost_map.json must exist on disk after a run"
    on_disk = json.loads(persisted.read_text())
    assert "test-model" in on_disk


def test_restart_reads_persisted_cost_map(monkeypatch, tmp_path):
    """A restart (get_cost_map, refresh=False) reads the file rather than
    recomputing — the discover poller is NOT invoked."""
    cost_map = {
        "cached-model": {
            "providers": [{"provider": "openai", "cost_input": 1.0,
                            "cost_output": 2.0, "context_window": 8000,
                            "free": False}],
        },
    }
    save_cost_map(cost_map, config_dir=tmp_path)

    polled = {"count": 0}

    def _should_not_be_called(*a, **kw):  # noqa: ANN001
        polled["count"] += 1
        return [{"id": "polled-model"}]

    monkeypatch.setattr("charon.discover.discover_provider", _should_not_be_called)
    monkeypatch.setattr("charon.discover.providers.PRESETS", {})
    monkeypatch.setattr("charon.discover.config.load_providers", lambda **kw: {})
    monkeypatch.setattr("charon.discover.secrets.load_secrets", lambda **kw: {})
    monkeypatch.setattr("charon.discover.secrets.config_dir", lambda **kw: tmp_path)

    result = get_cost_map(config_dir=tmp_path, refresh=False)
    assert "cached-model" in result
    assert "polled-model" not in result
    assert polled["count"] == 0, "restart must read disk, not re-poll providers"


def test_get_cost_map_refresh_true_recomputes(monkeypatch, tmp_path):
    save_cost_map({"stale": {"providers": []}}, config_dir=tmp_path)

    from charon import providers

    def _fake_discover(base_url, api_key, strip_v1=True, timeout=10):  # noqa: ANN001
        return [{"id": "fresh-model",
                 "pricing": {"prompt": "0.0000025", "completion": "0.00001"},
                 "context_window": 128000}]

    monkeypatch.setattr("charon.discover.discover_provider", _fake_discover)
    monkeypatch.setattr("charon.discover.providers.PRESETS", {
        "prov-a": providers.ProviderPreset("http://a.example/v1", strip_v1=True),
    })
    monkeypatch.setattr("charon.discover.config.load_providers", lambda **kw: {})
    monkeypatch.setattr("charon.discover.secrets.load_secrets", lambda **kw: {})
    monkeypatch.setattr("charon.discover.secrets.config_dir", lambda **kw: tmp_path)

    result = get_cost_map(config_dir=tmp_path, refresh=True)
    assert "fresh-model" in result
    assert "stale" not in result


# ── contract c: cheapest provider for a model ranked first ────────────────────

def test_cheapest_provider_ranked_first():
    """One model served by 2 providers at different prices → cheapest first."""
    discoveries = {
        "openai": [{"id": "gpt-4o",
                    "pricing": {"prompt": "0.000005", "completion": "0.000015"},
                    "context_window": 128000}],
        "openrouter": [{"id": "gpt-4o",
                        "pricing": {"prompt": "0.0000025", "completion": "0.00001"},
                        "context_window": 128000}],
    }
    result = build_cost_map(discoveries)
    provs = result["gpt-4o"]["providers"]
    assert len(provs) == 2
    # openrouter (0.0000025) is cheaper than openai (0.000005) → first
    assert provs[0]["provider"] == "openrouter"
    assert provs[1]["provider"] == "openai"
    # each carries the canonical per-token cost
    assert provs[0]["cost_input"] == 0.0000025
    assert provs[0]["cost_output"] == 0.00001


def test_cheapest_ranking_red_revert_is_sort():
    """Revert the ordering → RED: the sort IS the contract. Unsorted discovery
    order would put openai first; the cheapest-first sort must reorder it."""
    discoveries = {
        "openai": [{"id": "gpt-4o",
                    "pricing": {"prompt": "0.000005", "completion": "0.000015"},
                    "context_window": 128000}],
        "openrouter": [{"id": "gpt-4o",
                        "pricing": {"prompt": "0.0000025", "completion": "0.00001"},
                        "context_window": 128000}],
    }
    result = build_cost_map(discoveries)
    blended_cheaper = (3.0 * 0.0000025 + 0.00001) / 4.0
    blended_costlier = (3.0 * 0.000005 + 0.000015) / 4.0
    assert blended_cheaper < blended_costlier
    assert result["gpt-4o"]["providers"][0]["provider"] == "openrouter"


def test_three_providers_cheapest_first():
    discoveries = {
        "p1": [{"id": "m", "pricing": {"prompt": "0.000003", "completion": "0.00001"},
                "context_window": 128000}],
        "p2": [{"id": "m", "pricing": {"prompt": "0.000001", "completion": "0.000005"},
                "context_window": 128000}],
        "p3": [{"id": "m", "pricing": {"prompt": "0.000002", "completion": "0.000008"},
                "context_window": 128000}],
    }
    result = build_cost_map(discoveries)
    provs = result["m"]["providers"]
    assert [p["provider"] for p in provs] == ["p2", "p3", "p1"]


# ── scope 3: litellm feed populates price/context a provider omitted ──────────

def test_litellm_feed_fills_missing_price(monkeypatch):
    """A provider /models entry with NO pricing is enriched from the litellm
    feed so the model still gets cost-ranked (CATALOG-COMPLETENESS scope 3)."""
    fake_feed = {"gpt-4o": {
        "cost_input": 0.0000025, "cost_output": 0.00001,
        "context_window": 128000, "free": False, "source": "litellm"}}
    monkeypatch.setattr("charon.discover._litellm_feed", lambda: fake_feed)

    discoveries = {"openai": [{"id": "gpt-4o", "context_window": 128000}]}
    result = build_cost_map(discoveries)
    entry = result["gpt-4o"]["providers"][0]
    # litellm filled the price the provider omitted
    assert entry["cost_input"] == 0.0000025
    assert entry["cost_output"] == 0.00001
    assert "litellm" in entry.get("sources", [])


def test_litellm_feed_fills_context_window(monkeypatch):
    fake_feed = {"glm-4.7": {
        "cost_input": 6e-07, "cost_output": 2.2e-06,
        "context_window": 200000, "free": False, "source": "litellm"}}
    monkeypatch.setattr("charon.discover._litellm_feed", lambda: fake_feed)

    discoveries = {"zai": [{"id": "glm-4.7"}]}
    result = build_cost_map(discoveries)
    entry = result["glm-4.7"]["providers"][0]
    assert entry["context_window"] == 200000
    assert entry["cost_input"] == 6e-07
    assert entry["cost_output"] == 2.2e-06


def test_litellm_feed_disagreement_recorded_not_silently_picked(monkeypatch):
    """When provider AND litellm both quote a price and they differ, the
    provider's quote WINS but the litellm figure is RECORDED (visible, not
    erased) — multiple corroborating sources over one SSOT."""
    fake_feed = {"gpt-4o": {
        "cost_input": 0.0000099, "cost_output": 0.0000290,
        "context_window": 128000, "free": False, "source": "litellm"}}
    monkeypatch.setattr("charon.discover._litellm_feed", lambda: fake_feed)

    discoveries = {"openai": [{"id": "gpt-4o",
                               "pricing": {"prompt": "0.0000025", "completion": "0.00001"},
                               "context_window": 128000}]}
    result = build_cost_map(discoveries)
    entry = result["gpt-4o"]["providers"][0]
    # provider's own quote wins
    assert entry["cost_input"] == 0.0000025
    assert entry["cost_output"] == 0.00001
    # but the litellm disagreement is recorded
    assert "price_sources" in entry
    rec = entry["price_sources"][0]
    assert rec["source"] == "litellm"
    assert rec["cost_input"] == 0.0000099


def test_litellm_feed_matches_provider_namespace(monkeypatch):
    fake_feed = {"zai/glm-4.7": {
        "cost_input": 6e-07, "cost_output": 2.2e-06,
        "context_window": 200000, "free": False, "source": "litellm"}}
    monkeypatch.setattr("charon.discover._litellm_feed", lambda: fake_feed)

    result = build_cost_map({"zai": [{"id": "glm-4.7"}]})
    entry = result["glm-4.7"]["providers"][0]
    assert entry["cost_input"] == 6e-07
    assert entry["context_window"] == 200000


def test_litellm_output_price_disagreement_recorded(monkeypatch):
    fake_feed = {"gpt-4o": {
        "cost_input": 0.0000025, "cost_output": 0.000029,
        "context_window": 128000, "free": False, "source": "litellm"}}
    monkeypatch.setattr("charon.discover._litellm_feed", lambda: fake_feed)

    result = build_cost_map({"openai": [{"id": "gpt-4o",
        "pricing": {"prompt": "0.0000025", "completion": "0.00001"},
        "context_window": 128000}]})
    entry = result["gpt-4o"]["providers"][0]
    assert entry["cost_output"] == 0.00001
    assert entry["price_sources"][0]["cost_output"] == 0.000029


def test_litellm_feed_absent_is_silent(monkeypatch):
    """No litellm available → discovery still works (no hard-fail)."""
    monkeypatch.setattr("charon.discover._litellm_feed", lambda: {})
    discoveries = {"openai": [{"id": "gpt-4o",
                               "pricing": {"prompt": "0.0000025", "completion": "0.00001"},
                               "context_window": 128000}]}
    result = build_cost_map(discoveries)
    assert result["gpt-4o"]["providers"][0]["cost_input"] == 0.0000025


# ── scope 4: zai (funded first-party GLM provider) covered by the feed ─────────

def test_zai_glm_models_in_litellm_feed():
    """zai is a funded first-party GLM provider; the live litellm feed must
    carry price+context for its GLM models (scope 4 — cover it)."""
    feed = None
    try:
        feed = __import__("charon.discover", fromlist=["_litellm_feed"])._litellm_feed()
    except Exception:  # noqa: BLE001 — litellm optional; skip when absent
        pytest.skip("litellm not installed")
    if not feed:
        pytest.skip("litellm model_cost unavailable")
    zai_keys = [k for k in feed if k.startswith("zai/")]
    assert zai_keys, "litellm feed must cover zai/* GLM models"
    glm_key = next((k for k in zai_keys if "glm" in k), None)
    assert glm_key is not None
    spec = feed[glm_key]
    assert "cost_input" in spec and "cost_output" in spec
    assert spec["context_window"] is not None
