"""TIER-2 — tiers compile INTO the gateway's existing pool machinery (DTC HARD REQ #2).

`tiers.json.members` is read via TIER-1's `config.load_tiers` (a separate store from the
strict `pools.json` loader) and fed through the UNCHANGED `_build_routes_and_pools`, so each
tier is published in `/v1/models` and fails over via the normal request loop. `pools.json`
wins on name collision; absent tiers → no tier vids (behavior unchanged); the `"tiers"` setup
branch persists + hot-reloads.
"""
from __future__ import annotations

import dataclasses
import json

import pytest

from charon import gateway


@pytest.fixture
def home(monkeypatch, tmp_path):
    """Point both the gateway state dir AND `config.config_dir()` (CHARON_HOME) at one tmp
    dir so `config.load_tiers()` reads the same place `models.json`/`pools.json` live."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.delenv("CHARON_GATEWAY_TOKEN", raising=False)
    return tmp_path


def _write_models(home, **models):
    (home / "models.json").write_text(json.dumps(models))


def test_tier_members_compile_into_pools_and_model_ids(home):
    """A tier's members become a `GatewayConfig.pools` chain + a `/v1/models` id, ordered
    free-first→cost_rank by the SHARED compiler (not reimplemented)."""
    _write_models(
        home,
        flash={"upstream_base": "http://flash/v1", "free": True, "cost_rank": 0},
        gpt={"upstream_base": "http://gpt/v1", "cost_rank": 10},
    )
    (home / "tiers.json").write_text(json.dumps({
        "order": ["low", "med", "high"],
        # listed paid-first; the gateway must still sort the free model first
        "members": {"low": [], "med": [], "high": ["gpt", "flash"]},
        "aliases": {},
    }))
    cfg = gateway.load_config(state_dir=home)
    assert "high" in cfg.pools and "high" in cfg.model_ids
    assert [r.upstream_base for r in cfg.pools["high"]] == ["http://flash/v1", "http://gpt/v1"]


def test_pools_json_vid_wins_on_name_collision(home):
    """An explicit `pools.json` vid is NOT overridden by a same-named tier (no surprise)."""
    _write_models(
        home,
        a={"upstream_base": "http://a/v1"},
        b={"upstream_base": "http://b/v1"},
    )
    (home / "pools.json").write_text(json.dumps({"high": ["a"]}))
    (home / "tiers.json").write_text(json.dumps({
        "order": ["low", "med", "high"],
        "members": {"low": [], "med": [], "high": ["b"]},
        "aliases": {},
    }))
    cfg = gateway.load_config(state_dir=home)
    # pools.json definition (a) wins; the tier member (b) does not leak in
    assert [r.upstream_base for r in cfg.pools["high"]] == ["http://a/v1"]


def test_absent_tiers_file_adds_no_tier_vids(home):
    """No `tiers.json` → the legacy default's bare Anthropic ids are absent from the registry,
    so zero tier pools compile and behavior is unchanged."""
    _write_models(home, kimi={"upstream_base": "http://kimi/v1", "free": True})
    cfg = gateway.load_config(state_dir=home)
    assert cfg.model_ids == ["kimi"]
    assert cfg.pools == {}


def test_setup_tiers_branch_persists_and_reloads(home):
    """The `"tiers"` setup action calls `config.set_tiers` (writes `tiers.json`) then reloads,
    so the new tier pool is live on the server immediately."""
    from charon import config

    _write_models(home, m={"upstream_base": "http://m/v1"})
    cfg = gateway.load_config(state_dir=home)
    cfg = dataclasses.replace(cfg, port=0)
    server = gateway.build_server(cfg, setup_dir=home)
    try:
        status, body = server.setup_handler("tiers", {
            "order": ["low", "med", "high"],
            "members": {"low": [], "med": [], "high": ["m"]},
            "aliases": {"opus": "high"},
        })
        assert status == 200 and body == {"ok": True}
        # persisted
        assert config.load_tiers()["members"]["high"] == ["m"]
        # hot-reloaded into the live server
        assert "high" in server.pools
        assert [r.upstream_base for r in server.pools["high"]] == ["http://m/v1"]
    finally:
        server.server_close()
