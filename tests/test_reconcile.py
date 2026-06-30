"""WCI-MVP tests (ADR-0015): static reconciler + depth pre-sort."""
from __future__ import annotations

from pathlib import Path

from charon.engine.board import Board, Unit
from charon.engine.reconcile import (
    FindingKind,
    Severity,
    reconcile_static,
)


# -------------------------------------------------------------------- helpers
def _board(tmp_path: Path) -> Board:
    return Board.create(tmp_path / "board.json")


# ==================================================================== reconcile
class TestReconcileStatic:
    def test_empty_units(self) -> None:
        assert reconcile_static([]) == []

    def test_bad_dep(self) -> None:
        findings = reconcile_static([
            {"id": "a", "owns": ["src/a.py"], "depends_on": ["nope"]},
        ])
        assert len(findings) == 1
        f = findings[0]
        assert f.kind == FindingKind.BAD_DEP
        assert f.unit_id == "a"
        assert f.related_unit_id == "nope"
        assert f.severity == Severity.ERROR

    def test_bad_dep_multiple(self) -> None:
        findings = reconcile_static([
            {"id": "a", "owns": ["src/a.py"], "depends_on": ["missing-a", "missing-b"]},
            {"id": "b", "owns": ["src/b.py"], "depends_on": ["a"]},
        ])
        bads = [f for f in findings if f.kind == FindingKind.BAD_DEP]
        assert len(bads) == 2  # two missing refs on a
        assert all(f.unit_id == "a" for f in bads)

    def test_bad_dep_not_raised_for_existing_unit(self) -> None:
        findings = reconcile_static([
            {"id": "a", "owns": ["src/a.py"]},
            {"id": "b", "owns": ["src/b.py"], "depends_on": ["a"]},
        ])
        bads = [f for f in findings if f.kind == FindingKind.BAD_DEP]
        assert len(bads) == 0

    def test_duplicate_branch(self) -> None:
        findings = reconcile_static([
            {"id": "a", "branch": "feat/x", "owns": ["src/a.py"]},
            {"id": "b", "branch": "feat/x", "owns": ["src/b.py"]},
        ])
        dups = [f for f in findings if f.kind == FindingKind.DUPLICATE]
        assert len(dups) == 1
        assert dups[0].unit_id == "b"
        assert dups[0].related_unit_id == "a"
        assert "feat/x" in dups[0].detail

    def test_duplicate_branch_three_units(self) -> None:
        findings = reconcile_static([
            {"id": "a", "branch": "feat/x", "owns": ["src/a.py"]},
            {"id": "b", "branch": "feat/x", "owns": ["src/b.py"]},
            {"id": "c", "branch": "feat/x", "owns": ["src/c.py"]},
        ])
        dups = [f for f in findings if f.kind == FindingKind.DUPLICATE]
        assert len(dups) == 2  # b and c are duplicates of a
        assert {f.unit_id for f in dups} == {"b", "c"}

    def test_no_duplicate_for_unique_branches(self) -> None:
        findings = reconcile_static([
            {"id": "a", "branch": "feat/x", "owns": ["src/a.py"]},
            {"id": "b", "branch": "feat/y", "owns": ["src/b.py"]},
        ])
        dups = [f for f in findings if f.kind == FindingKind.DUPLICATE]
        assert len(dups) == 0

    def test_no_duplicate_for_empty_branch(self) -> None:
        findings = reconcile_static([
            {"id": "a", "branch": "", "owns": ["src/a.py"]},
            {"id": "b", "branch": "", "owns": ["src/b.py"]},
        ])
        dups = [f for f in findings if f.kind == FindingKind.DUPLICATE]
        assert len(dups) == 0

    def test_owns_overlap_concurrent_collision(self) -> None:
        findings = reconcile_static([
            {"id": "a", "owns": ["src/shared"], "state": "ready"},
            {"id": "b", "owns": ["src/shared"], "state": "ready"},
        ])
        overlaps = [f for f in findings if f.kind == FindingKind.OWNS_OVERLAP]
        assert len(overlaps) == 1
        assert overlaps[0].unit_id == "a"
        assert overlaps[0].related_unit_id == "b"

    def test_owns_overlap_nested_path_collision(self) -> None:
        findings = reconcile_static([
            {"id": "a", "owns": ["src/pkg"], "state": "ready"},
            {"id": "b", "owns": ["src/pkg/mod.py"], "state": "ready"},
        ])
        overlaps = [f for f in findings if f.kind == FindingKind.OWNS_OVERLAP]
        assert len(overlaps) == 1

    def test_owns_overlap_dep_sequenced_is_safe(self) -> None:
        findings = reconcile_static([
            {"id": "a", "owns": ["src/shared"], "state": "ready",
             "depends_on": []},
            {"id": "b", "owns": ["src/shared"], "state": "ready",
             "depends_on": ["a"]},
        ])
        overlaps = [f for f in findings if f.kind == FindingKind.OWNS_OVERLAP]
        assert len(overlaps) == 0  # b depends on a → sequenced, safe

    def test_owns_overlap_transitive_sequencing_is_safe(self) -> None:
        findings = reconcile_static([
            {"id": "a", "owns": ["src/shared"], "state": "ready"},
            {"id": "b", "owns": ["src/other"], "state": "ready",
             "depends_on": ["a"]},
            {"id": "c", "owns": ["src/shared"], "state": "ready",
             "depends_on": ["b"]},
        ])
        overlaps = [f for f in findings if f.kind == FindingKind.OWNS_OVERLAP]
        assert len(overlaps) == 0  # c transitively depends on a → sequenced

    def test_owns_overlap_done_unit_not_live(self) -> None:
        findings = reconcile_static([
            {"id": "a", "owns": ["src/shared"], "state": "done"},
            {"id": "b", "owns": ["src/shared"], "state": "ready"},
        ])
        overlaps = [f for f in findings if f.kind == FindingKind.OWNS_OVERLAP]
        assert len(overlaps) == 0  # a is done — no live collision

    def test_contradiction_disjoint_owns_dep(self) -> None:
        findings = reconcile_static([
            {"id": "a", "owns": ["src/a.py"], "state": "ready"},
            {"id": "b", "owns": ["src/b.py"], "state": "ready",
             "depends_on": ["a"]},
        ])
        contras = [f for f in findings if f.kind == FindingKind.CONTRADICTION]
        assert len(contras) == 1
        assert contras[0].unit_id == "b"
        assert contras[0].related_unit_id == "a"
        assert contras[0].severity == Severity.WARN

    def test_contradiction_not_raised_for_overlapping_owns(self) -> None:
        findings = reconcile_static([
            {"id": "a", "owns": ["src/shared"], "state": "ready"},
            {"id": "b", "owns": ["src/shared"], "state": "ready",
             "depends_on": ["a"]},
        ])
        contras = [f for f in findings if f.kind == FindingKind.CONTRADICTION]
        assert len(contras) == 0  # shared owns → plausible real dep

    def test_contradiction_done_dependent_not_checked(self) -> None:
        findings = reconcile_static([
            {"id": "a", "owns": ["src/a.py"], "state": "ready"},
            {"id": "b", "owns": ["src/b.py"], "state": "done",
             "depends_on": ["a"]},
        ])
        contras = [f for f in findings if f.kind == FindingKind.CONTRADICTION]
        assert len(contras) == 0  # b is done — no live dependent to check

    def test_redundancy_identical_owns(self) -> None:
        findings = reconcile_static([
            {"id": "a", "owns": ["src/x.py", "src/y.py"], "state": "ready"},
            {"id": "b", "owns": ["src/x.py", "src/y.py"], "state": "ready"},
        ])
        dups = [f for f in findings if f.kind == FindingKind.DUPLICATE
                and "identical owns" in f.detail]
        assert len(dups) == 1
        assert dups[0].unit_id == "a"
        assert dups[0].related_unit_id == "b"

    def test_redundancy_not_raised_for_distinct_owns(self) -> None:
        findings = reconcile_static([
            {"id": "a", "owns": ["src/x.py"], "state": "ready"},
            {"id": "b", "owns": ["src/y.py"], "state": "ready"},
        ])
        dups = [f for f in findings if f.kind == FindingKind.DUPLICATE
                and "identical owns" in f.detail]
        assert len(dups) == 0

    def test_redundancy_not_raised_for_empty_owns(self) -> None:
        findings = reconcile_static([
            {"id": "a", "owns": [], "state": "ready"},
            {"id": "b", "owns": [], "state": "ready"},
        ])
        dups = [f for f in findings if f.kind == FindingKind.DUPLICATE
                and "identical owns" in f.detail]
        assert len(dups) == 0

    def test_multiple_finding_kinds_on_same_units(self) -> None:
        findings = reconcile_static([
            {"id": "a", "branch": "feat/z", "owns": ["src/a.py"], "state": "ready",
             "depends_on": ["missing"]},
            {"id": "b", "branch": "feat/z", "owns": ["src/b.py"], "state": "ready",
             "depends_on": ["a"]},
        ])
        kinds = {f.kind for f in findings}
        assert FindingKind.BAD_DEP in kinds
        assert FindingKind.DUPLICATE in kinds
        assert FindingKind.CONTRADICTION in kinds

    def test_board_state_override(self) -> None:
        """board_state marks 'a' as done even though its unit state is 'ready'."""
        findings = reconcile_static(
            [
                {"id": "a", "owns": ["src/shared"], "state": "ready"},
                {"id": "b", "owns": ["src/shared"], "state": "ready"},
            ],
            board_state={"a": "done"},
        )
        overlaps = [f for f in findings if f.kind == FindingKind.OWNS_OVERLAP]
        assert len(overlaps) == 0  # a treated as done → no live collision

    def test_deterministic_output(self) -> None:
        units = [
            {"id": "a", "owns": ["src/a.py"], "branch": "feat/x", "state": "ready",
             "depends_on": ["missing"]},
            {"id": "b", "owns": ["src/a.py"], "branch": "feat/x", "state": "ready"},
            {"id": "c", "owns": ["src/c.py"], "state": "ready",
             "depends_on": ["a"]},
        ]
        first = reconcile_static(units)
        second = reconcile_static(units)
        assert first == second

    def test_accepts_board_unit_objects(self, tmp_path: Path) -> None:
        b = _board(tmp_path)
        b.add(Unit(id="a", owns=["src/a.py"]))
        b.add(Unit(id="b", owns=["src/a.py"]))
        findings = reconcile_static([b.get("a"), b.get("b")])
        overlaps = [f for f in findings if f.kind == FindingKind.OWNS_OVERLAP]
        assert len(overlaps) == 1

    def test_id_missing_skipped_silently(self) -> None:
        findings = reconcile_static([{"owns": ["src/x.py"]}])
        assert findings == []


