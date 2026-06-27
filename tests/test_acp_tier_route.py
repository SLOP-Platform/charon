"""Tests for AcpBackend tier-model routing (TIER-7 / DTC tier-abstraction).

Verifies that dispatch() wires the tier vid (canonical low/med/high) as
ANTHROPIC_MODEL in the agent subprocess env when the tier has members, and
preserves today's behaviour (no override) when the tier is unconfigured.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from charon.adapters.acp import AcpBackend
from charon.types import Budget, OutcomeStatus, Tier, WorkUnit

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _unit() -> WorkUnit:
    return WorkUnit(task_id="t1", goal="do the thing")


def _budget() -> Budget:
    return Budget()


def _make_backend(passthrough: dict | None = None) -> AcpBackend:
    return AcpBackend(["echo", "acp"], passthrough_env=passthrough)


def _popen_factory(captured: dict):
    """Popen stub: records the env kwarg in captured['env'], returns a mock proc."""
    def factory(cmd, **kwargs):
        captured["env"] = dict(kwargs.get("env") or {})
        m = MagicMock()
        m.stdin = MagicMock()
        m.stdout = MagicMock()
        return m
    return factory


def _rpc_stub(method: str, params: dict, **kw) -> dict:
    if method == "session/new":
        return {"sessionId": "s1"}
    return {}


# ---------------------------------------------------------------------------
# tier vid injection — happy path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tier, expected_vid", [
    (Tier.LOW,  "low"),
    (Tier.MED,  "med"),
    (Tier.HIGH, "high"),
])
def test_tier_vid_injected_as_anthropic_model(tmp_path, monkeypatch, tier, expected_vid):
    """dispatch sets ANTHROPIC_MODEL to the canonical tier vid when the tier has members."""
    monkeypatch.setattr("charon.config.tier_members", lambda t, **kw: ["some-model"])

    captured: dict = {}
    monkeypatch.setattr("subprocess.Popen", _popen_factory(captured))

    backend = _make_backend()
    monkeypatch.setattr(backend, "_rpc", _rpc_stub)
    monkeypatch.setattr("charon.gitutil.commit_all", lambda wt, msg: "abc123")

    outcome = backend.dispatch(_unit(), tier, _budget(), tmp_path, {})

    assert outcome.status == OutcomeStatus.PROGRESSED
    assert captured["env"].get("ANTHROPIC_MODEL") == expected_vid


# ---------------------------------------------------------------------------
# absent / unconfigured tier → no regression
# ---------------------------------------------------------------------------

def test_absent_tier_config_no_model_override(tmp_path, monkeypatch):
    """dispatch does NOT set ANTHROPIC_MODEL when tier_members returns empty."""
    monkeypatch.setattr("charon.config.tier_members", lambda t, **kw: [])

    captured: dict = {}
    monkeypatch.setattr("subprocess.Popen", _popen_factory(captured))

    backend = _make_backend()
    monkeypatch.setattr(backend, "_rpc", _rpc_stub)
    monkeypatch.setattr("charon.gitutil.commit_all", lambda wt, msg: "abc123")

    backend.dispatch(_unit(), Tier.MED, _budget(), tmp_path, {})

    assert "ANTHROPIC_MODEL" not in captured["env"]


# ---------------------------------------------------------------------------
# passthrough_env wins over the tier vid
# ---------------------------------------------------------------------------

def test_passthrough_env_wins_over_tier_vid(tmp_path, monkeypatch):
    """passthrough_env is merged AFTER env in _start, so an explicit model overrides
    the injected tier vid — the operator can still pin a concrete model."""
    monkeypatch.setattr("charon.config.tier_members", lambda t, **kw: ["some-model"])

    captured: dict = {}
    monkeypatch.setattr("subprocess.Popen", _popen_factory(captured))

    backend = _make_backend(passthrough={"ANTHROPIC_MODEL": "explicit-model"})
    monkeypatch.setattr(backend, "_rpc", _rpc_stub)
    monkeypatch.setattr("charon.gitutil.commit_all", lambda wt, msg: "abc123")

    backend.dispatch(_unit(), Tier.MED, _budget(), tmp_path, {})

    assert captured["env"].get("ANTHROPIC_MODEL") == "explicit-model"


# ---------------------------------------------------------------------------
# caller env is not mutated
# ---------------------------------------------------------------------------

def test_caller_env_not_mutated(tmp_path, monkeypatch):
    """dispatch must not modify the caller's env dict."""
    monkeypatch.setattr("charon.config.tier_members", lambda t, **kw: ["some-model"])
    monkeypatch.setattr("subprocess.Popen", _popen_factory({}))

    backend = _make_backend()
    monkeypatch.setattr(backend, "_rpc", _rpc_stub)
    monkeypatch.setattr("charon.gitutil.commit_all", lambda wt, msg: "abc123")

    original = {"HOME": "/home/test"}
    caller_env = dict(original)
    backend.dispatch(_unit(), Tier.MED, _budget(), tmp_path, caller_env)

    assert caller_env == original


# ---------------------------------------------------------------------------
# caps keyed on canonical tier — the tier vid IS the canonical string
# ---------------------------------------------------------------------------

def test_canonical_tier_values():
    """Tier.value is the canonical low/med/high string used as both the cap key
    and the model id — one vocabulary, no translation shim (DTC HARD REQ)."""
    assert Tier.LOW.value == "low"
    assert Tier.MED.value == "med"
    assert Tier.HIGH.value == "high"
