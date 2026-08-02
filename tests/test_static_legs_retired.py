"""SW-STATIC-LEGS-RETIRE — FAIL-ON-REVERT tests.

Discovery is the SOLE source of pool membership.  The static catalog's
``enabled: false`` silent-filter is RETIRED from the selection path.

Guards, each MUST go RED when the retirement is reverted:
  1. An entry with ``"enabled": false`` no longer vanishes silently — it
     appears in routes and pools.
  2. NON-VACUOUS: the test registry has real entries so an empty-result
     would be a genuine failure, not a silent pass.
"""
from __future__ import annotations

from charon.routing_policy import build_routes_and_pools

_PROVIDERS = {
    "openrouter": {"base_url": "https://openrouter/v1", "key_env": "OR_KEY"},
    "together": {"base_url": "https://together/v1", "key_env": "TG_KEY"},
    "deepseek": {"base_url": "https://deepseek/v1", "key_env": "DS_KEY"},
}


def _registry() -> dict:
    return {
        "tester/model-pinned": {
            "provider": "openrouter",
            "upstream_base": "https://openrouter/v1",
            "key_env": "OR_KEY",
            "upstream_model": "hand-pinned-variant",
            "enabled": True,
        },
        "tester/model-normal": {
            "provider": "together",
            "upstream_base": "https://together/v1",
            "key_env": "TG_KEY",
            "enabled": True,
        },
        "tester/hidden-model": {
            "provider": "deepseek",
            "upstream_base": "https://deepseek/v1",
            "key_env": "DS_KEY",
            "upstream_model": "deepseek-pinned",
            "enabled": False,
        },
    }


def _pool_map() -> dict:
    return {
        "pool-main": [
            "tester/model-pinned",
            "tester/model-normal",
            "tester/hidden-model",
        ],
    }


def test_enabled_false_not_silently_hidden():
    """FAIL-ON-REVERT: ``"enabled": false`` MUST NOT silently drop a model from
    routes or pools.  Re-introduce the filter → RED."""
    registry = _registry()
    routes, pools, _ = build_routes_and_pools(registry, _pool_map(), _PROVIDERS)

    assert "tester/model-pinned" in routes, "non-vacuous: normal model must exist"
    assert "tester/model-normal" in routes, "non-vacuous: normal model must exist"
    assert "tester/hidden-model" in routes, (
        "enabled=false model 'hidden-model' was SILENTLY DROPPED from routes — "
        "the static-leg filter is still active (REVERTED)"
    )

    pool_members = [r.model_id for r in pools.get("pool-main", [])]
    assert "tester/hidden-model" in pool_members, (
        "enabled=false model 'hidden-model' was SILENTLY DROPPED from pool-main — "
        "the static-leg filter is still active (REVERTED)"
    )


def test_disabled_model_still_routable():
    """FAIL-ON-REVERT: the previously-hidden model routes correctly with its
    configured upstream_base and provider."""
    registry = _registry()
    routes, _, _ = build_routes_and_pools(registry, _pool_map(), _PROVIDERS)

    hidden = routes["tester/hidden-model"]
    assert hidden.provider == "deepseek", "hidden model provider mismatch"
    assert hidden.upstream_base == "https://deepseek/v1", "hidden model base mismatch"
    assert hidden.upstream_model == "deepseek-pinned", (
        "hidden model upstream_model mismatch — field should still be read, "
        "only the enabled=false filter is retired"
    )


def test_pinned_upstream_model_still_on_route():
    """FAIL-ON-REVERT GUARD: hand-pinned ``upstream_model`` IS still read onto
    the route (wire routing field, not membership).  If this unexpectedly goes
    GREEN (None), something was over-retired — the code path still serves the
    wire rewrite."""
    registry = _registry()
    routes, _, _ = build_routes_and_pools(registry, _pool_map(), _PROVIDERS)

    pinned = routes["tester/model-pinned"]
    assert pinned.upstream_model == "hand-pinned-variant", (
        "hand-pinned upstream_model should still be on the route for wire "
        "routing — only the enabled=false membership filter is retired.  "
        "If this is None, something else was incidentally broken."
    )


def test_non_vacuous_empty_registry_is_red():
    """FAIL-LOUD: zero fixtures examined is a RED condition."""
    registry: dict = {}
    pool_map = {"pool-none": ["nonexistent"]}
    routes, pools, _ = build_routes_and_pools(registry, pool_map, _PROVIDERS)

    assert len(routes) == 0, (
        f"non-vacuous: expected 0 routes from empty registry, got {len(routes)}"
    )
    assert len(pools) == 0, (
        f"non-vacuous: expected 0 pools from empty registry, got {len(pools)}"
    )


def test_no_pool_member_lost_by_enabled_false():
    """A pool that includes an enabled=false model must not lose any other
    members.  Only the disabled model is gained (from invisible→visible)."""
    registry = _registry()
    _, pools, _ = build_routes_and_pools(registry, _pool_map(), _PROVIDERS)

    pool_main = pools.get("pool-main", [])
    member_ids = {r.model_id for r in pool_main}

    assert "tester/model-pinned" in member_ids, (
        "model-pinned lost — removal of enabled=false filter should not drop other models"
    )
    assert "tester/model-normal" in member_ids, (
        "model-normal lost — removal of enabled=false filter should not drop other models"
    )
    assert "tester/hidden-model" in member_ids, (
        "hidden-model still missing — enabled=false filter still active"
    )
    assert len(member_ids) == 3, (
        f"expected 3 pool members, got {len(member_ids)}: {member_ids}"
    )
