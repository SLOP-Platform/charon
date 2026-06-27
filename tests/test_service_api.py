"""Read-only API helpers behind the web dashboard (ADR-0004 D7/R3) and
the enqueue / worker helpers added in Tier 2b.

Core-gate tests (no [service] extra needed) exercise listing/config functions
directly.  HTTP-layer tests require the [service] extra and are guarded with
``pytest.importorskip``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

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


# ---------------------------------------------------------------------------
# Tier 2b: enqueue helper (no [service] extra needed for the stdlib side)
# ---------------------------------------------------------------------------

def test_enqueue_writes_job_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from charon.service.app import RunRequest, _enqueue

    qd = tmp_path / "queue"
    monkeypatch.setenv("CHARON_QUEUE_DIR", str(qd))

    req = RunRequest(goal="make hello", accept=["test -f hello.txt"])
    job_id = _enqueue(req)

    job_file = qd / "pending" / f"{job_id}.json"
    assert job_file.is_file()
    job = json.loads(job_file.read_text())
    assert job["job_id"] == job_id
    assert job["goal"] == "make hello"
    assert job["accept"] == ["test -f hello.txt"]
    assert job["autonomy"] == "L0"
    assert job["budget"] == 8
    # no `repo` field: worker always uses an auto-created sandbox
    assert "repo" not in job


def test_enqueue_generates_unique_job_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    from charon.service.app import RunRequest, _enqueue

    monkeypatch.setenv("CHARON_QUEUE_DIR", str(tmp_path / "queue"))
    req = RunRequest(goal="do something", accept=["true"])
    ids = {_enqueue(req) for _ in range(5)}
    assert len(ids) == 5  # all distinct


def test_enqueue_503_when_queue_dir_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    from fastapi import HTTPException

    from charon.service.app import RunRequest, _enqueue

    monkeypatch.delenv("CHARON_QUEUE_DIR", raising=False)
    with pytest.raises(HTTPException) as exc_info:
        _enqueue(RunRequest(goal="x", accept=["true"]))
    assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# Tier 2b: HTTP round-trip for POST /v1/runs (requires [service] extra)
# ---------------------------------------------------------------------------

def test_post_runs_returns_202_and_queues_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from charon.service.app import app

    qd = tmp_path / "queue"
    monkeypatch.setenv("CHARON_QUEUE_DIR", str(qd))
    monkeypatch.delenv("CHARON_SERVICE_TOKEN", raising=False)

    client = TestClient(app, raise_server_exceptions=True)
    resp = client.post("/v1/runs", json={"goal": "build it", "accept": ["true"]})

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    job_id = body["job_id"]
    assert (qd / "pending" / f"{job_id}.json").is_file()


def test_post_runs_without_token_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from charon.service.app import app

    monkeypatch.setenv("CHARON_QUEUE_DIR", str(tmp_path / "queue"))
    monkeypatch.setenv("CHARON_SERVICE_TOKEN", "secret")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/v1/runs", json={"goal": "x", "accept": ["true"]})
    assert resp.status_code == 401


def test_post_runs_503_when_queue_not_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from charon.service.app import app

    monkeypatch.delenv("CHARON_QUEUE_DIR", raising=False)
    monkeypatch.delenv("CHARON_SERVICE_TOKEN", raising=False)

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/v1/runs", json={"goal": "x", "accept": ["true"]})
    assert resp.status_code == 503
