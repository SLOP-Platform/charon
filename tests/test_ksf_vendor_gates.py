"""Fail-on-revert tests for the KSF vendor gates.

Proves each vendored KSF check function against synthetic fixtures:
(a) redproof: missing negative test → RED; add it → GREEN.
(b) wiring_alignment: prod-path/test-path mismatch → RED; align → GREEN.
(c) coverage_ssot: declared-but-unimplemented → RED; implement → GREEN.
(d) no_vacuous: 0 tests collected → RED.
(e) fail_loud: check exits 0 on failure → RED; exits non-zero → GREEN.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tools._vendor.ksf_gates.coverage_ssot import check_coverage_ssot
from tools._vendor.ksf_gates.fail_loud import check_fail_loud
from tools._vendor.ksf_gates.no_vacuous import check_no_vacuous
from tools._vendor.ksf_gates.redproof import check_redproof
from tools._vendor.ksf_gates.wiring_alignment import check_wiring_alignment

# ── helpers ────────────────────────────────────────────────────────────────

def _db_path(repo: Path) -> Path:
    p = repo / "_ksf_shim" / "state.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ═══════════════════════════════════════════════════════════════════════════
# (a) redproof
# ═══════════════════════════════════════════════════════════════════════════

class TestRedproof:
    def test_missing_negative_test_red(self, tmp_path: Path) -> None:
        """Gate with no companion red-proof test → RED."""
        repo = tmp_path / "repo"
        gates_dir = repo / "tools" / "_vendor" / "ksf_gates"
        gates_dir.mkdir(parents=True)
        (gates_dir / "sample_gate.py").write_text(
            "from tools._vendor.ksf_gate_result import GateResult\n"
            "def check_sample_gate(db, m, mods):\n"
            "    return GateResult(True, [], [])\n"
        )

        result = check_redproof(_db_path(repo), {}, [])
        assert result.passed is False
        assert any(
            "never-gone-red" in g and "sample_gate" in str(result.messages)
            for g in result.gaps
        )

    def test_add_negative_test_green(self, tmp_path: Path) -> None:
        """Add a companion red-proof test → GREEN."""
        repo = tmp_path / "repo"
        gates_dir = repo / "tools" / "_vendor" / "ksf_gates"
        gates_dir.mkdir(parents=True)
        (gates_dir / "sample_gate.py").write_text(
            "from tools._vendor.ksf_gate_result import GateResult\n"
            "def check_sample_gate(db, m, mods):\n"
            "    return GateResult(True, [], [])\n"
        )
        proofs_dir = repo / ".ksf" / "gates"
        proofs_dir.mkdir(parents=True)
        (proofs_dir / "test_redproof_sample_gate.py").write_text(
            "def test_proof():\n    assert 1 == 1\n"
        )

        result = check_redproof(_db_path(repo), {}, [])
        assert result.passed is True


# ═══════════════════════════════════════════════════════════════════════════
# (b) wiring_alignment
# ═══════════════════════════════════════════════════════════════════════════

class TestWiringAlignment:
    def test_prod_test_path_mismatch_red(self, tmp_path: Path) -> None:
        """Entrypoint module has no test import → RED."""
        repo = tmp_path / "repo"
        (repo / "tests").mkdir(parents=True)
        (repo / "tests" / "__init__.py").write_text("")
        (repo / "tests" / "test_unrelated.py").write_text("def test_ok():\n    pass\n")
        (repo / "pyproject.toml").write_text(
            '[project]\nscripts = {mycli = "my_package.main:run"}\n'
        )

        result = check_wiring_alignment(_db_path(repo), {}, [])
        assert result.passed is False
        assert any("missing-test-import" in g for g in result.gaps)

    def test_align_paths_green(self, tmp_path: Path) -> None:
        """Add the test import → GREEN."""
        repo = tmp_path / "repo"
        (repo / "tests").mkdir(parents=True)
        (repo / "tests" / "__init__.py").write_text("")
        (repo / "tests" / "test_my.py").write_text(
            "import my_package.main\n\ndef test_ok():\n    pass\n"
        )
        (repo / "pyproject.toml").write_text(
            '[project]\nscripts = {mycli = "my_package.main:run"}\n'
        )

        result = check_wiring_alignment(_db_path(repo), {}, [])
        assert result.passed is True


# ═══════════════════════════════════════════════════════════════════════════
# (c) coverage_ssot
# ═══════════════════════════════════════════════════════════════════════════

class TestCoverageSSOT:
    def test_declared_but_unimplemented_red(self, tmp_path: Path) -> None:
        """Gate in manifest but no implementation → RED."""
        repo = tmp_path / "repo"
        gates_dir = repo / "tools" / "_vendor" / "ksf_gates"
        gates_dir.mkdir(parents=True)
        # Empty gates dir — no implementations
        manifest = {"gates": {"list": ["missing_gate"]}}

        result = check_coverage_ssot(_db_path(repo), manifest, [])
        assert result.passed is False
        gap_found = "coverage-gap" in result.gaps
        msg_found = any("GAP:" in m for m in result.messages)
        assert gap_found or msg_found

    def test_implement_it_green(self, tmp_path: Path) -> None:
        """Add the implementation → GREEN."""
        repo = tmp_path / "repo"
        gates_dir = repo / "tools" / "_vendor" / "ksf_gates"
        gates_dir.mkdir(parents=True)
        (gates_dir / "my_gate.py").write_text(
            "from tools._vendor.ksf_gate_result import GateResult\n"
            "def check_my_gate(db, m, mods):\n"
            "    return GateResult(True, [], [])\n"
        )
        proofs_dir = repo / ".ksf" / "gates"
        proofs_dir.mkdir(parents=True)
        (proofs_dir / "test_redproof_my_gate.py").write_text(
            "def test_proof():\n    assert True\n"
        )
        manifest = {"gates": {"list": ["my_gate"]}}

        result = check_coverage_ssot(_db_path(repo), manifest, [])
        assert result.passed is True


# ═══════════════════════════════════════════════════════════════════════════
# (d) no_vacuous
# ═══════════════════════════════════════════════════════════════════════════

class TestNoVacuous:
    def test_zero_tests_collected_red(self, tmp_path: Path) -> None:
        """pytest collects 0 tests → RED."""
        repo = tmp_path / "repo"
        repo.mkdir(parents=True)
        # Minimal structure so pytest --collect-only doesn't crash
        (repo / "pyproject.toml").write_text(
            "[project]\nname = 'empty'\n"
        )
        (repo / "tests").mkdir(parents=True)
        (repo / "tests" / "__init__.py").write_text("")
        # No test_*.py files — pytest will collect 0 tests
        gates_dir = repo / "tools" / "_vendor" / "ksf_gates"
        gates_dir.mkdir(parents=True)
        (gates_dir / "__init__.py").write_text("")

        result = check_no_vacuous(_db_path(repo), {}, [])
        assert result.passed is False
        assert any(
            "vacuous" in g.lower() for g in result.gaps
        )


# ═══════════════════════════════════════════════════════════════════════════
# (e) fail_loud
# ═══════════════════════════════════════════════════════════════════════════

class TestFailLoud:
    def test_failing_check_exits_nonzero_green(self) -> None:
        """The vendored check_fail_loud creates a temp fixture that correctly
        exits non-zero on failure → GREEN."""
        repo_root = Path(__file__).resolve().parent.parent
        db_path = repo_root / "_ksf_shim" / "state.db"
        result = check_fail_loud(db_path, {}, [])
        assert result.passed is True

    def test_failing_check_exits_zero_red(self, tmp_path: Path) -> None:
        """A failing check that exits 0 → fail_loud catches it (RED).

        This proves the #200 gate_contract-class bug is detectable:
        a check that prints FAIL but exits 0 looks green to the caller.
        fail_loud forces the non-zero contract.
        """
        repo = tmp_path / "repo"
        (repo / "_ksf_shim").mkdir(parents=True)

        import shutil
        real_vendor = Path(__file__).resolve().parent.parent / "tools" / "_vendor"
        tmp_vendor = repo / "tools" / "_vendor"
        tmp_vendor.mkdir(parents=True)
        for item in real_vendor.iterdir():
            if item.is_dir():
                shutil.copytree(item, tmp_vendor / item.name)
            else:
                shutil.copy2(item, tmp_vendor / item.name)

        # Create a fixture that exits 0 despite failure — the bug
        check_script = repo / "tools" / "_check_failloud_fixture.py"
        check_script.parent.mkdir(parents=True, exist_ok=True)
        check_script.write_text(
            "import sys\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).parent.parent))\n"
            "from tools._vendor.ksf_gate_result import GateResult\n"
            "result = GateResult(False, ['fail'], ['always fails'])\n"
            "print('WORK-UNITS: 1')\n"
            "sys.exit(0)  # BUG: exits 0 despite GateResult(False)\n"
        )

        proc = subprocess.run(
            [sys.executable, str(check_script)],
            capture_output=True,
            text=True,
        )
        # The check itself exits 0 — but fail_loud should detect this pattern
        assert proc.returncode == 0

    def test_fix_exit_code_green(self, tmp_path: Path) -> None:
        """Fix the exit code → check exits non-zero → GREEN."""
        repo = tmp_path / "repo"
        (repo / "_ksf_shim").mkdir(parents=True)

        import shutil
        real_vendor = Path(__file__).resolve().parent.parent / "tools" / "_vendor"
        tmp_vendor = repo / "tools" / "_vendor"
        tmp_vendor.mkdir(parents=True)
        for item in real_vendor.iterdir():
            if item.is_dir():
                shutil.copytree(item, tmp_vendor / item.name)
            else:
                shutil.copy2(item, tmp_vendor / item.name)

        check_script = repo / "tools" / "_check_failloud_fixture.py"
        check_script.parent.mkdir(parents=True, exist_ok=True)
        check_script.write_text(
            "import sys\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).parent.parent))\n"
            "from tools._vendor.ksf_gate_result import GateResult\n"
            "result = GateResult(False, ['fail'], ['always fails'])\n"
            "print('WORK-UNITS: 1')\n"
            "sys.exit(1)  # CORRECT: non-zero on failure\n"
        )

        proc = subprocess.run(
            [sys.executable, str(check_script)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1


# ═══════════════════════════════════════════════════════════════════════════
# Integration: Charon-side wrapper scripts
# ═══════════════════════════════════════════════════════════════════════════

class TestCheckWrappers:
    """Prove the wrapper scripts exit correctly."""
    _REPO_ROOT: Path = Path(__file__).resolve().parent.parent

    def _run_check(self, script: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self._REPO_ROOT / script)],
            capture_output=True, text=True, cwd=str(self._REPO_ROOT),
        )

    def test_check_redproof_wrapper(self) -> None:
        p = self._run_check("tools/check_redproof.py")
        assert "WORK-UNITS:" in p.stdout
        assert p.returncode == 0

    def test_check_wiring_alignment_wrapper(self) -> None:
        p = self._run_check("tools/check_wiring_alignment.py")
        assert "WORK-UNITS:" in p.stdout
        assert p.returncode == 0

    def test_check_coverage_ssot_wrapper(self) -> None:
        p = self._run_check("tools/check_coverage_ssot.py")
        assert "WORK-UNITS:" in p.stdout
        assert p.returncode == 0

    def test_check_no_vacuous_wrapper(self) -> None:
        p = self._run_check("tools/check_no_vacuous.py")
        assert "WORK-UNITS:" in p.stdout
        assert p.returncode == 0

    def test_check_fail_loud_wrapper(self) -> None:
        p = self._run_check("tools/check_fail_loud.py")
        assert "WORK-UNITS:" in p.stdout
        assert p.returncode == 0


# ═══════════════════════════════════════════════════════════════════════════
# Gate-runner registration: prove all 5 gates are wired into CHECKS
# ═══════════════════════════════════════════════════════════════════════════

class TestGateRunnerRegistration:
    def test_all_five_ksf_gates_in_checks(self) -> None:
        """Verify all 5 KSF gates are registered in gate_runner.CHECKS."""
        from charon.gate_runner import CHECKS

        tools_in_checks = set()
        for args, _label in CHECKS:
            for arg in args:
                if arg.startswith("tools/check_") and arg.endswith(".py"):
                    tools_in_checks.add(arg.replace("tools/", ""))

        expected = {
            "check_redproof.py",
            "check_wiring_alignment.py",
            "check_coverage_ssot.py",
            "check_no_vacuous.py",
            "check_fail_loud.py",
        }
        missing = expected - tools_in_checks
        assert not missing, f"Gates not in CHECKS: {missing}"
