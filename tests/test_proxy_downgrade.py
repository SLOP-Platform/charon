"""Regression: silent-downgrade detection must compare the FINAL model-id path
segment, not the raw string (backport of SR-1 to v0.2.0).

Before the fix, ``classify()`` did a raw ``returned != expected`` equality check,
so a provider that echoes a fully-qualified id (``accounts/fireworks/models/
deepseek-v4-pro``) for a bare request (``deepseek-v4-pro``) was flagged as a
silent downgrade → the failover loop discarded an already-billed 200 and
refetched → double-bill. Comparing only the last ``/``-segment fixes it while
still catching a genuinely different model family.
"""
from __future__ import annotations

from charon.proxy import GatewayProxy


def test_provider_qualified_echo_is_not_pseudo_success() -> None:
    # the live double-bill case: provider echoes a fully-qualified id for a bare
    # request. Same final segment → NOT a downgrade. (Fails before the fix.)
    p = GatewayProxy()
    obs = p.classify("deepseek-v4-pro", 200,
                     body={"model": "accounts/fireworks/models/deepseek-v4-pro"},
                     expected_model="deepseek-v4-pro")
    assert obs.pseudo_success is False


def test_bare_exact_match_is_not_pseudo_success() -> None:
    p = GatewayProxy()
    obs = p.classify("deepseek-v4-pro", 200,
                     body={"model": "deepseek-v4-pro"},
                     expected_model="deepseek-v4-pro")
    assert obs.pseudo_success is False


def test_single_prefix_return_is_not_pseudo_success() -> None:
    # returned carries one provider prefix over the bare expected id → same
    # final segment → not a downgrade.
    p = GatewayProxy()
    obs = p.classify("gpt-4", 200,
                     body={"model": "openai/gpt-4"},
                     expected_model="gpt-4")
    assert obs.pseudo_success is False


def test_genuine_family_difference_is_still_pseudo_success() -> None:
    # guard: a real downgrade to a different family must STILL be flagged.
    p = GatewayProxy()
    obs = p.classify("opus", 200,
                     body={"model": "haiku"},
                     expected_model="opus")
    assert obs.pseudo_success is True
