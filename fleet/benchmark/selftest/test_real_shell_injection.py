#!/usr/bin/env python3
"""Fail-on-revert proof for GRADER-REAL-SHELL-INJECTION-FIX.

The reds-replay grader runs a check_cmd template (from the OOB keys) with the untrusted
{worktree} snapshot path substituted in. It MUST run as an argv list with shell=False so that
neither the substituted path nor a hostile template can inject a shell command. Revert to
shell=True and test_shell_injection_is_neutralized goes RED (the ';' payload executes).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # fleet/benchmark on sys.path
from graders import real  # noqa: E402


def _write_keys(tmp_path: Path, check_cmd: str, unit_id: str = "u1") -> Path:
    tsv = tmp_path / "reds-replay.tsv"
    header = "unit_id\tred_id\tprefix_snapshot\tcheck_cmd\texpect_green_exit\twork_class\tnote"
    tsv.write_text(f"{header}\n{unit_id}\tr1\t-\t{check_cmd}\t0\ttest\tnote\n")
    return tsv


def test_shell_injection_is_neutralized(tmp_path, monkeypatch):
    """A check_cmd carrying shell metacharacters must NOT execute the injected command."""
    snapshot = tmp_path / "snap"
    snapshot.mkdir()
    monkeypatch.setattr(real, "REDS_REPLAY_TSV", _write_keys(tmp_path, "true; touch {worktree}/INJECTED"))

    result = real.grade_reds_replay(snapshot, "u1")

    assert not (snapshot / "INJECTED").exists(), (
        "SECURITY REGRESSION: the ';' payload executed — shell=True was reintroduced"
    )
    assert result is not None
    assert result["verdict"] == "BLOCK" and result["gate"] == "error"


def test_legit_argv_check_passes(tmp_path, monkeypatch):
    """A plain argv check_cmd with {worktree} substitution still grades MERGE on exit 0."""
    snapshot = tmp_path / "snap"
    snapshot.mkdir()
    (snapshot / "marker").write_text("x")
    monkeypatch.setattr(real, "REDS_REPLAY_TSV", _write_keys(tmp_path, "test -f {worktree}/marker"))

    result = real.grade_reds_replay(snapshot, "u1")
    assert result is not None
    assert result["verdict"] == "MERGE" and result["score"] == 100


def test_legit_argv_check_fails_on_nonzero(tmp_path, monkeypatch):
    """A plain argv check_cmd that exits non-zero grades BLOCK (no false green)."""
    snapshot = tmp_path / "snap"
    snapshot.mkdir()
    monkeypatch.setattr(real, "REDS_REPLAY_TSV", _write_keys(tmp_path, "test -f {worktree}/marker"))

    result = real.grade_reds_replay(snapshot, "u1")
    assert result is not None
    assert result["verdict"] == "BLOCK" and result["score"] == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
