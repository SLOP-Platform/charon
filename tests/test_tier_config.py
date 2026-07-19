"""Tier config store (DTC tier-abstraction).

Proves the canonical ``low/med/high`` vocabulary with ``opus/sonnet/haiku`` +
``frontier/strong/economy`` as aliases: round-trip set/load, absent-file legacy
default + legacy ranks, alias-folding, stored member order, and order-index ranks.
"""
from __future__ import annotations

import pytest

from charon import config


def test_set_load_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.set_tiers(
        order=["low", "med", "high"],
        members={"low": ["gemini-flash", "haiku"], "med": ["sonnet"],
                 "high": ["opus", "deepseek-r1"]},
        aliases={"opus": "high", "Strong": "med"},
    )
    t = config.load_tiers()
    assert t["order"] == ["low", "med", "high"]
    assert t["members"]["low"] == ["gemini-flash", "haiku"]
    assert t["members"]["high"] == ["opus", "deepseek-r1"]
    assert t["aliases"]["opus"] == "high"
    assert t["aliases"]["strong"] == "med"  # alias name folded to lowercase on write


def test_absent_file_legacy_default_and_ranks(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    t = config.load_tiers()  # nothing written → legacy default
    assert t["order"] == ["low", "med", "high"]
    assert t["members"] == {"low": ["haiku"], "med": ["sonnet"], "high": ["opus"]}
    # legacy ranks fall out of the 1-based order index
    assert config.tier_rank("opus") == 3
    assert config.tier_rank("sonnet") == 2
    assert config.tier_rank("haiku") == 1
    assert config.tier_rank("high") == 3
    assert config.tier_rank("low") == 1
    assert config.tier_rank("nope") == 0  # unknown → 0 (matches the fleet ${RANK:-0})


def test_resolve_tier_folds_aliases(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    # legacy fallback works even with no file present
    assert config.resolve_tier("opus") == "high"
    assert config.resolve_tier("strong") == "med"
    assert config.resolve_tier("economy") == "low"
    assert config.resolve_tier("HIGH") == "high"  # canonical, case-insensitive
    assert config.resolve_tier(" Haiku ") == "low"  # trimmed + folded
    with pytest.raises(ValueError):
        config.resolve_tier("frontiermost")


def test_tier_members_returns_stored_order(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.set_tiers(
        order=["low", "med", "high"],
        members={"low": [], "med": ["sonnet"], "high": ["opus", "deepseek-r1"]},
        aliases={"frontier": "high"},
    )
    assert config.tier_members("high") == ["opus", "deepseek-r1"]  # stored order preserved
    assert config.tier_members("frontier") == ["opus", "deepseek-r1"]  # via alias
    assert config.tier_members("low") == []


def test_tier_rank_matches_order_index(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.set_tiers(
        order=["low", "med", "high"],
        members={"low": ["haiku"], "med": ["sonnet"], "high": ["opus"]},
        aliases={"opus": "high", "haiku": "low"},
    )
    assert config.tier_rank("low") == 1
    assert config.tier_rank("med") == 2
    assert config.tier_rank("high") == 3
    assert config.tier_rank("opus") == 3  # alias-folded


def test_set_tiers_validation(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    with pytest.raises(ValueError):  # non-canonical tier in order
        config.set_tiers(order=["low", "med", "huge"], members={}, aliases={})
    with pytest.raises(ValueError):  # order missing a canonical tier
        config.set_tiers(order=["low", "med"], members={}, aliases={})
    with pytest.raises(ValueError):  # invalid model id
        config.set_tiers(order=["low", "med", "high"],
                         members={"low": ["bad id"], "med": [], "high": []}, aliases={})
    with pytest.raises(ValueError):  # alias targets a non-canonical tier
        config.set_tiers(order=["low", "med", "high"],
                         members={"low": [], "med": [], "high": []},
                         aliases={"opus": "huge"})
