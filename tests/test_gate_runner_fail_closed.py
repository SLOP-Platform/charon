"""Fail-on-revert: the CHARON-GATE runner must FAIL CLOSED on a bad manifest.

``gate_runner._verify_gate_registry_wired`` used to ``return 0`` when
``tools/gates.json`` was missing or unparseable. That meant a deleted, renamed,
truncated or malformed manifest silently skipped the registry-wiring
verification and the runner went on to print a pass — "could not determine"
rendering as "all gates passed", i.e. a false receipt on the merge path.

Every test below goes RED if that fail-open ``return 0`` is restored.

Choice recorded for the EMPTY case: an empty manifest is treated as an ERROR,
not as an explicit "no gates configured" mode. There is no caller that
legitimately runs the gate without a manifest (``python3 -m charon.cli gate``
is repo-root-only and ``tools/gates.json`` is git-tracked), and
``tools/check_gate_registry.py`` already rejects an empty manifest — so an
opt-out here would be a hole no real flow needs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from charon import gate_runner

VALID_MANIFEST = [
    {
        "id": "example-gate",
        "domain": "example",
        "enforcer": "tools/check_example.py",
        "ci_step": False,
    }
]


@pytest.fixture
def manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the runner at a throwaway manifest under tmp_path.

    Never lets a test touch the live repo's real tools/gates.json.
    """
    path = tmp_path / "gates.json"
    monkeypatch.setattr(gate_runner, "_gates_json_path", lambda: path)
    return path


def _run_and_capture(capsys) -> tuple[int, str]:
    rc = gate_runner._verify_gate_registry_wired()
    return rc, capsys.readouterr().err


def test_missing_manifest_is_nonzero_and_names_the_file(manifest, capsys) -> None:
    """A DELETED or renamed manifest must be a hard error, not a silent pass."""
    assert not manifest.exists()
    rc, err = _run_and_capture(capsys)
    assert rc != 0, "a MISSING gates.json must not report a pass"
    assert "gates.json" in err
    assert "not found" in err


@pytest.mark.parametrize(
    ("label", "content", "expected_reason"),
    [
        ("truncated", '[{"id": "truncated"', "not valid JSON"),
        ("garbage", "{ not json at all", "not valid JSON"),
        ("zero-byte", "", "empty"),
        ("whitespace-only", "   \n\t ", "empty"),
        ("empty-array", "[]", "no gates"),
        ("not-an-array", '{"id": "not-an-array"}', "JSON array"),
    ],
)
def test_unusable_manifest_is_nonzero_and_names_the_failure_mode(
    manifest, capsys, label: str, content: str, expected_reason: str
) -> None:
    """Every unusable manifest shape must exit non-zero naming file and reason."""
    manifest.write_text(content)
    rc, err = _run_and_capture(capsys)
    assert rc != 0, f"a {label} gates.json must not report a pass"
    assert "gates.json" in err, f"{label}: reason must name the file"
    assert expected_reason in err, f"{label}: reason must name the failure mode"


def test_unreadable_manifest_is_nonzero(manifest, capsys) -> None:
    """A manifest that exists but cannot be opened is also a hard error."""
    manifest.write_text(json.dumps(VALID_MANIFEST))
    manifest.chmod(0o000)
    try:
        rc, err = _run_and_capture(capsys)
    finally:
        manifest.chmod(0o644)
    if rc == 0:  # running as root: permissions are unenforceable
        pytest.skip("filesystem permissions not enforced for this user")
    assert "gates.json" in err


def test_valid_manifest_verifies_clean(manifest, capsys) -> None:
    """Anti-over-block: a good manifest must still pass the registry check."""
    manifest.write_text(json.dumps(VALID_MANIFEST))
    rc, _err = _run_and_capture(capsys)
    assert rc == 0


def test_unwired_ci_step_gate_still_detected(manifest, capsys) -> None:
    """No regression: the original mismatch detection still fires."""
    manifest.write_text(
        json.dumps(
            [
                {
                    "id": "orphaned-gate",
                    "domain": "example",
                    "enforcer": "tools/check_never_wired.py",
                    "ci_step": True,
                }
            ]
        )
    )
    rc, err = _run_and_capture(capsys)
    assert rc != 0
    assert "GATE-REGISTRY-MISMATCH" in err
    assert "orphaned-gate" in err


def test_run_gate_returns_nonzero_when_manifest_missing(manifest, monkeypatch) -> None:
    """End-to-end: run_gate itself must not print a pass with no manifest."""
    monkeypatch.setattr(gate_runner, "CHECKS", [(["true"], "noop")])
    assert not manifest.exists()
    assert gate_runner.run_gate() != 0


def test_run_gate_returns_nonzero_when_a_gate_fails(manifest, monkeypatch) -> None:
    """No regression: a valid manifest with a FAILING check is still non-zero."""
    manifest.write_text(json.dumps(VALID_MANIFEST))
    monkeypatch.setattr(gate_runner, "CHECKS", [(["false"], "always-fails")])
    assert gate_runner.run_gate() != 0


def test_run_gate_returns_zero_when_all_pass(manifest, monkeypatch, capsys) -> None:
    """Anti-over-block: a runner that always fails is as useless as one that
    always passes."""
    manifest.write_text(json.dumps(VALID_MANIFEST))
    monkeypatch.setattr(gate_runner, "CHECKS", [(["true"], "noop")])
    assert gate_runner.run_gate() == 0
    assert "all checks passed" in capsys.readouterr().out
