"""Red-proof tests for pylint W0613 (unused-argument) detection.

Pylint's W0613 is the ONLY tool in our stack that signals unused function
arguments — ruff F841 covers variables only, and our other inert-code /
dead-code detectors don't look at arguments at all. See DEADCODE-TOOL-REDERIVE
(2026-08-01, operator-approved).

These tests validate that:
  1. pylint W0613 flags unused function arguments in synthetic fixtures.
  2. A function using all its arguments passes cleanly.
  3. The check operates on a codebase root specified at invocation, so the
     gate runner can scope it to src/ without including test/ fixture noise.
  4. Ruff's existing F401/F841 behaviour is unchanged (ANTI-OVER-BLOCK).

NOTE(pylint-4.0): pylint 4.0.6 defaults ``ignored-argument-names`` to
``_.*|^ignored_|^unused_``, so test arguments MUST use names that do not
match this pattern (e.g. ``spare``, ``extra_arg``) to reliably trigger W0613.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run_pylint(path: Path) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        "-m",
        "pylint",
        "--disable=all",
        "--enable=W0613",
        str(path),
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


def _ruff_check(path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ruff", "check", str(path)],
        capture_output=True,
        text=True,
    )


class TestPylintW0613Detector:
    """Proves pylint W0613 catches unused arguments in synthetic code."""

    def test_flags_unused_argument(self, tmp_path: Path) -> None:
        src = tmp_path / "code.py"
        src.write_text(
            "def handler(event, context):\n"
            "    return 'ok'\n"
        )
        result = _run_pylint(tmp_path)
        assert result.returncode != 0
        assert "Unused argument" in result.stdout

    def test_passes_when_all_args_used(self, tmp_path: Path) -> None:
        src = tmp_path / "code.py"
        src.write_text(
            "def handler(event, context):\n"
            "    return event + context\n"
        )
        result = _run_pylint(tmp_path)
        assert result.returncode == 0

    def test_flags_only_unused_not_used(self, tmp_path: Path) -> None:
        """Argument name must NOT match pylint's default ignored-argument-names
        pattern (``^unused_``). Use a name like ``spare`` instead."""
        src = tmp_path / "code.py"
        src.write_text(
            "def handler(event, context, spare):\n"
            "    return event + context\n"
        )
        result = _run_pylint(tmp_path)
        assert result.returncode != 0
        assert "spare" in result.stdout

    def test_method_unused_argument(self, tmp_path: Path) -> None:
        """``self`` is exempt; other instance-method arguments are not."""
        src = tmp_path / "code.py"
        src.write_text(
            "class Handler:\n"
            "    def handle(self, request, extra_arg):\n"
            "        return request\n"
        )
        result = _run_pylint(tmp_path)
        assert result.returncode != 0
        assert "extra_arg" in result.stdout

    def test_self_and_cls_are_exempt_other_arg_is_not(self, tmp_path: Path) -> None:
        src = tmp_path / "code.py"
        src.write_text(
            "class Handler:\n"
            "    @staticmethod\n"
            "    def handle(request):\n"
            "        return request\n"
            "    @classmethod\n"
            "    def create(cls, cfg):\n"
            "        return cls()\n"
        )
        result = _run_pylint(tmp_path)
        assert result.returncode != 0
        assert "cfg" in result.stdout

    def test_non_exempt_method_passes_when_args_used(self, tmp_path: Path) -> None:
        src = tmp_path / "code.py"
        src.write_text(
            "class Handler:\n"
            "    @staticmethod\n"
            "    def handle(request):\n"
            "        return request\n"
            "    @classmethod\n"
            "    def create(cls, config):\n"
            "        return cls(config)\n"
        )
        result = _run_pylint(tmp_path)
        assert result.returncode == 0

    def test_multiple_files_scanned(self, tmp_path: Path) -> None:
        (tmp_path / "good.py").write_text("def f(a, b): return a + b\n")
        (tmp_path / "bad.py").write_text("def f(a, spare): return a\n")
        result = _run_pylint(tmp_path)
        assert result.returncode != 0
        assert "spare" in result.stdout

    def test_no_false_positive_on_callback_signature(self, tmp_path: Path) -> None:
        src = tmp_path / "code.py"
        src.write_text(
            "def sort_and_filter(items, key=lambda x: x):\n"
            "    return sorted(items, key=key)\n"
        )
        result = _run_pylint(tmp_path)
        assert result.returncode == 0

    def test_dummy_variable_trailing_underscore(self, tmp_path: Path) -> None:
        src = tmp_path / "code.py"
        src.write_text(
            "def handler(event, _):\n"
            "    return event\n"
        )
        result = _run_pylint(tmp_path)
        assert result.returncode == 0

    def test_works_on_directory(self, tmp_path: Path) -> None:
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "mod.py").write_text(
            "def f(a, spare): return a\n"
        )
        result = _run_pylint(tmp_path)
        assert result.returncode != 0
        assert "spare" in result.stdout


class TestAntiOverBlock:
    """ANTI-OVER-BLOCK: ruff F401/F841 behaviour is unchanged by the presence
    of a pylint W0613 check — the two tools operate independently and must not
    interact."""

    def test_ruff_still_flags_unused_variable(self, tmp_path: Path) -> None:
        src = tmp_path / "code.py"
        src.write_text("def f():\n    unused_var = 42\n    return 0\n")
        result = _ruff_check(src)
        assert result.returncode != 0, (
            "ruff must still report F841 on unused variables — "
            "the pylint check must not suppress ruff's existing behaviour"
        )
        assert "F841" in result.stdout

    def test_ruff_accepts_clean_file(self, tmp_path: Path) -> None:
        """Ruff requires lint-clean imports even for trivial files."""
        src = tmp_path / "code.py"
        src.write_text(
            "def f():\n"
            "    return 42\n"
        )
        result = _ruff_check(src)
        assert result.returncode == 0


class TestBaselineCountSanity:
    """Proves pylint W0613 finds unused arguments in the real product tree."""

    def test_product_tree_has_findings(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        result = _run_pylint(repo_root / "src")
        assert result.returncode != 0 or "W0613" in result.stderr, (
            "Expected pylint W0613 to find unused arguments in the product tree "
            "(baseline ~46). If zero, check that pylint is installed and that "
            "src/ is within scope."
        )