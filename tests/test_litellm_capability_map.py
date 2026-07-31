"""Assert the ADR-0021 param list matches the INSTALLED ``litellm.Router.__init__`` signature.

This test is the automated drift-guard for ADR-0021. When litellm is upgraded and gains or
loses parameters, this test goes RED — forcing a re-disposition pass. The ADR's param list
is the authoritative register; this test programmatically confirms it against the installed
library so the register cannot silently drift.

NOTE: this test deliberately imports ``litellm``. If litellm is not installed, it is skipped
with a clear message. On CI legs that don't install the `router` extra, the test is harmless.
"""
from __future__ import annotations

import inspect

import pytest

# Param list from ADR-0021 (litellm 1.93.0), enumerated 2026-07-31 via
#   inspect.signature(litellm.Router.__init__)
# Ordered as they appear in the installed signature. Excludes ``self``.
EXPECTED_PARAMS: list[str] = [
    "model_list",
    "assistants_config",
    "search_tools",
    "guardrail_list",
    "redis_url",
    "redis_host",
    "redis_port",
    "redis_password",
    "redis_db",
    "cache_responses",
    "cache_kwargs",
    "caching_groups",
    "client_ttl",
    "polling_interval",
    "default_priority",
    "num_retries",
    "max_fallbacks",
    "timeout",
    "stream_timeout",
    "default_litellm_params",
    "default_max_parallel_requests",
    "set_verbose",
    "debug_level",
    "default_fallbacks",
    "fallbacks",
    "context_window_fallbacks",
    "content_policy_fallbacks",
    "model_group_alias",
    "enable_pre_call_checks",
    "enable_tag_filtering",
    "tag_filtering_match_any",
    "retry_after",
    "retry_policy",
    "model_group_retry_policy",
    "allowed_fails",
    "allowed_fails_policy",
    "cooldown_time",
    "disable_cooldowns",
    "routing_strategy",
    "optional_pre_call_checks",
    "routing_strategy_args",
    "routing_groups",
    "provider_budget_config",
    "alerting_config",
    "router_general_settings",
    "deployment_affinity_ttl_seconds",
    "model_group_affinity_config",
    "ignore_invalid_deployments",
    "enable_health_check_routing",
    "health_check_staleness_threshold",
    "health_check_ignore_transient_errors",
    "enable_weighted_failover",
]


def _installed_params() -> list[str] | None:
    """Return Router.__init__ param names (excluding ``self``) from the INSTALLED litellm,
    or ``None`` if litellm is not importable."""
    try:
        from litellm import Router
    except ImportError:
        return None
    sig = inspect.signature(Router.__init__)
    return [p for p in sig.parameters if p != "self"]


@pytest.fixture(scope="module")
def installed() -> list[str]:
    """Skip the whole module if litellm is not installed."""
    params = _installed_params()
    if params is None:
        pytest.skip("litellm not installed (optional 'router' extra)")
    return params


# ── Core assertions ──────────────────────────────────────────────────────────


def test_param_count_matches_expected(installed: list[str]) -> None:
    """The INSTALLED Router.__init__ must have exactly 52 params (excluding self)."""
    assert len(installed) == len(EXPECTED_PARAMS), (
        f"Param count mismatch: installed={len(installed)}, "
        f"expected={len(EXPECTED_PARAMS)} (ADR-0021). "
        f"installed params: {installed}"
    )


def test_param_order_matches_expected(installed: list[str]) -> None:
    """The INSTALLED Router.__init__ param ORDER must match the ADR list.

    litellm may add params at the end; positional order should be stable.
    If this fails because litellm reordered params on upgrade, the EXPECTED_PARAMS
    list must be regenerated from the installed signature (do NOT hand-edit)."""
    assert installed == EXPECTED_PARAMS, (
        f"Param order mismatch.\n"
        f"  installed: {installed}\n"
        f"  expected:  {EXPECTED_PARAMS}\n"
        f"Regenerate EXPECTED_PARAMS from inspect.signature(litellm.Router.__init__) "
        f"and re-run the ADR-0021 disposition pass for any new params."
    )


def test_no_missing_from_adr(installed: list[str]) -> None:
    """Every installed param must appear in EXPECTED_PARAMS (nothing missing from ADR)."""
    missing = set(installed) - set(EXPECTED_PARAMS)
    assert not missing, (
        f"New params in installed litellm not covered by ADR-0021: {sorted(missing)}. "
        f"Re-run the disposition pass for these new params."
    )


def test_no_extra_in_adr(installed: list[str]) -> None:
    """Every EXPECTED_PARAMS entry must exist in the installed signature (no stale ADR entries)."""
    extra = set(EXPECTED_PARAMS) - set(installed)
    assert not extra, (
        f"Params in ADR-0021 no longer in installed litellm: {sorted(extra)}. "
        f"Remove them from EXPECTED_PARAMS and update the ADR."
    )


# ── Sanity: this test file itself has the right count ────────────────────────


def test_expected_params_has_exactly_52() -> None:
    """Sanity-check: EXPECTED_PARAMS must have exactly 52 entries (excl. self)."""
    assert len(EXPECTED_PARAMS) == 52, (
        f"EXPECTED_PARAMS has {len(EXPECTED_PARAMS)} entries; expected 52. "
        f"Did someone hand-edit the list? Regenerate from inspect.signature."
    )
