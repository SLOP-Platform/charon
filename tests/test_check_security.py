"""Red-proof tests for tools/check_security.py.

Each test creates temp files with a specific anti-pattern and verifies the checker
flags it.  Clean tests assert the real codebase passes.
"""
from __future__ import annotations

from pathlib import Path

import tools.check_security as M


class TestCleanCodebase:
    def test_current_codebase_passes(self) -> None:
        violations: list[str] = []
        for py in sorted(Path("src").rglob("*.py")):
            violations.extend(M.scan_file(py))
        assert violations == []


class TestBareExcept:
    def test_bare_except_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            "def f():\n"
            "    try:\n"
            "        x = 1\n"
            "    except:\n"
            "        pass\n"
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 1
        assert "bare except" in violations[0]

    def test_broad_except_exception_without_raise_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            "def f():\n"
            "    try:\n"
            "        x = 1\n"
            "    except Exception:\n"
            "        pass\n"
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 1
        assert "except Exception" in violations[0]

    def test_except_exception_with_raise_not_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            "def f():\n"
            "    try:\n"
            "        x = 1\n"
            "    except Exception as exc:\n"
            "        raise\n"
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 0

    def test_except_exception_with_re_raise_wrapped_not_flagged(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "mod.py").write_text(
            "class MyError(Exception):\n"
            "    pass\n"
            "def f():\n"
            "    try:\n"
            "        x = 1\n"
            "    except Exception as exc:\n"
            "        raise MyError(str(exc)) from exc\n"
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 0

    def test_except_exception_in_finally_not_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            "def f():\n"
            "    fh = open('x')\n"
            "    try:\n"
            "        x = 1\n"
            "    finally:\n"
            "        try:\n"
            "            fh.close()\n"
            "        except Exception:\n"
            "            pass\n"
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 0

    def test_except_exception_with_noqa_not_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            "def f():\n"
            "    try:\n"
            "        x = 1\n"
            "    except Exception:  # noqa: BLE001\n"
            "        pass\n"
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 0


class TestSecretsTokens:
    def test_hardcoded_openai_key_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            'API_KEY = "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890"\n'
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 1
        assert "secret" in violations[0].lower()

    def test_hardcoded_anthropic_key_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            'API_KEY = "sk-ant-api123-abcdefghijklmnopqrstuvwxyz1234567890ABCDEF"\n'
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 1
        assert "secret" in violations[0].lower()

    def test_bearer_header_construction_not_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            'def build_header(key):\n'
            '    return "Bearer " + key\n'
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 0

    def test_short_string_not_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            'NAME = "Bearer"\n'
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 0


class TestHardcodedIPs:
    def test_non_loopback_ip_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            'HOST = "10.0.0.1"\n'
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 1
        assert "10.0.0.1" in violations[0]

    def test_loopback_ip_not_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            'HOST = "127.0.0.1"\n'
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 0

    def test_loopback_ip_127_0_0_0_not_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            'HOST = "127.0.0.0"\n'
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 0

    def test_unspecified_ip_not_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            'HOST = "0.0.0.0"\n'
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 0

    def test_localhost_not_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            'HOST = "localhost"\n'
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 0

    def test_public_ip_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            'HOST = "192.168.1.100"\n'
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 1
        assert "192.168.1.100" in violations[0]


class TestEvalExec:
    def test_eval_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            "x = eval('1+1')\n"
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 1
        assert "eval" in violations[0]

    def test_exec_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            "exec('x=1')\n"
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 1
        assert "exec" in violations[0]

    def test_eval_in_string_not_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            's = "use eval() to run code"\n'
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 0


class TestSubprocessShell:
    def test_subprocess_run_shell_true_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            "import subprocess\n"
            "subprocess.run('echo hi', shell=True)\n"
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 1
        assert "shell=True" in violations[0]

    def test_subprocess_run_shell_false_not_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            "import subprocess\n"
            "subprocess.run(['echo', 'hi'], shell=False)\n"
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 0

    def test_subprocess_shell_true_with_noqa_not_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            "import subprocess\n"
            "subprocess.run('echo hi', shell=True)  # noqa: S602\n"
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 0

    def test_subprocess_shell_true_in_shell_install_not_flagged(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "mod.py").write_text(
            "import subprocess\n"
            "def _shell_install(argv):\n"
            "    return subprocess.run(argv[0], shell=True).returncode\n"
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 0

    def test_subprocess_call_shell_true_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            "import subprocess\n"
            "subprocess.call('echo hi', shell=True)\n"
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 1
        assert "shell=True" in violations[0]

    def test_subprocess_popen_shell_true_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            "import subprocess\n"
            "subprocess.Popen('echo hi', shell=True)\n"
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 1
        assert "shell=True" in violations[0]

    def test_subprocess_other_shell_not_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            "import subprocess\n"
            "def myfunc(shell=True):\n"
            "    pass\n"
            "subprocess.run(['echo', 'hi'])\n"
        )
        violations = M.scan_file(tmp_path / "mod.py")
        assert len(violations) == 0
