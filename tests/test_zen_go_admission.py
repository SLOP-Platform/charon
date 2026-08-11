"""S26 ZEN/GO admission control — FAIL-ON-REVERT tests.

ZEN: free-only, discovery-driven (rotating list).
GO:  fixed two-model allowlist (deepseek-v4-flash, mimo-v2.5).

Both enforced at pool-build time via build_routes_and_pools.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from charon.routing_policy import (
    AdmissionViolation,
    build_routes_and_pools,
)
from charon.routing_policy.admission import (
    check_go_admission,
    check_zen_admission,
    load_zen_free_models,
    save_zen_free_models,
)


def _make_zen_free_json(tmpdir: Path, models: list[str] | set[str]) -> Path:
    p = tmpdir / "zen_free_models.json"
    p.write_text(json.dumps({"free_models": sorted(models)}))
    return tmpdir


class TestZenAdmission:
    """ZEN is free-only — models IN the free set pass, everything else is blocked."""

    def test_free_model_accepted(self):
        free_models = frozenset({"big-pickle", "deepseek-v4-flash-free"})
        check_zen_admission("big-pickle",
                            {"upstream_model": "big-pickle"},
                            free_models=free_models)

    def test_paid_model_blocked(self):
        free_models = frozenset({"big-pickle"})
        try:
            check_zen_admission("claude-opus-4-5",
                                {"upstream_model": "claude-opus-4-5"},
                                free_models=free_models)
        except AdmissionViolation as exc:
            assert "claude-opus-4-5" in str(exc)
            return
        raise AssertionError("expected AdmissionViolation was not raised")

    def test_empty_free_set_blocks_everything(self):
        try:
            check_zen_admission("anything", {},
                                free_models=frozenset())
        except AdmissionViolation as exc:
            assert "EMPTY" in str(exc)
            return
        raise AssertionError("expected AdmissionViolation was not raised")

    def test_model_with_free_in_name_but_not_in_set_is_blocked(self):
        free_models = frozenset({"big-pickle"})
        try:
            check_zen_admission("mimo-v2.5-free",
                                {"upstream_model": "mimo-v2.5-free"},
                                free_models=free_models)
        except AdmissionViolation:
            return
        raise AssertionError("expected AdmissionViolation was not raised")

    def test_discovered_free_model_persists_and_reloads(self, tmp_path):
        models = {"big-pickle", "deepseek-v4-flash-free", "mimo-v2.5-free"}
        assert save_zen_free_models(models, state_dir=str(tmp_path))
        loaded = load_zen_free_models(state_dir=str(tmp_path))
        assert loaded == models

    def test_missing_file_returns_empty(self, tmp_path):
        loaded = load_zen_free_models(state_dir=str(tmp_path))
        assert loaded == frozenset()


class TestGoAdmission:
    """GO is a fixed two-model allowlist with concrete catalog leg ids."""

    def test_allowlisted_model_accepted(self):
        check_go_admission("deepseek-v4-flash-go",
                           {"upstream_model": "deepseek-v4-flash"})

    def test_allowlisted_model_mimo_accepted(self):
        check_go_admission("mimo-v2.5-go",
                           {"upstream_model": "mimo-v2.5"})

    def test_non_allowlisted_model_blocked(self):
        try:
            check_go_admission("deepseek-v4-pro-go",
                               {"upstream_model": "deepseek-v4-pro"})
        except AdmissionViolation as exc:
            assert "deepseek-v4-pro" in str(exc)
            assert "mimo-v2.5" in str(exc)
            return
        raise AssertionError("expected AdmissionViolation was not raised")

    def test_free_skus_not_admitted_on_go(self):
        try:
            check_go_admission("deepseek-v4-flash-free-go",
                               {"upstream_model": "deepseek-v4-flash-free"})
        except AdmissionViolation:
            return
        raise AssertionError(
            "deepseek-v4-flash-free must NOT be admitted on GO — "
            "that is a ZEN free SKU, not a GO paid SKU"
        )

    def test_free_skus_not_admitted_mimo(self):
        try:
            check_go_admission("mimo-v2.5-free-go",
                               {"upstream_model": "mimo-v2.5-free"})
        except AdmissionViolation:
            return
        raise AssertionError(
            "mimo-v2.5-free must NOT be admitted on GO"
        )

    def test_claude_blocked_on_go(self):
        try:
            check_go_admission("claude-haiku-4-5-go",
                               {"upstream_model": "claude-haiku-4-5"})
        except AdmissionViolation:
            return
        raise AssertionError("expected AdmissionViolation was not raised")


class TestBuildRoutesAndPoolsWithAdmission:
    """Admission fires inside build_routes_and_pools — a rejected model
    is dropped from routes with a log, not raised."""

    def test_zen_paid_model_dropped_from_routes(self, tmp_path):
        _make_zen_free_json(tmp_path, ["big-pickle"])
        registry = {
            "big-pickle": {
                "provider": "opencode-zen",
                "free": True,
            },
            "claude-opus-4-5": {
                "provider": "opencode-zen",
                "free": False,
            },
        }
        pool_map = {"test": ["big-pickle", "claude-opus-4-5"]}
        routes, pools, _ = build_routes_and_pools(
            registry, pool_map, {}, state_dir=str(tmp_path))
        assert "big-pickle" in routes
        assert "claude-opus-4-5" not in routes
        assert len(pools["test"]) == 1

    def test_go_non_allowlisted_dropped_from_routes(self):
        registry = {
            "deepseek-v4-flash-go": {
                "provider": "opencode-go",
                "upstream_model": "deepseek-v4-flash",
                "free": False,
            },
            "deepseek-v4-pro-go": {
                "provider": "opencode-go",
                "upstream_model": "deepseek-v4-pro",
                "free": False,
            },
        }
        pool_map = {"test": ["deepseek-v4-flash-go",
                             "deepseek-v4-pro-go"]}
        routes, pools, _ = build_routes_and_pools(
            registry, pool_map, {})
        assert "deepseek-v4-flash-go" in routes
        assert "deepseek-v4-pro-go" not in routes

    def test_other_provider_paid_model_not_checked(self):
        registry = {
            "openrouter/claude-opus-4": {
                "provider": "openrouter",
                "upstream_model": "anthropic/claude-opus-4",
                "free": False,
            },
        }
        pool_map = {"claude-opus-4": ["openrouter/claude-opus-4"]}
        routes, pools, _ = build_routes_and_pools(
            registry, pool_map, {})
        assert "openrouter/claude-opus-4" in routes


class TestZenRotation:
    """A model moving from free→paid MUST be blocked. A new free model
    appearing MUST be adopted. The whole point is that a static-allowlist
    implementation would pass a naive test and fail in the real world."""

    def _setup_registry(self, tmp_path, free_models):
        _make_zen_free_json(tmp_path, free_models)
        return {
            "big-pickle": {
                "provider": "opencode-zen",
                "free": True,
            },
            "model-new-free": {
                "provider": "opencode-zen",
                "free": True,
            },
            "model-gone-paid": {
                "provider": "opencode-zen",
                "free": False,
            },
        }

    def test_new_free_model_in_list_is_adopted(self, tmp_path):
        free = {"big-pickle", "model-new-free"}
        registry = self._setup_registry(tmp_path, free)
        pool_map = {"t": ["big-pickle", "model-new-free"]}
        routes, pools, _ = build_routes_and_pools(
            registry, pool_map, {}, state_dir=str(tmp_path))
        assert "big-pickle" in routes
        assert "model-new-free" in routes

    def test_model_not_in_list_is_blocked(self, tmp_path):
        free = {"big-pickle", "model-new-free"}
        registry = self._setup_registry(tmp_path, free)
        pool_map = {"t": ["big-pickle", "model-gone-paid"]}
        routes, pools, _ = build_routes_and_pools(
            registry, pool_map, {}, state_dir=str(tmp_path))
        assert "big-pickle" in routes
        assert "model-gone-paid" not in routes

    def test_model_removed_from_list_is_blocked(self, tmp_path):
        free = {"big-pickle", "model-new-free"}
        registry = self._setup_registry(tmp_path, free)
        pool_map = {"t": ["big-pickle", "model-new-free"]}
        routes, pools, _ = build_routes_and_pools(
            registry, pool_map, {}, state_dir=str(tmp_path))
        assert "model-new-free" in routes

        save_zen_free_models({"big-pickle"}, state_dir=str(tmp_path))
        routes2, pools2, _ = build_routes_and_pools(
            registry, pool_map, {}, state_dir=str(tmp_path))
        assert "big-pickle" in routes2
        assert "model-new-free" not in routes2

    def test_model_added_to_list_is_adopted_next_refresh(self, tmp_path):
        free = {"big-pickle"}
        registry = self._setup_registry(tmp_path, free)
        pool_map = {"t": ["big-pickle", "model-new-free"]}
        routes, pools, _ = build_routes_and_pools(
            registry, pool_map, {}, state_dir=str(tmp_path))
        assert "model-new-free" not in routes

        save_zen_free_models({"big-pickle", "model-new-free"},
                             state_dir=str(tmp_path))
        routes2, pools2, _ = build_routes_and_pools(
            registry, pool_map, {}, state_dir=str(tmp_path))
        assert "model-new-free" in routes2


class TestOpencodePresetFundingClass:
    """The opencode presets carry funding_class so admission policy can
    be evaluated even without a providers.json override."""

    def test_opencode_zen_preset_has_funding_class_1(self):
        from charon import providers
        preset = providers.PRESETS["opencode-zen"]
        assert preset.funding_class == 1

    def test_opencode_go_preset_has_funding_class_2(self):
        from charon import providers
        preset = providers.PRESETS["opencode-go"]
        assert preset.funding_class == 2


class TestAdmissionViolationIsExported:
    def test_in_all(self):
        from charon import routing_policy
        assert "AdmissionViolation" in routing_policy.__all__

    def test_is_value_error(self):
        from charon.routing_policy.admission import AdmissionViolation
        exc = AdmissionViolation("test")
        assert isinstance(exc, ValueError)
