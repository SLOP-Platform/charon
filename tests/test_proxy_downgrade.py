"""SR-1 regression — namespaced model-id normalization (double-bill guard).

A provider that echoes a FULLY-QUALIFIED model id
("accounts/fireworks/models/deepseek-v4-pro") for a bare requested/expected id
("deepseek-v4-pro") is serving the SAME model. The old normalizer stripped only
the first path segment, leaving "fireworks/models/deepseek-v4-pro" != the bare
id, so every honest 200 was flagged as a silent downgrade — discarded
(count_usage=False) and refetched from the next provider, double-billing the
already-completed request. Fix: compare the FINAL path segment.
"""
from __future__ import annotations

from charon.proxy import GatewayProxy


def test_fully_qualified_return_is_not_pseudo_success() -> None:
    # The exact live case: a 200 whose returned id is fully namespaced while the
    # expected id is bare. Same model → NOT a silent downgrade, must be served.
    p = GatewayProxy()
    obs = p.observe("fireworks/deepseek-v4-pro", 200,
                    body={"model": "accounts/fireworks/models/deepseek-v4-pro",
                          "usage": {"prompt_tokens": 10, "completion_tokens": 5}},
                    expected_model="deepseek-v4-pro")
    assert not obs.pseudo_success and not obs.failover
    assert obs.usage is not None and obs.usage.tokens == 15
    assert p.exhausted_models() == set()


def test_bare_match_is_not_pseudo_success() -> None:
    # Bare id == bare id → same model, served.
    p = GatewayProxy()
    obs = p.observe("deepseek-v4-pro", 200,
                    body={"model": "deepseek-v4-pro", "usage": {"prompt_tokens": 3}},
                    expected_model="deepseek-v4-pro")
    assert not obs.pseudo_success and not obs.failover


def test_single_prefix_return_is_not_pseudo_success() -> None:
    # Single provider prefix vs bare expected → same model, served.
    p = GatewayProxy()
    obs = p.observe("openai/gpt-4", 200,
                    body={"model": "openai/gpt-4", "usage": {"prompt_tokens": 4}},
                    expected_model="gpt-4")
    assert not obs.pseudo_success and not obs.failover


def test_genuine_family_difference_still_flags_downgrade() -> None:
    # Regression guard: the fix must NOT disable downgrade detection. A different
    # model family (opus vs haiku) is a REAL silent downgrade — still fail over.
    p = GatewayProxy()
    obs = p.observe("anthropic/opus", 200,
                    body={"model": "anthropic/haiku", "usage": {"prompt_tokens": 6}},
                    expected_model="opus")
    assert obs.pseudo_success and obs.failover
    assert "silent downgrade" in obs.note
