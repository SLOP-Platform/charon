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

    def _fake_post(model_id, base_url, api_key, _prompt, timeout=30.0):
        calls.append(model_id)
        return None  # heuristic fallback — we only care about call ORDER

    monkeypatch.setattr(recommend, "_post_tier_ranking", _fake_post)

    recommend_tiers("any-provider", catalog, config_dir=str(tmp_path))
    assert calls, "_post_tier_ranking was never called"
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

    def _fake_post(model_id, base_url, api_key, _prompt, timeout=30.0):
        calls.append(model_id)
        return None

    monkeypatch.setattr(recommend, "_post_tier_ranking", _fake_post)

    recommend_tiers("any-provider", catalog, config_dir=str(tmp_path))
    assert calls, "_post_tier_ranking was never called"
    assert calls[0] == "tier-high-model"


# --------------------------------------------------------- DESTIFF-RECOMMEND failover
def test_recommend_tiers_fails_over_when_first_candidate_401s(
    tmp_path, monkeypatch
) -> None:
    # DESTIFF-RECOMMEND (accept): a transport/auth fault on the first candidate must
    # FAIL OVER to the next, not zero out the recommendation. The first candidate's
    # key 401s (provider-level auth fault → _TierTransportError), the second serves
    # a valid catalog ranking. The returned tiers MUST come from the SECOND model
    # (proves the loop advanced past the dead provider). FAIL-ON-REVERT: collapsing
    # ``_post_tier_ranking`` back to a blanket ``None`` (so 401 looks like an
    # unparseable reply) makes the loop treat it as quality → re-prompt the same
    # dead model → heuristic fallback. The 'real-model' in 'high' from the SECOND
    # provider then never appears.
    from charon import recommend

    catalog = [{"id": "real-model", "free": False}]
    monkeypatch.setattr(
        recommend,
        "_find_trusted_models",
        lambda cd: [
            ("dead-key-model", "https://api.openai.com/v1", "bad"),
            ("live-model", "https://api.openai.com/v1", "good"),
        ],
    )
    monkeypatch.delenv("CHARON_DECOMPOSE_WORKER_MODEL", raising=False)

    def _fake_post(model_id, base_url, api_key, _prompt, timeout=30.0):
        if model_id == "dead-key-model":
            raise recommend._TierTransportError(
                "auth", 401, "HTTP 401 from dead-key-model"
            )
        # Second candidate: valid catalog ranking.
        return {"high": ["real-model"], "med": [], "low": []}

    monkeypatch.setattr(recommend, "_post_tier_ranking", _fake_post)

    recs = recommend_tiers("any-provider", catalog, config_dir=str(tmp_path))
    tiers = {r.tier: r.model_ids for r in recs}
    assert "real-model" in tiers.get("high", []), (
        f"expected live-model's high ranking to win after failover; got {tiers}"
    )


def test_recommend_tiers_all_candidates_fail_returns_heuristic(
    tmp_path, monkeypatch
) -> None:
    # DESTIFF-RECOMMEND (accept): when EVERY candidate fails the loop must return a
    # clear, non-hanging result (the heuristic fallback — no live ranking, but every
    # catalog id still gets a tier assignment). A dead provider pool no longer
    # zeros out the recommendation or leaves the call hanging on a single
    # provider. FAIL-ON-REVERT: removing the failover wrapper or catching the
    # _RecommendError around it lets the exhaustion raise out of the public API,
    # which the CLI cannot handle cleanly.
    from charon import recommend

    catalog = [
        {"id": "claude-3.5-sonnet", "free": False},
        {"id": "haiku", "free": False},
    ]
    monkeypatch.setattr(
        recommend,
        "_find_trusted_models",
        lambda cd: [
            ("model-a", "https://api.openai.com/v1", "k1"),
            ("model-b", "https://api.openai.com/v1", "k2"),
        ],
    )
    monkeypatch.delenv("CHARON_DECOMPOSE_WORKER_MODEL", raising=False)

    def _fake_post(model_id, base_url, api_key, _prompt, timeout=30.0):
        raise recommend._TierTransportError("auth", 401, f"HTTP 401 from {model_id}")

    monkeypatch.setattr(recommend, "_post_tier_ranking", _fake_post)

    recs = recommend_tiers("any-provider", catalog, config_dir=str(tmp_path))
    # Heuristic path: both models still classified into a tier, none lost.
    assert len(recs) == 3
    all_ids: set[str] = set()
    for r in recs:
        all_ids.update(r.model_ids)
    assert all_ids == {"claude-3.5-sonnet", "haiku"}


