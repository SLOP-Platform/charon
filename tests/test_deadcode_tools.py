"""Red-proof tests for tools/check_deadcode_tools.py (the vulture+deadcode gate).

Three classes of assertion, matching the D&C contract:

1. **RED for newly-introduced dead code** (clauses (a) and (b)): the gate
   must catch the dead-code classes NOTHING ELSE in our stack currently
   catches — the new unused method/function/attribute (matches ruff F401/F841
   in some cases but the message here carries a DC code + the budget ratchet
   still fires independently of any other gate), and vulture's UNIQUE
   ``unreachable code after try/return`` class which is the entire reason
   vulture is in scope. Plus a NEW-FINDING ABOVE BUDGET regression check
   (clause (c)).

2. **GREEN on a clean fixture**: a fixture that has only reachable symbols
   and no unreachable code must pass. Proves we did not write a gate that
   always fails.

3. **Dedupe**: vulture and deadcode report the same symbol at the same line;
   the gate collapses to a single entry. Without dedupe the budget would
   double-count the overlap.

Plus the "it RUNS in CI" clause (d): this test imports and exercises
``tools/check_deadcode_tools.py`` as a Python module against synthetic
fixtures; the actual ``tools/check_deadcode_tools.py`` invocation in CI is
the runner doing ``python3 tools/check_deadcode_tools.py`` — the greenpath
end-to-end contract is covered by the real gate run, not duplicated here
(to avoid coupling this test to the global 169-finding baseline that
already passes).

Stdlib + the two adopted detector packages; no other test dependencies.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "check_deadcode_tools_mod", REPO_ROOT / "tools" / "check_deadcode_tools.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _make_clean_pkg(repo: Path) -> Path:
    """A pkg where every public symbol is reachable from a __main__-style entrypoint."""
    src = repo / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    (src / "a.py").write_text("def used(): return 1\n")
    # `__main__` is the deadcode + vulture recognized entrypoint — it marks
    # the immediately-enclosing function/module as reachable regardless of
    # the static call graph.
    (src / "entry.py").write_text(
        "from pkg.a import used\n\n"
        "if __name__ == '__main__':\n    used()\n"
    )
    return repo / "src"


def _make_pkg_with_unused_function(repo: Path) -> Path:
    """A pkg with one reachable and one unused function — exercises the
    unused-function class (DC02 / vulture unused-function)."""
    src = repo / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    (src / "a.py").write_text(
        "def used():\n    return 1\n\n"
        "def never_called_xyz_unique():\n    return 2\n"
    )
    (src / "entry.py").write_text(
        "from pkg.a import used\n\n"
        "if __name__ == '__main__':\n    used()\n"
    )
    return repo / "src"


def _make_pkg_with_unreachable_after_try(repo: Path) -> Path:
    """A pkg whose function has a vulture-unique ``unreachable code after
    try/return`` finding. This is the class ruff F401/F841 and the KSF
    reachability detector both MISS — the one reason vulture is in scope."""
    src = repo / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    # try/finally where body returns, code after is unreachable.
    (src / "f.py").write_text(
        "def only_returns():\n"
        "    try:\n"
        "        return 1\n"
        "    finally:\n"
        "        pass\n"
        "    return 2\n"
    )
    (src / "entry.py").write_text(
        "from pkg.f import only_returns\n\n"
        "if __name__ == '__main__':\n    only_returns()\n"
    )
    return repo / "src"


# ─────────────── module behaviour ───────────────


class TestCleanFixture:
    def test_clean_pkg_yields_no_findings(self, tmp_path: Path) -> None:
        """GREEN path: a fixture with only reachable public symbols AND
        no unreachable code is reported as clean."""
        src = _make_clean_pkg(tmp_path)
        M = _load_module()
        findings = M.collect_findings(src_root=src)
        assert findings == [], (
            f"clean fixture produced {len(findings)} finding(s) "
            f"(DC02/D04/D05/etc. should not fire here): {findings}"
        )


class TestNewlyIntroducedUnusedFunctionFailsTheGate:
    """Clause (a): a newly-introduced unused function makes the check RED.

    Proves the gate catches the DC02 class, distinct from the inert-code
    reachability gate (which catches *reference-graph* isomorphisms but
    never reports a single unused function because both stay referenced by
    each other — see the substrate's note on mutually-referencing dead
    islands)."""

    def test_unused_function_shows_up_in_findings(self, tmp_path: Path) -> None:
        src = _make_pkg_with_unused_function(tmp_path)
        M = _load_module()
        findings = M.collect_findings(src_root=src)
        names = [f["name"] for f in findings]
        assert "never_called_xyz_unique" in names, (
            f"unused function was NOT reported (redproof fails): {findings}"
        )
        # The class tag list should include DC02 (deadcode's taxonomy).
        for f in findings:
            if f["name"] == "never_called_xyz_unique":
                assert any("DC02" in c for c in f["classes"]), (
                    f"DC02 class tag missing: {f}"
                )


class TestNewlyIntroducedUnreachableAfterTryFailsTheGate:
    """Clause (b): vulture's UNIQUE class — unreachable code after try/return —
    must make the gate RED. This is the entire reason vulture is adopted.
    Ruff F401/F841 and the KSF inert-code gate NEVER emit this."""

    def test_unreachable_after_try_shows_up_in_findings(self, tmp_path: Path) -> None:
        src = _make_pkg_with_unreachable_after_try(tmp_path)
        M = _load_module()
        findings = M.collect_findings(src_root=src)
        unreachable = [
            f for f in findings if "vulture:unreachable" in f["classes"]
        ]
        assert unreachable, (
            f"vulture-unreachable finding was NOT reported (this class is the "
            f"entire reason vulture is in scope): {findings}"
        )
        # The symbolic name carries the kind of statement it follows.
        for f in unreachable:
            assert f["name"].startswith("unreachable-after-"), f


# ─────────────── ratchet budget contract ───────────────


class TestRatchetBudget:
    """Clause (c): the budget is a SHRINKING-ONLY ratchet. A budget too
    small fails; a budget too large fails (BUDGET-OUT-OF-DATE); matching
    passes."""

    def test_observed_above_budget_is_red(self, tmp_path: Path) -> None:
        """Floor-too-low: gate must fail closed if observed > budget."""
        src = _make_pkg_with_unused_function(tmp_path)
        M = _load_module()
        findings = M.collect_findings(src_root=src)
        observed = len(findings)

        budget_file = tmp_path / "budget.json"
        budget_file.write_text(json.dumps({"findings_count": observed - 1}))

        state, obs, bud, _fs = M.check(src_root=src, budget_file=budget_file)
        assert state is False
        assert obs == observed
        assert bud == observed - 1

    def test_observed_below_budget_is_red(self, tmp_path: Path) -> None:
        """Ceiling-too-high: gate must fail closed if observed < budget."""
        src = _make_clean_pkg(tmp_path)
        M = _load_module()
        findings = M.collect_findings(src_root=src)
        observed = len(findings)
        assert observed == 0  # clean pkg sanity-check before ratchet test

        budget_file = tmp_path / "budget.json"
        budget_file.write_text(json.dumps({"findings_count": 1}))

        # Three-valued ratchet: equal → True, above → False, below → None.
        # Below is BUDGET-OUT-OF-DATE, equally red.
        state, obs, bud, _fs = M.check(src_root=src, budget_file=budget_file)
        assert state is None
        assert obs == 0
        assert bud == 1

    def test_observed_equal_budget_is_green(self, tmp_path: Path) -> None:
        """The only GREEN configuration: findings exactly match budget."""
        src = _make_clean_pkg(tmp_path)
        M = _load_module()
        findings = M.collect_findings(src_root=src)
        observed = len(findings)
        assert observed == 0

        budget_file = tmp_path / "budget.json"
        budget_file.write_text(json.dumps({"findings_count": 0}))

        state, obs, bud, _fs = M.check(src_root=src, budget_file=budget_file)
        assert state is True
        assert obs == 0
        assert bud == 0

    def test_missing_budget_file_is_red(self, tmp_path: Path) -> None:
        """The gate refuses to report a pass when no budget is recorded —
        the absence of a number is itself a finding the operator must set
        explicitly (we cannot infer a 'frozen' baseline from a brand new
        tree; that is the [[best-not-defensible]] fake-green the ratchet
        exists to prevent)."""
        M = _load_module()
        src = _make_clean_pkg(tmp_path)
        missing = tmp_path / "absent.json"
        raised = False
        try:
            M.check(src_root=src, budget_file=missing)
        except FileNotFoundError:
            # The exception IS the red signal: the gate refuses to compute
            # a verdict rather than silently producing one. ``main()`` would
            # catch this and exit 1; the contract under test is the refusal.
            raised = True
        assert raised, (
            f"missing budget file {missing} should have raised "
            f"FileNotFoundError rather than silently passing the gate"
        )

    def test_malformed_budget_is_red(self, tmp_path: Path) -> None:
        """The gate refuses negative / non-int budgets."""
        M = _load_module()
        src = _make_clean_pkg(tmp_path)
        budget_file = tmp_path / "budget.json"
        budget_file.write_text(json.dumps({"findings_count": -3}))
        raised = False
        try:
            M.check(src_root=src, budget_file=budget_file)
        except ValueError:
            raised = True
        assert raised, "malformed budget should have raised ValueError"


# ─────────────── dedupe rule ───────────────


class TestDedupe:
    """Overlap rule: vulture and deadcode frequently report the same
    symbol at the same line. They MUST collapse to a single entry; the
    ratchet counts findings, not raw emissions."""

    def test_per_path_line_name_collapse(self) -> None:
        """Unit-level: dedupe merges on (path, line, name)."""
        M = _load_module()
        a = M.Finding(path="x.py", line=10, name="foo", classes=["DC04"])
        b = M.Finding(path="x.py", line=10, name="foo", classes=["vulture:unused"])
        c = M.Finding(path="x.py", line=11, name="foo", classes=["DC04"])
        out = M._dedupe([a, b, c])
        assert len(out) == 2
        # The merged entry's class list keeps both tags.
        merged = next(f for f in out if f["line"] == 10)
        assert set(merged["classes"]) == {"DC04", "vulture:unused"}

    def test_real_repo_dedupes_when_both_tools_agree(self) -> None:
        """Smoke test against the real product tree: the post-dedupe count
        never exceeds the union of the raw tool emissions. This catches a
        regression where someone removes the dedupe path and the budget
        ratchet would silently diverge from the operator-visible count.
        """
        M = _load_module()
        src_root = REPO_ROOT / "src"
        vulture_only = M._scan_vulture(src_root)
        deadcode_only = M._scan_deadcode(src_root)
        deduped = M._dedupe(list(vulture_only) + list(deadcode_only))
        # The ratchet operates on deduped count; raw union must be >= deduped.
        raw_union = len({(f["path"], f["line"], f["name"])
                          for f in (vulture_only + deadcode_only)})
        assert len(deduped) <= raw_union
        # Deduped count itself must equal the same set of (path, line, name).
        assert len(deduped) == raw_union


# ─────────────── real-repo green path ───────────────


class TestRealRepoGateIsGreen:
    """Anti-over-block: the prod tree, with the recorded budget, must
    pass — and the budget file must exist and parse."""

    def test_real_repo_passes_current_budget(self) -> None:
        M = _load_module()
        exit_code = M.main()
        assert exit_code == 0, (
            "real-repo gate failed; the recorded baseline in "
            f"{M.BUDGET_FILE.name} must equal the current post-dedupe count. "
            "If you lowered the count on this branch, lower the budget in the "
            "same commit (BUDGET-OUT-OF-DATE contract)."
        )

    def test_real_repo_budget_is_loaded_and_int(self) -> None:
        M = _load_module()
        budget = M.load_budget()
        assert isinstance(budget, int) and budget >= 0


# ─────────────── wired-in CI proof ───────────────


class TestWiring:
    """The gate is a charter-class check: every ``ci_step:true`` gate must
    be wired into ``src/charon/gate_runner.py`` so the runner actually runs
    it. A configured-but-unrun scanner is the inert class this whole
    programme is about."""

    def test_gate_is_in_gate_runner(self) -> None:
        runner_src = (REPO_ROOT / "src" / "charon" / "gate_runner.py").read_text()
        assert "tools/check_deadcode_tools.py" in runner_src, (
            "DEADCODE-TOOLS-WIRE not wired into gate_runner.CHECKS — "
            "configured-but-unrun is the inert class this gate exists to prevent."
        )

    def test_gate_is_in_gates_json_with_min_work_units(self) -> None:
        gates = json.loads((REPO_ROOT / "tools" / "gates.json").read_text())
        gate_entry = next(
            (g for g in gates if g.get("id") == "deadcode-tools"),
            None,
        )
        assert gate_entry is not None, "deadcode-tools gate not registered in tools/gates.json"
        assert gate_entry.get("ci_step") is True
        assert gate_entry.get("red_proof") == "tests/test_deadcode_tools.py"
        assert isinstance(gate_entry.get("min_work_units"), int)
        assert gate_entry["min_work_units"] >= 1

    def test_gate_dependency_declared_in_dev_extra(self) -> None:
        py = (REPO_ROOT / "pyproject.toml").read_text()
        assert '"vulture' in py, "vulture is not declared in [project.optional-dependencies] dev"
        assert '"deadcode' in py, "deadcode is not declared in [project.optional-dependencies] dev"
