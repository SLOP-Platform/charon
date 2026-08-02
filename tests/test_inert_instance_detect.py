"""FAIL-ON-REVERT tests for instance-inert detection in
tools/check_inert_code.py.

Three required assertions (from INERT-INSTANCE-DETECT):
(1) A fixture class that is constructed + stored but NEVER invoked -> RED.
    Adding a real invocation -> GREEN. Reverting the detector change causes
    the fixture to stop failing — the test fails.
(2) A fixture that IS invoked after construction -> GREEN (no false positive).
(3) Every known-inert gateway module is present in
    inert-code-disposition.json with a wire|retire disposition and a non-empty
    rationale. EXTENDED 2026-07-19: each must carry a recorded operator answer.

2026-07-24 (INERT-INSTANCE-DETECT): five of the original six were RETIRED and
deleted (Observability, SpeculativeExecutor, SessionAffinity, ConsensusRouter,
VirtualKeyManager). Only RequestInspector survives — it has a real planned
consumer (RFL-3). The roster is therefore SMALLER, so the tests below no longer
lean on "the heuristic misses one of the six" as their proof that the roster is
load-bearing; that property is now proven directly against the MECHANISM, with a
probe class the heuristic cannot see (see TestGateBHoleClosed).
"""
from __future__ import annotations

from pathlib import Path

import tools.check_inert_code as M

EXPECTED_MODULES: frozenset[str] = frozenset({
    "charon.request_inspector.RequestInspector",
})

# A real, live class that the collision-tolerant heuristic does NOT flag and that
# carries no disposition. Used to prove the roster mechanism forces a disposition
# for symbols the heuristic can never surface — independent of which real modules
# happen to be on the roster today.
_HEURISTIC_BLIND_PROBE = "charon.policy_router.PolicyRouter"
_HEURISTIC_BLIND_PROBE_PATH = "src/charon/policy_router.py"


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
        passed, undisposed, dead, schema, roster_issues = M.check(repo_root=repo)
        assert not passed
        assert schema == []
        assert "widget.Widget" in dead
        assert "widget.Widget" in undisposed

    def test_live_absent_from_check_output(self, tmp_path: Path) -> None:
        repo = _build_fixture(tmp_path, with_invocation=True)
        passed, undisposed, dead, schema, roster_issues = M.check(repo_root=repo)
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
    """FAIL-ON-REVERT (3): every named gateway module is present in
    inert-code-disposition.json with an explicit wire|retire disposition
    and a non-empty rationale. EXTENDED 2026-07-19: each entry must carry
    a recorded operator answer (non-empty reason)."""

    _DISPOSITION_PATH: Path = M.DISPOSITION_PATH

    def test_all_tracked_modules_present(self) -> None:
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
        """The real repo, including every gateway module tracked in the
        disposition file, must still pass — all of them are disposed."""
        passed, undisposed, dead, schema_issues, roster_issues = M.check()
        assert schema_issues == []
        assert roster_issues == []
        assert undisposed == [], (
            f"new dead symbol(s) not tracked: {undisposed}"
        )
        assert passed is True


