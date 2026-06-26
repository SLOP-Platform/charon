"""The web entrypoint's bind guard (ADR-0004 D7) and the privileged worker
(Tier 2b). Pure stdlib — runs in the core gate (no [service] extra needed)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from charon.service.__main__ import _is_loopback, main


def test_loopback_classification() -> None:
    assert _is_loopback("127.0.0.1")
    assert _is_loopback("::1")
    assert _is_loopback("localhost")
    # all-interfaces binds are EXPOSED, not loopback (the set-but-empty hole)
    assert not _is_loopback("")
    assert not _is_loopback("0.0.0.0")
    assert not _is_loopback("::")
    assert not _is_loopback("203.0.113.10")
    assert not _is_loopback("example.com")


def test_non_loopback_without_token_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHARON_SERVICE_TOKEN", raising=False)
    monkeypatch.setenv("CHARON_SERVICE_HOST", "0.0.0.0")
    assert main() == 2  # refused before ever importing/binding uvicorn


def test_empty_host_without_token_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHARON_SERVICE_TOKEN", raising=False)
    monkeypatch.setenv("CHARON_SERVICE_HOST", "")  # binds all interfaces
    assert main() == 2


# ---------------------------------------------------------------------------
# Tier 2b: worker (service/worker.py)
# ---------------------------------------------------------------------------

def test_worker_exits_2_without_queue_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHARON_QUEUE_DIR", raising=False)
    from charon.service.worker import main as worker_main
    assert worker_main(_once=True) == 2


def test_worker_poll_once_empty_queue_is_noop(tmp_path: Path) -> None:
    from charon.service.worker import _poll_once
    qd = tmp_path / "queue"
    assert _poll_once(qd, str(tmp_path / ".charon")) is False


def test_worker_poll_once_missing_queue_dir_is_noop(tmp_path: Path) -> None:
    from charon.service.worker import _poll_once
    assert _poll_once(tmp_path / "nonexistent", str(tmp_path / ".charon")) is False


def test_worker_poll_once_picks_up_job_and_archives_to_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import charon.service.worker as wmod
    from charon.service.worker import _poll_once

    qd = tmp_path / "queue"
    pending = qd / "pending"
    pending.mkdir(parents=True)
    job = {"job_id": "abc123", "goal": "hello", "accept": ["true"],
           "autonomy": "L0", "budget": 4}
    (pending / "abc123.json").write_text(json.dumps(job))

    monkeypatch.setattr(wmod._api, "run_task", lambda **kw: {"status": "complete"})

    result = _poll_once(qd, str(tmp_path / ".charon"))
    assert result is True
    # pending file is gone; done file exists with result folded in
    assert not (pending / "abc123.json").exists()
    done_file = qd / "done" / "abc123.json"
    assert done_file.is_file()
    record = json.loads(done_file.read_text())
    assert record["result"]["status"] == "complete"
    assert record["goal"] == "hello"


def test_worker_poll_once_archives_to_failed_on_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import charon.service.worker as wmod
    from charon.service.worker import _poll_once

    qd = tmp_path / "queue"
    pending = qd / "pending"
    pending.mkdir(parents=True)
    job = {"job_id": "errjob", "goal": "fail", "accept": ["false"]}
    (pending / "errjob.json").write_text(json.dumps(job))

    def _raise(**kw: object) -> dict:
        raise RuntimeError("backend unavailable")

    monkeypatch.setattr(wmod._api, "run_task", _raise)

    result = _poll_once(qd, str(tmp_path / ".charon"))
    assert result is True
    assert not (pending / "errjob.json").exists()
    fail_file = qd / "failed" / "errjob.json"
    assert fail_file.is_file()
    record = json.loads(fail_file.read_text())
    assert "backend unavailable" in record["error"]


def test_worker_poll_once_tolerates_malformed_job(tmp_path: Path) -> None:
    from charon.service.worker import _poll_once

    qd = tmp_path / "queue"
    pending = qd / "pending"
    pending.mkdir(parents=True)
    (pending / "badjob.json").write_text("{ not json }")

    # malformed JSON → job moves to failed, no crash
    result = _poll_once(qd, str(tmp_path / ".charon"))
    assert result is True
    assert not (pending / "badjob.json").exists()
    # file ends up in failed/
    assert (qd / "failed" / "badjob.json").is_file()
