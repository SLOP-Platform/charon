"""Tests for charon.recommend — tier ranking from live catalogs."""
from __future__ import annotations

from charon.recommend import (
    TierRecommendation,
    _find_trusted_models,
    _heuristic_rank,
    recommend_tiers,
)


def test_heuristic_rank_free_model():
    catalog = [{"id": "free-model", "free": True}]
    recs = _heuristic_rank(catalog)
    tiers = {r.tier: r.model_ids for r in recs}
    assert "free-model" in tiers.get("low", [])


def test_heuristic_rank_small_model():
    catalog = [{"id": "llama-3-8b", "free": False}]
    recs = _heuristic_rank(catalog)
    tiers = {r.tier: r.model_ids for r in recs}
    assert "llama-3-8b" in tiers.get("low", [])


def test_heuristic_rank_haiku():
    catalog = [{"id": "claude-haiku-3.5", "free": False}]
    recs = _heuristic_rank(catalog)
    tiers = {r.tier: r.model_ids for r in recs}
    assert "claude-haiku-3.5" in tiers.get("low", [])


def test_heuristic_rank_frontier():
    catalog = [{"id": "claude-3.5-sonnet", "free": False}]
    recs = _heuristic_rank(catalog)
    tiers = {r.tier: r.model_ids for r in recs}
    assert "claude-3.5-sonnet" in tiers.get("high", [])


def test_heuristic_rank_large_context():
    catalog = [{"id": "some-model", "context_window": 200000, "free": False}]
    recs = _heuristic_rank(catalog)
    tiers = {r.tier: r.model_ids for r in recs}
    assert "some-model" in tiers.get("high", [])


def test_heuristic_rank_default_med():
    catalog = [{"id": "generic-model", "free": False, "context_window": 4096}]
    recs = _heuristic_rank(catalog)
    tiers = {r.tier: r.model_ids for r in recs}
    assert "generic-model" in tiers.get("med", [])


def test_heuristic_rank_returns_three_tiers():
    catalog = [{"id": "m1", "free": False}]
    recs = _heuristic_rank(catalog)
    assert len(recs) == 3
    tier_names = {r.tier for r in recs}
    assert tier_names == {"low", "med", "high"}


def test_heuristic_rank_covers_all_models():
    catalog = [
        {"id": "claude-3.5-sonnet", "free": False},
        {"id": "gpt-4o", "free": False},
        {"id": "llama-3-8b", "free": False},
        {"id": "generic-model", "free": False},
    ]
    recs = _heuristic_rank(catalog)
    all_assigned = set()
    for r in recs:
        all_assigned.update(r.model_ids)
    assert all_assigned == {"claude-3.5-sonnet", "gpt-4o", "llama-3-8b", "generic-model"}


def test_recommend_tiers_falls_back_with_no_trusted_models(tmp_path):
    catalog = [{"id": "claude-3.5-sonnet", "free": False}, {"id": "haiku", "free": False}]
    recs = recommend_tiers("test-provider", catalog, config_dir=str(tmp_path))
    assert len(recs) == 3
    all_ids = set()
    for r in recs:
        all_ids.update(r.model_ids)
    assert all_ids == {"claude-3.5-sonnet", "haiku"}


def test_recommend_tiers_anti_hallucination(tmp_path):
    catalog = [{"id": "real-model", "free": False}]
    recs = recommend_tiers("test-provider", catalog, config_dir=str(tmp_path))
    all_ids = set()
    for r in recs:
        all_ids.update(r.model_ids)
    assert "hallucinated-model" not in all_ids
    assert "real-model" in all_ids


def test_find_trusted_models_resolves_preset_base_url(tmp_path, monkeypatch):
    """FAIL-ON-REVERT: a provider added from a built-in preset persists only its
    key_env (base_url lives in the preset). ``_find_trusted_models`` MUST resolve
    the preset base_url — reading the raw providers.json entry alone drops every
    preset-configured provider and returns no trusted models (the decomposer's
    "no trusted planner configured" failure). Revert the resolve() call → empty."""
    from charon import config

    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    # `charon providers add zai` (preset, no --base-url) → key_env only, NO base_url.
    config.add_provider("zai", base_url=None, key_env="ZAI_API_KEY")
    config.add_model("glm-4.6", provider="zai")
    monkeypatch.setenv("ZAI_API_KEY", "sk-test-key")

    trusted = _find_trusted_models(str(tmp_path))
    assert [(m, b) for m, b, _k in trusted] == [
        ("glm-4.6", "https://api.z.ai/api/paas/v4")
    ]
    assert trusted[0][2] == "sk-test-key"


def test_tier_recommendation_dataclass():
    r = TierRecommendation("high", ["m1", "m2"])
    assert r.tier == "high"
    assert r.model_ids == ["m1", "m2"]


# --------------------------------------------------------- WORKER env / tier override
def test_recommend_tiers_env_pinned_worker_queried_first(
    tmp_path, monkeypatch
) -> None:
    # DECOMPOSE-MODEL-WIRING: CHARON_DECOMPOSE_WORKER_MODEL must reorder the trusted
    # list so the pinned model is queried FIRST, even when it is not the first
    # configured trusted model. FAIL-ON-REVERT: stripping the sort block reverts to
    # first-in-list order and this test goes RED.
    from charon import recommend

    catalog = [{"id": "real-model", "free": False}]
    monkeypatch.setattr(
        recommend,
        "_find_trusted_models",
        lambda cd: [
            ("other-model", "https://api.openai.com/v1", "k1"),
            ("pinned-worker", "https://api.openai.com/v1", "k2"),
        ],
    )
    monkeypatch.setenv("CHARON_DECOMPOSE_WORKER_MODEL", "pinned-worker")

    calls: list[str] = []

    def _fake_ask(model_id, base_url, api_key, _catalog):
        calls.append(model_id)
        return None  # heuristic fallback — we only care about call ORDER

    monkeypatch.setattr(recommend, "_ask_model", _fake_ask)

    recommend_tiers("any-provider", catalog, config_dir=str(tmp_path))
    assert calls, "_ask_model was never called"
    assert calls[0] == "pinned-worker"


def test_recommend_tiers_tier_high_worker_queried_first(
    tmp_path, monkeypatch
) -> None:
    # DECOMPOSE-MODEL-WIRING: with no CHARON_DECOMPOSE_WORKER_MODEL set, a trusted
    # model whose id is in tiers.tier_members("high") must be queried FIRST even when
    # not the first configured trusted model. FAIL-ON-REVERT: removing the tier-'high'
    # sort reverts to first-in-list order and this test goes RED.
    from charon import recommend
    from charon.config import tiers as tiers_cfg

    catalog = [{"id": "real-model", "free": False}]
    monkeypatch.setattr(
        recommend,
        "_find_trusted_models",
        lambda cd: [
            ("other-model", "https://api.openai.com/v1", "k1"),
            ("tier-high-model", "https://api.openai.com/v1", "k2"),
        ],
    )
    monkeypatch.delenv("CHARON_DECOMPOSE_WORKER_MODEL", raising=False)
    monkeypatch.setattr(
        tiers_cfg, "tier_members", lambda tier, tiers=None: ["tier-high-model"]
    )

    calls: list[str] = []

    def _fake_ask(model_id, base_url, api_key, _catalog):
        calls.append(model_id)
        return None

    monkeypatch.setattr(recommend, "_ask_model", _fake_ask)

    recommend_tiers("any-provider", catalog, config_dir=str(tmp_path))
    assert calls, "_ask_model was never called"
    assert calls[0] == "tier-high-model"
