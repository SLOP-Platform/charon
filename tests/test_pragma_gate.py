"""RED-proof for the pragma-evasion hole closed in tools/diff_cover_gate.py.

THE HOLE (PR #266, 2026-08-09): a single diff added 42 ``# pragma: no cover``
lines to ``src/``. That flipped the ``gate`` (diff-coverage) required check from
RED to green while hiding a live money-path bug: ``cost`` was bound to $0.00 and
every request silently booked $0.00, disabling the spend limiter.

A gate that a PR can silence by annotating the code it is judging is not a gate.

FOUR RED-PROOF CASES:
1. RED — added unjustified pragma MUST fail with file+line diagnostic.
2. RED (prong b) — added money-path pragma MUST fail EVEN WHEN justified.
3. GREEN — added justified pragma on genuinely unreachable guard MUST pass.
4. GREEN — no pragmas MUST pass with explicit "no added pragmas" message.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO_ROOT = Path(__file__).resolve().parent.parent

_BASE_MODULE = '''"""Fixture product module."""


def add(a, b):
    return a + b
'''

# (1) RED: unjustified pragma — bare "# pragma: no cover" with no justification text
_UNJUSTIFIED = '''assert add(1, 1) == 2  # pragma: no cover
'''

# (2) RED: money-path pragma — justified but adjacent to record_spend
_MONEY_PATH = '''
def record_balance():
    balance = {"total": 0}
    balance["total"] += 1  # pragma: no cover  # balance tracker unreachable
    record_spend("test", 0.0, balance)
'''

# (3) GREEN: justified pragma on a genuinely unreachable guard
_JUSTIFIED = '''import math as _math  # pragma: no cover  # wired in next sprint
'''

# (4) GREEN: regular added function (no pragma at all)
_NO_PRAGMA = '''
def noop():
    return None
'''

_BASE_TEST = '''from fixturepkg.calc import add


def test_add():
    assert add(2, 3) == 5
'''

_NOOP_TEST = _BASE_TEST + '''

from fixturepkg.calc import noop


def test_noop():
    assert noop() is None
'''

_CONFTEST = '''import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent / "src"))
'''


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    assert proc.returncode == 0, f"git {args} failed in {root}: {proc.stderr}"
    return proc.stdout


def _build_fixture(root: Path) -> Path:
    (root / "src" / "fixturepkg").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "tools").mkdir()
    (root / "src" / "fixturepkg" / "__init__.py").write_text("")
    (root / "src" / "fixturepkg" / "calc.py").write_text(_BASE_MODULE)
    (root / "tests" / "test_calc.py").write_text(_BASE_TEST)
    (root / "conftest.py").write_text(_CONFTEST)
    (root / "pyproject.toml").write_text('[project]\nname = "fixturepkg"\nversion = "0"\n')
    for name in ("gate_contract.py", "diff_scope.py", "diff_cover_gate.py"):
        shutil.copy2(REPO_ROOT / "tools" / name, root / "tools" / name)
    _git(root, "init", "-q", "-b", "master")
    _git(root, "config", "user.email", "fixture@charon.invalid")
    _git(root, "config", "user.name", "fixture")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "fixture base")
    return root


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    return _build_fixture(tmp_path / "repo")


def _gate_env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTEST_CURRENT_TEST", None)
    return env


def _run_gate(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "tools/diff_cover_gate.py", *args],
        cwd=root, capture_output=True, text=True, env=_gate_env(),
    )


# ---------------------------------------------------------------------------
# RED case 1: unjustified pragma MUST fail fast (before coverage), naming
#             the file and line
# ---------------------------------------------------------------------------

def _detail(proc: subprocess.CompletedProcess[str]) -> str:
    return f"got {proc.returncode}:\nstdout: {proc.stdout}\nstderr: {proc.stderr}"


def test_unjustified_pragma_reds(fixture_repo: Path) -> None:
    module = fixture_repo / "src" / "fixturepkg" / "calc.py"
    module.write_text(_BASE_MODULE + _UNJUSTIFIED)

    red = _run_gate(fixture_repo, "HEAD")
    assert red.returncode == 1, _detail(red)
    assert "UNJUSTIFIED PRAGMA" in red.stderr
    assert "calc.py:" in red.stderr
    assert "pragma violation" in red.stderr


# ---------------------------------------------------------------------------
# RED case 2 (prong b): money-path pragma MUST fail even when justified
# ---------------------------------------------------------------------------

def test_money_path_pragma_reds(fixture_repo: Path) -> None:
    module = fixture_repo / "src" / "fixturepkg" / "calc.py"
    module.write_text(_BASE_MODULE + _MONEY_PATH)

    red = _run_gate(fixture_repo, "HEAD")
    assert red.returncode == 1, _detail(red)
    assert "MONEY-PATH PRAGMA REFUSED" in red.stderr
    assert "pragma violation" in red.stderr


# ---------------------------------------------------------------------------
# GREEN case 3: justified pragma on genuinely unreachable guard MUST pass
# ---------------------------------------------------------------------------

def test_justified_pragma_greens(fixture_repo: Path) -> None:
    module = fixture_repo / "src" / "fixturepkg" / "calc.py"
    module.write_text(_BASE_MODULE + _JUSTIFIED)

    green = _run_gate(fixture_repo, "HEAD")
    assert green.returncode == 0, _detail(green)
    assert "added '# pragma: no cover'" in green.stdout
    assert "all justified" in green.stdout


# ---------------------------------------------------------------------------
# GREEN case 4: no pragmas MUST pass with explicit message (never silent)
# ---------------------------------------------------------------------------

def test_no_pragmas_greens_with_explicit_message(fixture_repo: Path) -> None:
    module = fixture_repo / "src" / "fixturepkg" / "calc.py"
    module.write_text(_BASE_MODULE + _NO_PRAGMA)
    test_file = fixture_repo / "tests" / "test_calc.py"
    test_file.write_text(_NOOP_TEST)

    green = _run_gate(fixture_repo, "HEAD")
    assert green.returncode == 0, _detail(green)
    assert "no added '# pragma: no cover'" in green.stdout
