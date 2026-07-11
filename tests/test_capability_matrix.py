"""CapabilityMatrix data + query API tests.

Covers the static provider-quirk rules (reasoning-incapable providers) and the
grade query API. This module is **not yet wired** into the gateway / forwarder —
that is out of scope (later ticket / R4 work).
"""
from __future__ import annotations

import pytest

from charon.routing_policy.matrix import CapabilityMatrix, Grade, WorkClass, _DEFAULT_PROVIDER_DENIES


class TestQueryAPI:
    """Grade lookup + provider capability queries."""

    def test_get_grade_missing_returns_unknown(self):
        m = CapabilityMatrix()
        assert m.get_grade("gpt-4", "reasoning") == "unknown"

    def test_set_and_get_grade(self):
        m = CapabilityMatrix()
        m.set_grade("gpt-4", "reasoning", grade="A", confidence=0.9)
        assert m.get_grade("gpt-4", "reasoning") == "A"

    def test_set_grade_overwrites_prior(self):
        m = CapabilityMatrix()
        m.set_grade("gpt-4", "coding", grade="B")
        m.set_grade("gpt-4", "coding", grade="A")
        assert m.get_grade("gpt-4", "coding") == "A"

    def test_supports_unknown_provider_defaults_true(self):
        """Providers not listed in the quirk table should default to True
        (safe assumption — no data means not known-bad)."""
        m = CapabilityMatrix()
        assert m.supports("some-new-provider", "reasoning") is True
        assert m.supports("deepseek", "coding") is True

    def test_supports_openrouter_reasoning_is_false(self):
        m = CapabilityMatrix()
        assert m.supports("openrouter", "reasoning") is False

    def test_supports_openrouter_other_classes_still_true(self):
        m = CapabilityMatrix()
        assert m.supports("openrouter", "coding") is True
        assert m.supports("openrouter", "general") is True
        assert m.supports("openrouter", "analysis") is True

    def test_supports_novita_reasoning_is_false(self):
        m = CapabilityMatrix()
        assert m.supports("novita", "reasoning") is False

    def test_supports_novita_other_classes_still_true(self):
        m = CapabilityMatrix()
        assert m.supports("novita", "creative") is True
        assert m.supports("novita", "translation") is True


class TestProviderDenyAllow:
    """Mutation of provider-level denials."""

    def test_deny_adds_restriction(self):
        m = CapabilityMatrix()
        m.deny("deepseek", "reasoning")
        assert m.supports("deepseek", "reasoning") is False

    def test_allow_removes_restriction(self):
        m = CapabilityMatrix()
        # openrouter is denied reasoning by default
        assert m.supports("openrouter", "reasoning") is False
        m.allow("openrouter", "reasoning")
        assert m.supports("openrouter", "reasoning") is True

    def test_allow_on_unknown_provider_is_noop(self):
        m = CapabilityMatrix()
        m.allow("brand-new", "reasoning")
        assert m.supports("brand-new", "reasoning") is True


class TestDefaultProviderDenies:
    """The built-in static quirk table matches ROUTER-DESIGN.md."""

    def test_defaults_include_openrouter_and_novita(self):
        assert "openrouter" in _DEFAULT_PROVIDER_DENIES
        assert "novita" in _DEFAULT_PROVIDER_DENIES
        assert _DEFAULT_PROVIDER_DENIES["openrouter"] == {"reasoning"}
        assert _DEFAULT_PROVIDER_DENIES["novita"] == {"reasoning"}

    def test_defaults_are_seeded_on_init(self):
        m = CapabilityMatrix()
        # not relying on _DEFAULT_PROVIDER_DENIES directly — exercise the instance
        assert m.supports("openrouter", "reasoning") is False
        assert m.supports("novita", "reasoning") is False

    def test_defaults_overrideable(self):
        """Caller can pass an explicit provider_denies to override defaults."""
        m = CapabilityMatrix(provider_denies={"openrouter": set()})
        assert m.supports("openrouter", "reasoning") is True
        assert m.supports("novita", "reasoning") is False  # still present via default

    @pytest.mark.parametrize("wc", ["reasoning", "coding", "translation", "creative", "analysis", "general"])
    def test_all_work_classes_are_valid_literals(self, wc: str):
        """Smoke: every WorkClass literal can round-trip through the API."""
        m = CapabilityMatrix()
        m.set_grade("m1", wc, "A")  # type: ignore[arg-type]
        assert m.get_grade("m1", wc) == "A"  # type: ignore[arg-type]