def test_recommend_tiers_quality_fault_reprompts_same_model(
    tmp_path, monkeypatch
) -> None:
    # DESTIFF-RECOMMEND (fix A): a 200-but-unparseable reply is a QUALITY fault of
    # THIS model, not a provider fault — the loop must re-prompt the SAME model
    # (one extra attempt) before advancing. With one dead-parse candidate and one
    # live candidate, the live candidate's answer must still win (the dead-parse
    # was retried, then advanced). FAIL-ON-REVERT: classifying unparseable-200 as
    # a transport error advances the loop too early, OR as a blanket-OK lets a
    # bad parse through. The retry-then-failover behavior is the contract.
    from charon import recommend

    catalog = [{"id": "real-model", "free": False}]
    monkeypatch.setattr(
        recommend,
        "_find_trusted_models",
        lambda cd: [
            ("garbage-model", "https://api.openai.com/v1", "k1"),
            ("live-model", "https://api.openai.com/v1", "k2"),
        ],
    )
    monkeypatch.delenv("CHARON_DECOMPOSE_WORKER_MODEL", raising=False)

    calls: list[str] = []

    def _fake_post(model_id, base_url, api_key, _prompt, timeout=30.0):
        calls.append(model_id)
        if model_id == "garbage-model":
            return None  # 200-but-unparseable → RETRY the same model
        return {"high": ["real-model"], "med": [], "low": []}

    monkeypatch.setattr(recommend, "_post_tier_ranking", _fake_post)

    recs = recommend_tiers("any-provider", catalog, config_dir=str(tmp_path))
    tiers = {r.tier: r.model_ids for r in recs}
    assert "real-model" in tiers.get("high", [])
    # garbage-model is retried (max_retries=1 → 2 attempts), then advanced.
    assert calls.count("garbage-model") == 2
    assert calls[-1] == "live-model"


# ─────────────────── SG-never-Anthropic HARD RULE (GATEWAY-WIDE) ────────────────
def test_find_trusted_models_never_returns_anthropic(tmp_path, monkeypatch):
    """SG-never-Anthropic HARD RULE (GATEWAY-WIDE), COVERED AT THE PRODUCTION FILTER.

    Drives the REAL ``_find_trusted_models`` against a config dir where the operator
    has deliberately configured the built-in ``anthropic`` preset WITH a live key —
    the exact condition under which the tier-voter used to happily invoke Claude
    (the voter shipped with NO never-Anthropic guard while the planner had one).
    Only the non-Anthropic model may be trusted.

    FAIL-ON-REVERT: delete the ``is_anthropic_route`` guard in ``_find_trusted_models``
    and 'claude-opus-4' reappears in the trusted list → RED. (Verified by removing the
    guard locally: trusted became ['claude-opus-4', 'glm-4.6'].)
    """
    from charon import config

    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    # `charon providers add anthropic` — preset carries base_url + ANTHROPIC_API_KEY.
    config.add_provider("anthropic", base_url=None, key_env="ANTHROPIC_API_KEY")
    config.add_model("claude-opus-4", provider="anthropic")
    config.add_provider("zai", base_url=None, key_env="ZAI_API_KEY")
    config.add_model("glm-4.6", provider="zai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-live-key")
    monkeypatch.setenv("ZAI_API_KEY", "sk-zai-key")

    trusted = _find_trusted_models(str(tmp_path))

    assert [m for m, _b, _k in trusted] == ["glm-4.6"]
    assert not any("anthropic" in b.lower() for _m, b, _k in trusted)


def test_recommend_tiers_never_invokes_anthropic(tmp_path, monkeypatch):
    """End-to-end companion: even with an Anthropic model configured AND sorted to the
    front of the pool (tiers.json's absent-file default seeds Anthropic names into the
    'high' tier, which ``recommend_tiers`` queries FIRST), no Anthropic route may ever
    reach ``_post_tier_ranking``. Guards the INVOCATION, not just the candidate list."""
    from charon import config, recommend

    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.add_provider("anthropic", base_url=None, key_env="ANTHROPIC_API_KEY")
    config.add_model("claude-opus-4", provider="anthropic")
    config.add_provider("zai", base_url=None, key_env="ZAI_API_KEY")
    config.add_model("glm-4.6", provider="zai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-live-key")
    monkeypatch.setenv("ZAI_API_KEY", "sk-zai-key")

    posted: list[tuple[str, str]] = []

    def _fake_post(model_id, base_url, api_key, _prompt, timeout=30.0):
        posted.append((model_id, base_url))
        return {"low": [], "med": ["real-model"], "high": []}

    monkeypatch.setattr(recommend, "_post_tier_ranking", _fake_post)

    recommend_tiers("some-provider", [{"id": "real-model"}], config_dir=str(tmp_path))

    assert posted, "_post_tier_ranking was never called — test would vacuously pass"
    for model_id, base_url in posted:
        assert "claude" not in model_id.lower()
        assert "anthropic" not in model_id.lower()
        assert "anthropic" not in base_url.lower()