# ========================================================== depth pre-sort (WCI-2)
class TestDepthPreSort:
    def test_depth_zero_for_no_deps(self, tmp_path: Path) -> None:
        b = _board(tmp_path)
        b.add(Unit(id="a", owns=["src/a.py"]))
        assert b._unit_depth("a") == 0

    def test_depth_one_for_single_dep(self, tmp_path: Path) -> None:
        b = _board(tmp_path)
        b.add(Unit(id="a", owns=["src/a.py"]))
        b.add(Unit(id="b", owns=["src/b.py"], depends_on=["a"]))
        assert b._unit_depth("a") == 0
        assert b._unit_depth("b") == 1

    def test_depth_max_of_chains(self, tmp_path: Path) -> None:
        b = _board(tmp_path)
        b.add(Unit(id="a", owns=["src/a.py"]))
        b.add(Unit(id="b", owns=["src/b.py"], depends_on=["a"]))
        b.add(Unit(id="c", owns=["src/c.py"], depends_on=["a"]))
        b.add(Unit(id="d", owns=["src/d.py"], depends_on=["b", "c"]))
        b.mark_done("a")
        b.mark_done("b")
        b.mark_done("c")
        # After marking deps done, d is claimable
        # Depth: a=0, b=1, c=1, d=2
        assert b._unit_depth("d") == 2

    def test_depth_with_missing_dep(self, tmp_path: Path) -> None:
        """_unit_depth is safe even if a dep isn't on the board."""
        b = _board(tmp_path)
        b.add(Unit(id="b", owns=["src/b.py"], depends_on=["a"]))
        assert b._unit_depth("b") == 1  # declared dep (even missing) gives depth

    def test_depth_cycle_terminates(self, tmp_path: Path) -> None:
        b = _board(tmp_path)
        b.add(Unit(id="a", owns=["src/a.py"], depends_on=["b"]))
        b.add(Unit(id="b", owns=["src/b.py"], depends_on=["a"]))
        assert b._unit_depth("a") >= 1  # terminates at path detection
        assert b._unit_depth("b") >= 1

    def test_claimable_units_depth_order(self, tmp_path: Path) -> None:
        b = _board(tmp_path)
        b.add(Unit(id="a", owns=["src/a.py"]))
        b.add(Unit(id="b", owns=["src/b.py"], depends_on=["a"]))
        b.add(Unit(id="c", owns=["src/c.py"], depends_on=["a"]))
        b.add(Unit(id="d", owns=["src/d.py"], depends_on=["b", "c"]))
        b.add(Unit(id="e", owns=["src/e.py"]))  # no deps, depth 0
        b.add(Unit(id="f", owns=["src/f.py"], depends_on=["d"]))  # depth 3, not ready yet

        # Initially only a and e are claimable
        claimable = b.claimable_units()
        assert {u.id for u in claimable} == {"a", "e"}
        # Both have depth 0, so id order breaks the tie → ["a", "e"]
        assert [u.id for u in claimable] == ["a", "e"]

        # Mark a done → b, c, e claimable
        b.mark_done("a")
        claimable = b.claimable_units()
        assert {u.id for u in claimable} == {"b", "c", "e"}
        # b and c have depth 1, e has depth 0 → b, c before e
        assert [u.id for u in claimable] == ["b", "c", "e"]

    def test_claimable_units_same_set_sorted_order(self, tmp_path: Path) -> None:
        """Depth pre-sort never changes the claimable *set* — only the order."""
        b = _board(tmp_path)
        b.add(Unit(id="z", owns=["src/z.py"]))
        b.add(Unit(id="a", owns=["src/a.py"]))
        b.add(Unit(id="b", owns=["src/b.py"], depends_on=["z"]))
        b.add(Unit(id="c", owns=["src/c.py"], depends_on=["z"]))

        # Before z done: only a, z claimable
        assert {u.id for u in b.claimable_units()} == {"a", "z"}

        # After z done: a, b, c claimable
        b.mark_done("z")
        claimable = b.claimable_units()
        assert {u.id for u in claimable} == {"a", "b", "c"}
        # b and c have depth 1, a has depth 0 → b, c before a
        assert claimable[0].id in ("b", "c")
        assert claimable[1].id in ("b", "c")
        assert claimable[2].id == "a"

    def test_depth_pre_sort_id_tiebreak(self, tmp_path: Path) -> None:
        """When depths are equal, id breaks the tie deterministically."""
        b = _board(tmp_path)
        b.add(Unit(id="z", owns=["src/z.py"]))
        b.add(Unit(id="y", owns=["src/y.py"]))  # depth 0
        b.add(Unit(id="x", owns=["src/x.py"]))  # depth 0

        # All claimable, all depth 0 → id order
        claimable = b.claimable_units()
        assert [u.id for u in claimable] == ["x", "y", "z"]

    def test_depth_pre_sort_deterministic(self, tmp_path: Path) -> None:
        """Same input always produces the same order."""
        b = _board(tmp_path)
        b.add(Unit(id="a", owns=["src/a.py"]))
        b.add(Unit(id="b", owns=["src/b.py"], depends_on=["a"]))
        b.add(Unit(id="c", owns=["src/c.py"], depends_on=["b"]))
        b.add(Unit(id="d", owns=["src/d.py"]))

        # Before any done: a and d are claimable
        first = [u.id for u in b.claimable_units()]
        second = [u.id for u in b.claimable_units()]
        assert first == second

        b.mark_done("a")
        first = [u.id for u in b.claimable_units()]
        second = [u.id for u in b.claimable_units()]
        assert first == second

    def test_claimable_predicate_unchanged_by_depth(self, tmp_path: Path) -> None:
        """Depth pre-sort does NOT change what is claimable — only the order."""
        b = _board(tmp_path)
        b.add(Unit(id="a", owns=["src/a.py"]))
        b.add(Unit(id="b", owns=["src/b.py"], depends_on=["a"]))
        b.add(Unit(id="c", owns=["src/shared"]))
        b.add(Unit(id="d", owns=["src/shared"]))

        assert b.claimable("a") is True
        assert b.claimable("b") is False  # a not done
        assert b.claimable("c") is True  # lower id
        assert b.claimable("d") is False  # collides with c
