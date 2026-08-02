"""ZEN-GO-ROUTING-POLICY — FAIL-ON-REVERT tests.

Policy (operator decision 2026-08-02):
  opencode-zen  -> FREE models ONLY  (funding_class 1)
  opencode-go   -> FREE models ONLY  (funding_class 2; "very cheap" enforced as free)

Constraint fires at pool-build time (build_routes_and_pools), so it is enforced on
EVERY catalog refresh cycle — not seeded once and forgotten.
"""
from __future__ import annotations

from charon.routing_policy import (
    RoutingPolicyViolation,
    build_routes_and_pools,
)


class TestZenGoRoutingPolicyViolation:
    """Fail loud when a model violates the opencode-zen / opencode-go policy."""

    def test_opencode_zen_free_model_accepted(self) -> None:
        registry = {
            "opencode-zen/minimax-m3-free": {
                "provider": "opencode-zen",
                "upstream_model": "minimax-m3-free",
                "free": True,
            },
        }
        pool_map = {"minimax-m3-free": ["opencode-zen/minimax-m3-free"]}
        routes, pools, _ = build_routes_and_pools(registry, pool_map, {})
        assert "opencode-zen/minimax-m3-free" in routes
        assert "minimax-m3-free" in pools

    def test_opencode_go_free_model_accepted(self) -> None:
        registry = {
            "opencode-go/qwen3-coder-next": {
                "provider": "opencode-go",
                "upstream_model": "qwen3-coder-next",
                "free": True,
            },
        }
        pool_map = {"qwen3-coder-next": ["opencode-go/qwen3-coder-next"]}
        routes, pools, _ = build_routes_and_pools(registry, pool_map, {})
        assert "opencode-go/qwen3-coder-next" in routes

    def test_opencode_zen_paid_model_rejected_loudly(self) -> None:
        registry = {
            "opencode-zen/claude-opus-4-1": {
                "provider": "opencode-zen",
                "upstream_model": "claude-opus-4-1",
                "free": False,
            },
        }
        pool_map = {"claude-opus-4-1": ["opencode-zen/claude-opus-4-1"]}
        try:
            build_routes_and_pools(registry, pool_map, {})
        except RoutingPolicyViolation as exc:
            assert "claude-opus-4-1" in str(exc)
            assert "opencode-zen" in str(exc)
            assert "FREE-ONLY" in str(exc)
            return
        raise AssertionError("expected RoutingPolicyViolation was not raised")

    def test_opencode_zen_paid_model_rejected_name_has_free_suffix(self) -> None:
        registry = {
            "opencode-zen/minimax-m3-free": {
                "provider": "opencode-zen",
                "upstream_model": "minimax-m3-free",
                "free": False,
            },
        }
        pool_map = {"minimax-m3-free": ["opencode-zen/minimax-m3-free"]}
        try:
            build_routes_and_pools(registry, pool_map, {})
        except RoutingPolicyViolation as exc:
            assert "minimax-m3-free" in str(exc)
            assert "opencode-zen" in str(exc)
            return
        raise AssertionError("expected RoutingPolicyViolation was not raised")

    def test_opencode_go_paid_model_rejected_loudly(self) -> None:
        registry = {
            "opencode-go/claude-haiku-4-5": {
                "provider": "opencode-go",
                "upstream_model": "claude-haiku-4-5",
                "free": False,
            },
        }
        pool_map = {"claude-haiku-4-5": ["opencode-go/claude-haiku-4-5"]}
        try:
            build_routes_and_pools(registry, pool_map, {})
        except RoutingPolicyViolation as exc:
            assert "claude-haiku-4-5" in str(exc)
            assert "opencode-go" in str(exc)
            assert "VERY-CHEAP" in str(exc)
            return
        raise AssertionError("expected RoutingPolicyViolation was not raised")

    def test_opencode_go_free_model_accepted_despites_funding_class_2(self) -> None:
        registry = {
            "opencode-go/qwen3-coder-next": {
                "provider": "opencode-go",
                "upstream_model": "qwen3-coder-next",
                "free": True,
            },
        }
        pool_map = {"qwen3-coder-next": ["opencode-go/qwen3-coder-next"]}
        routes, pools, _ = build_routes_and_pools(registry, pool_map, {})
        assert "opencode-go/qwen3-coder-next" in routes

    def test_other_provider_paid_model_not_checked(self) -> None:
        registry = {
            "openrouter/claude-opus-4": {
                "provider": "openrouter",
                "upstream_model": "claude-opus-4",
                "free": False,
            },
        }
        pool_map = {"claude-opus-4": ["openrouter/claude-opus-4"]}
        routes, pools, _ = build_routes_and_pools(registry, pool_map, {})
        assert "openrouter/claude-opus-4" in routes

    def test_opencode_zen_rejected_across_catalog_refresh(self) -> None:
        registry = {
            "opencode-zen/claude-fable-5": {
                "provider": "opencode-zen",
                "upstream_model": "claude-fable-5",
                "free": False,
            },
        }
        pool_map = {"claude-fable-5": ["opencode-zen/claude-fable-5"]}
        try:
            build_routes_and_pools(registry, pool_map, {})
        except RoutingPolicyViolation as exc:
            assert "claude-fable-5" in str(exc)
            assert "opencode-zen" in str(exc)
            assert "FREE-ONLY" in str(exc)
            return
        raise AssertionError("expected RoutingPolicyViolation was not raised")


class TestOpencodePresetFundingClass:
    """opencode-zen and opencode-go presets carry funding_class so the policy
    can be evaluated even when no providers.json override exists."""

    def test_opencode_zen_preset_has_funding_class_1(self) -> None:
        from charon import providers as _providers_mod
        preset = _providers_mod.PRESETS["opencode-zen"]
        assert preset.funding_class == 1

    def test_opencode_go_preset_has_funding_class_2(self) -> None:
        from charon import providers as _providers_mod
        preset = _providers_mod.PRESETS["opencode-go"]
        assert preset.funding_class == 2

    def test_opencode_zen_funding_class_from_preset_not_overridden(self) -> None:
        registry = {
            "opencode-zen/some-free": {
                "provider": "opencode-zen",
                "upstream_model": "some-free",
                "free": True,
            },
        }
        pool_map = {"some-free": ["opencode-zen/some-free"]}
        routes, _, _ = build_routes_and_pools(registry, pool_map, {})
        assert "opencode-zen/some-free" in routes

    def test_opencode_zen_paid_rejected_via_preset_funding_class(self) -> None:
        registry = {
            "opencode-zen/claude-haiku-4-5": {
                "provider": "opencode-zen",
                "upstream_model": "claude-haiku-4-5",
                "free": False,
            },
        }
        pool_map = {"claude-haiku-4-5": ["opencode-zen/claude-haiku-4-5"]}
        try:
            build_routes_and_pools(registry, pool_map, {})
        except RoutingPolicyViolation:
            return
        raise AssertionError("expected RoutingPolicyViolation was not raised")


class TestRoutingPolicyViolationIsExported:
    def test_routing_policy_violation_in_all(self) -> None:
        from charon import routing_policy
        assert "RoutingPolicyViolation" in routing_policy.__all__

    def test_routing_policy_violation_is_value_error(self) -> None:
        from charon.routing_policy import RoutingPolicyViolation
        exc = RoutingPolicyViolation("test")
        assert isinstance(exc, ValueError)
