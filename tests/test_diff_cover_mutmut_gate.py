"""Fail-on-revert tests for diff-cover and mutmut diff-scoped gates.

(a) A fixture diff with an unexercised new line → diff_cover_gate.py RED;
    add the covering test → GREEN; revert → RED again.
(b) A fixture diff with a surviving mutant → mutmut_diff_gate.py RED;
    strengthen the assertion → GREEN; revert → RED again.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS = REPO_ROOT / "tools"


def _run_gate(script: str, cwd: Path, base: str = "master") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOLS / script), base],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True)


def _init_repo(tmp: Path) -> None:
    _git(tmp, "init", "--initial-branch=master")
    _git(tmp, "config", "user.email", "test@test")
    _git(tmp, "config", "user.name", "Test")
    _git(tmp, "config", "commit.gpgSign", "false")


@pytest.fixture
def diff_cover_fixture(tmp_path: Path) -> Path:
    """Temp git repo with a module (add) and its test, on master."""
    repo = tmp_path / "repo"
    src_dir = repo / "src"
    tests_dir = repo / "tests"
    src_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)

    (repo / "pyproject.toml").write_text("[project]\nname = 'test'\nversion = '0.1'\n")
    _init_repo(repo)

    (src_dir / "__init__.py").write_text("")
    (src_dir / "mycalc.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n"
    )
    (tests_dir / "__init__.py").write_text("")
    (tests_dir / "test_mycalc.py").write_text(
        "import sys; sys.path.insert(0, 'src')\n"
        "from mycalc import add\n\n"
        "def test_add():\n    assert add(2, 3) == 5\n"
    )

    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial: add mycalc module")
    _git(repo, "branch", "feature")
    return repo


@pytest.fixture
def mutmut_fixture(tmp_path: Path) -> Path:
    """Temp git repo with multiply + strong test, on master."""
    repo = tmp_path / "repo"
    src_dir = repo / "src"
    tests_dir = repo / "tests"
    src_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)

    (repo / "pyproject.toml").write_text(
        "[project]\nname = 'test'\nversion = '0.1'\n\n"
        "[tool.mutmut]\nsource_paths = ['src']\n"
    )
    _init_repo(repo)

    (src_dir / "__init__.py").write_text("")
    (src_dir / "mycalc.py").write_text(
        "def multiply(a: int, b: int) -> int:\n    return a * b\n"
    )
    (tests_dir / "__init__.py").write_text("")
    (tests_dir / "test_mycalc.py").write_text(
        "import sys; sys.path.insert(0, 'src')\n"
        "from mycalc import multiply\n\n"
        "def test_multiply():\n    assert multiply(3, 4) == 12\n"
    )

    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial: add mycalc with strong test")
    _git(repo, "branch", "feature")
    return repo


class TestDiffCoverGate:

    def test_uncovered_new_line_is_red(self, diff_cover_fixture: Path) -> None:
        _git(diff_cover_fixture, "checkout", "feature")
        _git(diff_cover_fixture, "checkout", "-b", "test-branch")

        mycalc = diff_cover_fixture / "src" / "mycalc.py"
        mycalc.write_text(
            "def add(a: int, b: int) -> int:\n    return a + b\n\n"
            "def subtract(a: int, b: int) -> int:\n    return a - b\n"
        )
        _git(diff_cover_fixture, "add", "-A")
        _git(diff_cover_fixture, "commit", "-m", "add untested subtract function")

        result = _run_gate("diff_cover_gate.py", diff_cover_fixture, "master")
        assert result.returncode != 0, (
            f"diff-cover should RED with untested new lines\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_covered_new_line_is_green(self, diff_cover_fixture: Path) -> None:
        _git(diff_cover_fixture, "checkout", "feature")
        _git(diff_cover_fixture, "checkout", "-b", "test-branch")

        mycalc = diff_cover_fixture / "src" / "mycalc.py"
        mycalc.write_text(
            "def add(a: int, b: int) -> int:\n    return a + b\n\n"
            "def subtract(a: int, b: int) -> int:\n    return a - b\n"
        )
        test_file = diff_cover_fixture / "tests" / "test_mycalc.py"
        test_file.write_text(
            "import sys; sys.path.insert(0, 'src')\n"
            "from mycalc import add, subtract\n\n"
            "def test_add():\n    assert add(2, 3) == 5\n\n"
            "def test_subtract():\n    assert subtract(5, 3) == 2\n"
        )
        _git(diff_cover_fixture, "add", "-A")
        _git(diff_cover_fixture, "commit", "-m", "add subtract function with test")

        result = _run_gate("diff_cover_gate.py", diff_cover_fixture, "master")
        assert result.returncode == 0, (
            f"diff-cover should GREEN when all new lines are exercised\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_revert_brings_red_back(self, diff_cover_fixture: Path) -> None:
        _git(diff_cover_fixture, "checkout", "feature")
        _git(diff_cover_fixture, "checkout", "-b", "test-branch")

        mycalc = diff_cover_fixture / "src" / "mycalc.py"
        mycalc.write_text(
            "def add(a: int, b: int) -> int:\n    return a + b\n\n"
            "def subtract(a: int, b: int) -> int:\n    return a - b\n"
        )
        test_file = diff_cover_fixture / "tests" / "test_mycalc.py"
        test_file.write_text(
            "import sys; sys.path.insert(0, 'src')\n"
            "from mycalc import add, subtract\n\n"
            "def test_add():\n    assert add(2, 3) == 5\n\n"
            "def test_subtract():\n    assert subtract(5, 3) == 2\n"
        )
        _git(diff_cover_fixture, "add", "-A")
        _git(diff_cover_fixture, "commit", "-m", "add subtract with test")

        _run_gate("diff_cover_gate.py", diff_cover_fixture, "master")

        test_file.write_text(
            "import sys; sys.path.insert(0, 'src')\n"
            "from mycalc import add\n\n"
            "def test_add():\n    assert add(2, 3) == 5\n"
        )
        _git(diff_cover_fixture, "add", "-A")
        _git(diff_cover_fixture, "commit", "-m", "revert: remove subtract test")

        result = _run_gate("diff_cover_gate.py", diff_cover_fixture, "master")
        assert result.returncode != 0, (
            f"after reverting the covering test, diff-cover should RED again\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


class TestMutmutGate:

    def test_no_test_leaves_surviving_mutant(self, mutmut_fixture: Path) -> None:
        """New source file with no covering test -> surviving mutant -> RED."""
        _git(mutmut_fixture, "checkout", "feature")
        _git(mutmut_fixture, "checkout", "-b", "test-branch")

        src_dir = mutmut_fixture / "src"
        (src_dir / "newcalc.py").write_text(
            "def divide(a: int, b: int) -> int:\n    return a / b\n"
        )
        _git(mutmut_fixture, "add", "-A")
        _git(mutmut_fixture, "commit", "-m", "add divide without test")

        result = _run_gate("mutmut_diff_gate.py", mutmut_fixture, "master")
        assert result.returncode != 0, (
            f"mutmut should RED with untested new file\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_strong_test_kills_mutant(self, mutmut_fixture: Path) -> None:
        """New source file with strong test -> mutant killed -> GREEN."""
        _git(mutmut_fixture, "checkout", "feature")
        _git(mutmut_fixture, "checkout", "-b", "test-branch")

        src_dir = mutmut_fixture / "src"
        tests_dir = mutmut_fixture / "tests"
        (src_dir / "newcalc.py").write_text(
            "def divide(a: int, b: int) -> int:\n    return a / b\n"
        )
        (tests_dir / "test_newcalc.py").write_text(
            "import sys; sys.path.insert(0, 'src')\n"
            "from newcalc import divide\n\n"
            "def test_divide():\n    assert divide(10, 2) == 5\n"
        )
        _git(mutmut_fixture, "add", "-A")
        _git(mutmut_fixture, "commit", "-m", "add divide with strong test")

        result = _run_gate("mutmut_diff_gate.py", mutmut_fixture, "master")
        assert result.returncode == 0, (
            f"mutmut should GREEN with properly tested code\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_revert_brings_red_back(self, mutmut_fixture: Path) -> None:
        _git(mutmut_fixture, "checkout", "feature")
        _git(mutmut_fixture, "checkout", "-b", "test-branch")

        src_dir = mutmut_fixture / "src"
        tests_dir = mutmut_fixture / "tests"
        (src_dir / "newcalc.py").write_text(
            "def divide(a: int, b: int) -> int:\n    return a / b\n"
        )
        (tests_dir / "test_newcalc.py").write_text(
            "import sys; sys.path.insert(0, 'src')\n"
            "from newcalc import divide\n\n"
            "def test_divide():\n    assert divide(10, 2) == 5\n"
        )
        _git(mutmut_fixture, "add", "-A")
        _git(mutmut_fixture, "commit", "-m", "add divide with strong test")
        _run_gate("mutmut_diff_gate.py", mutmut_fixture, "master")

        (tests_dir / "test_newcalc.py").write_text(
            "import sys; sys.path.insert(0, 'src')\n"
            "from newcalc import divide\n\n"
            "def test_divide():\n"
            "    result = divide(10, 2)\n"
            "    assert result is not None\n"
        )
        _git(mutmut_fixture, "add", "-A")
        _git(mutmut_fixture, "commit", "-m", "revert: weaken assertion")

        result = _run_gate("mutmut_diff_gate.py", mutmut_fixture, "master")
        assert result.returncode != 0, (
            f"after weakening assertion, mutmut should RED again\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
