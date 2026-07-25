"""FAIL-ON-REVERT tests for instance-inert detection in
tools/check_inert_code.py.

Three required assertions (from INERT-INSTANCE-DETECT):
(1) A fixture class that is constructed + stored but NEVER invoked -> RED.
    Adding a real invocation -> GREEN. Reverting the detector change causes
    the fixture to stop failing — the test fails.
(2) A fixture that IS invoked after construction -> GREEN (no false positive).
(3) Every one of the 6 known-inert gateway modules is present in
    inert-code-disposition.json with a wire|retire disposition and a non-empty
    rationale. EXTENDED 2026-07-19: each must carry a recorded operator answer.
"""
from __future__ import annotations

from pathlib import Path

import tools.check_inert_code as M

EXPECTED_MODULES: frozenset[str] = frozenset({
    "charon.request_inspector.RequestInspector",
    "charon.session_affinity.SessionAffinity",
    "charon.observability.Observability",
    "charon.speculative_execution.SpeculativeExecutor",
    "charon.consensus.ConsensusRouter",
    "charon.virtual_keys.VirtualKeyManager",
})


def _build_fixture(tmp_path: Path, with_invocation: bool) -> Path:
    """Create a minimal repo with one class that is either inert or live."""
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)

    (src / "widget.py").write_text(
        "class Widget:\n"
        "    def __init__(self):\n"
        "        pass\n"
        "    def do_stuff(self):\n"
        "        return 42\n"
    )

    if with_invocation:
        (src / "entry.py").write_text(
            "from widget import Widget\n"
            "\n"
            "def main():\n"
            "    w = Widget()\n"
            "    result = w.do_stuff()\n"
            "    return result\n"
        )
    else:
        (src / "entry.py").write_text(
            "from widget import Widget\n"
            "\n"
            "def main():\n"
            "    w = Widget()\n"
        )

    (repo / "pyproject.toml").write_text(
        '[project]\nscripts = {run = "entry:main"}\n'
    )
    return repo


class TestInstanceInertCore:
    """FAIL-ON-REVERT (1): core assertion — the instance-inert pattern must
    produce RED, and adding an invocation must produce GREEN. Reverting the
    detector diff makes the fixture stop failing, which fails this test."""

    def test_constructed_but_never_invoked_is_inert(self, tmp_path: Path) -> None:
        repo = _build_fixture(tmp_path, with_invocation=False)
        instance_inert = M.find_instance_inert_classes(repo_root=repo)
        assert "widget.Widget" in instance_inert, (
            "Widget is constructed but never invoked — must be flagged inert"
        )

    def test_constructed_and_invoked_is_not_inert(self, tmp_path: Path) -> None:
        repo = _build_fixture(tmp_path, with_invocation=True)
        instance_inert = M.find_instance_inert_classes(repo_root=repo)
        assert "widget.Widget" not in instance_inert, (
            "Widget is constructed AND invoked — must NOT be flagged inert"
        )

    def test_inert_appears_in_check_output(self, tmp_path: Path) -> None:
        repo = _build_fixture(tmp_path, with_invocation=False)
        passed, undisposed, dead, schema = M.check(repo_root=repo)
        assert not passed
        assert schema == []
        assert "widget.Widget" in dead
        assert "widget.Widget" in undisposed

    def test_live_absent_from_check_output(self, tmp_path: Path) -> None:
        repo = _build_fixture(tmp_path, with_invocation=True)
        passed, undisposed, dead, schema = M.check(repo_root=repo)
        assert passed
        assert schema == []
        assert "widget.Widget" not in dead


class TestNoFalsePositive:
    """FAIL-ON-REVERT (2): a class that is genuinely invoked after
    construction must NOT be flagged — guards against detector crying wolf."""

    def test_class_with_method_invocation_not_inert(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        src = repo / "src"
        src.mkdir(parents=True)

        (src / "worker.py").write_text(
            "class Worker:\n"
            "    def process(self, data: str) -> str:\n"
            "        return data.upper()\n"
        )
        (src / "entry.py").write_text(
            "from worker import Worker\n"
            "\n"
            "def main():\n"
            "    w = Worker()\n"
            "    return w.process('hello')\n"
        )
        (repo / "pyproject.toml").write_text(
            '[project]\nscripts = {run = "entry:main"}\n'
        )

        instance_inert = M.find_instance_inert_classes(repo_root=repo)
        assert "worker.Worker" not in instance_inert

    def test_class_with_multiple_invocations_not_inert(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        src = repo / "src"
        src.mkdir(parents=True)

        (src / "service.py").write_text(
            "class Service:\n"
            "    def start(self) -> None:\n"
            "        pass\n"
            "    def stop(self) -> None:\n"
            "        pass\n"
            "    def status(self) -> str:\n"
            "        return 'ok'\n"
        )
        (src / "entry.py").write_text(
            "from service import Service\n"
            "\n"
            "def main():\n"
            "    svc = Service()\n"
            "    svc.start()\n"
            "    print(svc.status())\n"
            "    svc.stop()\n"
        )
        (repo / "pyproject.toml").write_text(
            '[project]\nscripts = {run = "entry:main"}\n'
        )

        instance_inert = M.find_instance_inert_classes(repo_root=repo)
        assert "service.Service" not in instance_inert


class TestDispositionHonest:
    """FAIL-ON-REVERT (3): every one of the 6 named gateway modules is present
    in inert-code-disposition.json with an explicit wire|retire disposition
    and a non-empty rationale. EXTENDED 2026-07-19: each entry must carry
    a recorded operator answer (non-empty reason)."""

    _DISPOSITION_PATH: Path = M.DISPOSITION_PATH

    def test_all_six_modules_present(self) -> None:
        dispositions = M.load_dispositions()
        for mod in sorted(EXPECTED_MODULES):
            assert mod in dispositions, (
                f"{mod} missing from {self._DISPOSITION_PATH.name}"
            )

    def test_each_has_valid_disposition(self) -> None:
        dispositions = M.load_dispositions()
        for mod in sorted(EXPECTED_MODULES):
            entry = dispositions[mod]
            disp = entry.get("disposition", "")
            assert disp in ("wire", "retire"), (
                f"{mod}: disposition must be wire|retire, got {disp!r}"
            )

    def test_each_has_non_empty_reason(self) -> None:
        dispositions = M.load_dispositions()
        for mod in sorted(EXPECTED_MODULES):
            entry = dispositions[mod]
            reason = entry.get("reason", "")
            assert isinstance(reason, str) and reason.strip(), (
                f"{mod}: missing/empty rationale (operator answer not recorded)"
            )

    def test_current_codebase_passes(self) -> None:
        """The real repo, including the 6 gateway modules now tracked in the
        disposition file, must still pass — all 6 are disposed."""
        passed, undisposed, dead, schema_issues = M.check()
        assert schema_issues == []
        assert undisposed == [], (
            f"new dead symbol(s) not tracked: {undisposed}"
        )
        assert passed is True
