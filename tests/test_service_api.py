"""Read-only API helpers behind the web dashboard (ADR-0004 D7/R3).

These run in the core gate (no [service] extra needed) — they exercise the
listing/config functions directly, no HTTP. The FastAPI layer is covered by
test_service_ui.py (skipped when the extra is absent).
"""
from __future__ import annotations

import json
from pathlib import Path

from charon import api


def _make_complete_run(state: Path, goal: str = "make hello") -> str:
    out = api.run_task(goal=goal, accept=["test -f hello.txt"],
                       state_dir=str(state), backend_name="mock", autonomy="L1")
    assert out["status"] == "complete"
    return out["task_id"]


def test_list_ledgers_summarizes_and_skips_non_ledgers(tmp_path: Path) -> None:
    state = tmp_path / ".charon"
    task_id = _make_complete_run(state)

    runs = api.list_ledgers(str(state))
    assert len(runs) == 1  # the sandbox/ dir (no ledger.json) is skipped
    r = runs[0]
    assert r["task_id"] == task_id
    assert r["status"] == "complete" and r["remaining"] == []
    assert r["verified"] == ["a0"]
    assert "usage" in r and "providers" in r and "checkpoints" in r


def test_list_ledgers_missing_dir_is_empty(tmp_path: Path) -> None:
    assert api.list_ledgers(str(tmp_path / "nope")) == []


def test_list_ledgers_tolerates_a_corrupt_neighbour(tmp_path: Path) -> None:
    state = tmp_path / ".charon"
    _make_complete_run(state)
    # a junk dir that looks like a task but has unreadable metadata must not crash
    bad = state / "broken-task"
    bad.mkdir()
    (bad / "ledger.json").write_text("{ not json")
    runs = api.list_ledgers(str(state))
    assert len(runs) == 1 and runs[0]["status"] == "complete"


def test_show_config_reads_models_and_pools(tmp_path: Path) -> None:
    state = tmp_path / ".charon"
    state.mkdir(parents=True)
    models = {"opencode-go/kimi": {"cost_tier": "flat", "code_safe": True,
                                   "key_env": "OPENCODE_API_KEY"}}
    pools = {"coder": ["opencode-go/kimi"]}
    (state / "models.json").write_text(json.dumps(models))
    (state / "pools.json").write_text(json.dumps(pools))

    cfg = api.show_config(str(state))
    assert cfg["models"] == models and cfg["pools"] == pools
    # no provider secret is exposed — only the key *env* name
    assert "key_env" in cfg["models"]["opencode-go/kimi"]


def test_show_config_allowlists_model_fields_drops_stray_secret(tmp_path: Path) -> None:
    state = tmp_path / ".charon"
    state.mkdir(parents=True)
    # an operator fat-fingers an inline key into models.json — it must NOT survive
    models = {"opencode-go/kimi": {"cost_tier": "flat", "code_safe": True,
                                   "key_env": "OPENCODE_API_KEY",
                                   "api_key": "sk-LEAKED-should-be-dropped"}}
    (state / "models.json").write_text(json.dumps(models))
    cfg = api.show_config(str(state))
    entry = cfg["models"]["opencode-go/kimi"]
    assert "api_key" not in entry and "sk-LEAKED" not in json.dumps(cfg)
    assert entry["key_env"] == "OPENCODE_API_KEY" and entry["cost_tier"] == "flat"


def test_show_config_absent_files_are_none(tmp_path: Path) -> None:
    state = tmp_path / ".charon"
    state.mkdir()
    cfg = api.show_config(str(state))
    assert cfg["models"] is None and cfg["pools"] is None


def test_show_config_invalid_json_surfaces_error_not_crash(tmp_path: Path) -> None:
    state = tmp_path / ".charon"
    state.mkdir()
    (state / "models.json").write_text("{ broken")
    cfg = api.show_config(str(state))
    assert "error" in cfg["models"]