class TestGateBHoleClosed:
    """THE GATE-B RED-PROOF (INERT-INSTANCE-DETECT accept D2).

    Gate B of WORK-GATE-UNIVERSAL is built on this detector, so a detector that
    reports OK while an inert module carries no disposition CERTIFIES INERT CODE
    AS FULLY WIRED. Before the KNOWN_INSTANCE_INERT roster, that hole was real
    and measured: dropping SessionAffinity, ConsensusRouter or VirtualKeyManager
    from the disposition file left ``check_inert_code.py`` at rc=0, because the
    heuristic's collision-tolerant method matching cannot see those three.

    These tests delete each roster entry in turn (in memory — the real file is
    never written) and require the detector to go RED for every one.
    """

    def test_dropping_any_tracked_module_turns_the_gate_red(self, monkeypatch) -> None:
        real = M.load_dispositions()
        for mod in sorted(EXPECTED_MODULES):
            pruned = {k: v for k, v in real.items() if k != mod}
            monkeypatch.setattr(M, "load_dispositions", lambda p=pruned: dict(p))
            passed, undisposed, dead, schema_issues, roster_issues = M.check()
            assert mod in dead, (
                f"{mod} is instance-inert but the detector does not even report "
                "it — Gate B would certify it as wired"
            )
            assert mod in undisposed, f"{mod} undispositioned but not reported"
            assert passed is False, (
                f"detector still GREEN with {mod} undispositioned — this is the "
                "Gate-B hole, not a pass"
            )

    def test_roster_covers_exactly_the_tracked_modules(self) -> None:
        """NON-VACUOUS: a roster that has drifted empty would pass over nothing."""
        assert set(M.KNOWN_INSTANCE_INERT) == set(EXPECTED_MODULES)
        assert M.KNOWN_INSTANCE_INERT, (
            "the roster is EMPTY — the Gate-B backstop now checks nothing"
        )

    def test_roster_backstops_what_the_heuristic_misses(self, monkeypatch) -> None:
        """The roster must be load-bearing, not decorative.

        Proven against the MECHANISM rather than against whichever modules happen
        to be on the roster today: ``_HEURISTIC_BLIND_PROBE`` is a real class the
        collision-tolerant heuristic does NOT flag and that carries no
        disposition. Putting it on the roster must make the gate RED. If it does
        not, the roster is inert and the Gate-B hole is back open — regardless of
        how many rows the roster has.
        """
        heuristic = set(M.find_instance_inert_classes())
        assert _HEURISTIC_BLIND_PROBE not in heuristic, (
            f"{_HEURISTIC_BLIND_PROBE} is now heuristic-visible — pick a new "
            "blind probe, or this test proves nothing"
        )
        assert _HEURISTIC_BLIND_PROBE not in M.load_dispositions()

        probed = dict(M.KNOWN_INSTANCE_INERT)
        probed[_HEURISTIC_BLIND_PROBE] = _HEURISTIC_BLIND_PROBE_PATH
        monkeypatch.setattr(M, "KNOWN_INSTANCE_INERT", probed)
        passed, undisposed, dead, _schema, roster_issues = M.check()
        assert roster_issues == [], "the probe class must really exist"
        assert _HEURISTIC_BLIND_PROBE in dead, (
            "the roster did not surface a symbol the heuristic cannot see"
        )
        assert _HEURISTIC_BLIND_PROBE in undisposed
        assert passed is False, (
            "gate still GREEN with a rostered, undispositioned symbol — the "
            "Gate-B hole is open"
        )

    def test_a_new_inert_instance_still_reds_without_a_roster_row(
        self, tmp_path: Path
    ) -> None:
        """The other direction: a NEW instance-inert class nobody has rostered
        must still fail, on the heuristic alone. Shrinking the roster must not
        make new inert code shippable."""
        repo = _build_fixture(tmp_path, with_invocation=False)
        assert M.roster_for(repo) == {}, "fixture must not inherit this repo's roster"
        inert = M.find_instance_inert_classes(repo)
        assert any(sym.endswith(".Widget") for sym in inert), (
            "a constructed-but-never-invoked class went undetected with no "
            "roster row to catch it"
        )

    def test_stale_roster_row_is_a_failure(self, monkeypatch) -> None:
        """A roster row whose code no longer exists must RED, so a module cannot
        be deleted while leaving the gate silently checking nothing."""
        bogus = dict(M.KNOWN_INSTANCE_INERT)
        bogus["charon.gone.Vanished"] = "src/charon/gone.py"
        monkeypatch.setattr(M, "KNOWN_INSTANCE_INERT", bogus)
        issues = M.find_stale_roster_symbols()
        assert any("charon.gone.Vanished" in i for i in issues)
        passed, _u, _d, _s, roster_issues = M.check()
        assert passed is False
        assert roster_issues

    def test_roster_does_not_apply_to_foreign_trees(self, tmp_path: Path) -> None:
        """Scoping guard: the roster describes THIS repo, so a fixture tree must
        not inherit its rows (which would red every fixture test)."""
        assert M.roster_for(tmp_path) == {}
        assert set(M.roster_for(M.REPO_ROOT)) == set(EXPECTED_MODULES)
