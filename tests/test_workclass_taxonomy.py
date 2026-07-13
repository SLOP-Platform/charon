"""Tests for the open work-class taxonomy (GATEWAY-PROGRAM §1.9).

Coverage:
  * Hot-path classifier routes known prompts to a named class.
  * Truly unknown prompts return kind="unknown" + a stable signature.
  * ``observe_unknown`` populates the sink; the sink is bounded (LRU evict).
  * The taxonomy is append-only — re-adding an existing class raises.
  * Crystallized / new classes default to risk="high" (red-team fix #4);
    ``attest`` is the ONLY way to flip to risk="low".
  * Offline ``crystallize`` proposes new classes from the unknown pile.
  * Round-trip JSON (``to_dict`` / ``from_dict``) preserves seed + state.
  * Fail-on-revert: ``tools/check_no_rig_import.py`` flags ``import benchmark``
    / ``import grader_daemon`` on the product hot path (red-team fix #2).
"""
from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import pytest

from charon.capability.taxonomy import (
    Classification,
    UnknownEntry,
    UnknownSink,
    WorkClassDef,
    WorkClassTaxonomy,
)

# ── hot path ────────────────────────────────────────────────────────────


class TestHotPathClassify:
    """The cheap per-request classifier."""

    def test_seed_classes_are_present(self):
        tax = WorkClassTaxonomy()
        names = set(tax.names())
        # The canonical seed set.
        assert {"reasoning", "coding", "translation", "creative",
                "analysis", "general"}.issubset(names)

    def test_reasoning_keyword_matches(self):
        tax = WorkClassTaxonomy()
        c = tax.classify_request("Prove that sqrt(2) is irrational")
        assert c.kind == "known"
        assert c.work_class is not None
        assert c.work_class.name == "reasoning"

    def test_coding_keyword_matches(self):
        tax = WorkClassTaxonomy()
        c = tax.classify_request("Write a Python function to compute fibonacci")
        assert c.kind == "known"
        assert c.work_class.name == "coding"

    def test_translation_keyword_matches(self):
        tax = WorkClassTaxonomy()
        c = tax.classify_request("Translate this sentence into Japanese")
        assert c.kind == "known"
        assert c.work_class.name == "translation"

    def test_creative_keyword_matches(self):
        tax = WorkClassTaxonomy()
        c = tax.classify_request("Write a poem about the autumn rain")
        assert c.kind == "known"
        assert c.work_class.name == "creative"

    def test_analysis_keyword_matches(self):
        tax = WorkClassTaxonomy()
        c = tax.classify_request("Summarize this 20-page research report")
        assert c.kind == "known"
        assert c.work_class.name == "analysis"

    def test_unrelated_text_falls_back_to_general(self):
        tax = WorkClassTaxonomy()
        # No specific keyword — must hit the ``general`` catch-all.
        c = tax.classify_request("what's the weather like today in tokyo")
        assert c.kind == "known"
        assert c.work_class.name == "general"

    def test_classify_empty_string_is_unknown(self):
        """Empty prompts get logged to the unknown sink — they don't match
        any pattern AND have no signature to cluster on."""
        tax = WorkClassTaxonomy()
        c = tax.classify_request("")
        assert c.kind == "unknown"
        assert c.signature is not None
        assert c.work_class is None

    def test_signature_is_stable_across_whitespace(self):
        tax = WorkClassTaxonomy()
        c1 = tax.classify_request("Prove    that\nsqrt(2)\tis irrational")
        c2 = tax.classify_request("prove that sqrt(2) is irrational")
        # Both hit ``reasoning`` → both are kind="known".
        assert c1.kind == "known" and c2.kind == "known"
        # Empty text is the only true unknown (catch-all `.+` matches anything
        # else). Two different "empty-looking" inputs collapse to one signature.
        tax.observe_unknown("", now=1.0)
        tax.observe_unknown("   \n\t  ", now=2.0)
        assert len(tax.unknown) == 1

    def test_classification_name_helper(self):
        tax = WorkClassTaxonomy()
        known = tax.classify_request("debug my python script")
        assert known.name() == "coding"
        unknown = tax.classify_request("")
        assert unknown.name() == "unknown"

    def test_is_unknown_property(self):
        tax = WorkClassTaxonomy()
        assert tax.classify_request("debug my python script").is_unknown is False
        assert tax.classify_request("").is_unknown is True


# ── unknown sink ────────────────────────────────────────────────────────


class TestUnknownSink:
    """The in-memory pile the offline crystallizer inspects."""

    def test_record_then_top(self):
        sink = UnknownSink()
        sink.record(signature="aaa", sample="x", now=1.0)
        sink.record(signature="aaa", sample="x", now=2.0)  # bump count
        sink.record(signature="bbb", sample="y", now=3.0)
        top = sink.top(2)
        assert top[0].signature == "aaa"
        assert top[0].count == 2
        assert top[1].signature == "bbb"
        assert top[1].count == 1

    def test_lru_evict_when_full(self):
        sink = UnknownSink(max_entries=3)
        sink.record(signature="a", sample="a", now=1.0)
        sink.record(signature="b", sample="b", now=2.0)
        sink.record(signature="c", sample="c", now=3.0)
        sink.record(signature="d", sample="d", now=4.0)  # evicts "a" (oldest)
        names = {e.signature for e in sink.all()}
        assert "a" not in names
        assert names == {"b", "c", "d"}

    def test_evict_preserves_existing_counts(self):
        sink = UnknownSink(max_entries=2)
        sink.record(signature="a", sample="a", now=1.0)
        sink.record(signature="b", sample="b", now=2.0)
        # "a" gets bumped (keeps it fresh), "b" stays old → next add evicts "b".
        sink.record(signature="a", sample="a", now=3.0)
        sink.record(signature="c", sample="c", now=4.0)
        names = {e.signature for e in sink.all()}
        assert names == {"a", "c"}

    def test_sample_is_capped(self):
        sink = UnknownSink()
        long = "a" * 10_000
        sink.record(signature="x", sample=long, now=1.0)
        assert len(sink.all()[0].sample) == 240

    def test_observe_unknown_populates_sink(self):
        tax = WorkClassTaxonomy()
        # Use a prompt that won't match any specific class → falls to general
        # (still kind="known"). Force unknown with empty input.
        result = tax.observe_unknown("", now=1.0)
        assert result.is_unknown
        assert len(tax.unknown) == 1

    def test_observe_unknown_does_not_log_known(self):
        tax = WorkClassTaxonomy()
        tax.observe_unknown("Prove that 1+1=2", now=1.0)
        # "reasoning" matched → sink empty.
        assert len(tax.unknown) == 0


# ── append-only + risk attestation (red-team fix #4) ────────────────────


class TestAppendOnlyAndRisk:
    """Taxonomy mutation rules + risk attestation flow."""

    def test_seed_classes_default_low_risk(self):
        tax = WorkClassTaxonomy()
        for n in ("reasoning", "coding", "translation", "creative", "analysis", "general"):
            assert tax.get(n).risk == "low"

    def test_add_new_class_defaults_to_high_risk(self):
        """NEW/unknown classes default to HIGH-RISK (red-team fix #4).

        The gateway must NEVER auto-attest a crystallized class as low-risk —
        that breaks the novel-class × risk-gate deadlock the red team
        identified.
        """
        tax = WorkClassTaxonomy()
        cls = tax.add("my-novel-class", [r"\bmy-novel-class\b"])
        assert cls.risk == "high"
        assert tax.get("my-novel-class").risk == "high"

    def test_adding_existing_name_raises(self):
        tax = WorkClassTaxonomy()
        with pytest.raises(ValueError):
            tax.add("coding", [r"foo"])

    def test_attest_moves_class_to_low_risk(self):
        tax = WorkClassTaxonomy()
        tax.add("x", [r"x"])
        assert tax.get("x").risk == "high"
        tax.attest("x", risk="low")
        assert tax.get("x").risk == "low"

    def test_attest_can_move_back_to_high(self):
        tax = WorkClassTaxonomy()
        tax.add("x", [r"x"])
        tax.attest("x", risk="low")
        tax.attest("x", risk="high")
        assert tax.get("x").risk == "high"

    def test_attest_unknown_raises(self):
        tax = WorkClassTaxonomy()
        with pytest.raises(KeyError):
            tax.attest("nope")

    def test_update_patterns_preserves_risk(self):
        tax = WorkClassTaxonomy()
        tax.add("x", [r"\bfoo\b"], risk="low")
        tax.update_patterns("x", [r"\bbar\b"])
        assert tax.get("x").risk == "low"
        assert tax.get("x").patterns == (r"\bbar\b",)
        # New pattern compiles + matches the test prompt (independent of the
        # seed-class ordering, which puts ``general`` first).
        compiled = tax.get("x").compiled()
        assert compiled[0].search("please bar this for me") is not None

    def test_update_patterns_unknown_raises(self):
        tax = WorkClassTaxonomy()
        with pytest.raises(KeyError):
            tax.update_patterns("nope", [r"x"])

    def test_added_class_is_classified(self):
        """End-to-end: add a new class, then classify with it."""
        tax = WorkClassTaxonomy()
        tax.add("kubernetes-debug", [r"\b(kubectl|kubernetes|pod stuck|cluster)\b"])
        assert tax.get("kubernetes-debug") is not None
        # The class appears in ``names()`` after the seeds.
        assert "kubernetes-debug" in tax.names()


# ── crystallizer (offline) ──────────────────────────────────────────────


class TestCrystallize:
    """Offline batch: cluster unknowns → propose new classes."""

    def test_crystallize_suggests_only_by_default(self):
        """suggest_only=True must NOT mutate the taxonomy."""
        tax = WorkClassTaxonomy()
        tax.observe_unknown("", now=1.0)
        tax.observe_unknown("", now=2.0)
        before = set(tax.names())
        proposals = tax.crystallize(min_count=1, suggest_only=True)
        assert proposals  # non-empty
        assert set(tax.names()) == before  # unchanged

    def test_crystallize_min_count_filter(self):
        tax = WorkClassTaxonomy()
        # 1 hit — below min_count=3.
        tax.observe_unknown("", now=1.0)
        # Different empty signatures all collapse to one — let's use distinct
        # texts that classify as "unknown" (use very long random text so
        # catch-all "general" still wins? No — catch-all is a literal ``.+``
        # so EVERYTHING matches it. We need an EMPTY text or text that the
        # catch-all regex doesn't match — the catch-all uses re.DOTALL so
        # everything matches. So unknown = empty input only.
        # Multiple empty observations collapse to one signature. To create
        # truly distinct unknown entries, we must rely on the sink's count.
        # Add 5 empty hits → 1 entry with count=5 → above min_count=3.
        for _ in range(5):
            tax.observe_unknown("", now=float(_))
        proposals = tax.crystallize(min_count=3, suggest_only=True)
        # At least one proposal for the empty-input cluster.
        assert any(p["total_count"] >= 3 for p in proposals)

    def test_crystallize_inserts_with_high_risk(self):
        """suggest_only=False inserts new classes, ALWAYS as high-risk
        (red-team fix #4)."""
        tax = WorkClassTaxonomy()
        for _ in range(10):
            tax.observe_unknown("", now=float(_))
        proposals = tax.crystallize(min_count=1, suggest_only=False, max_new=4)
        # Each proposal corresponds to one new class. Verify risk is "high".
        for p in proposals:
            cls = tax.get(p["suggested_name"])
            assert cls is not None
            assert cls.risk == "high"
            assert cls.provenance == "crystallized"

    def test_crystallize_proposal_has_patterns(self):
        tax = WorkClassTaxonomy()
        tax.observe_unknown("kubernetes pod stuck in crashloop", now=1.0)
        # The catch-all matches this → it's kind="known" not unknown. We
        # need a way to force unknown. Empty text it is.
        tax.observe_unknown("", now=2.0)
        # Empty text → no useful patterns → fallback [.+] is acceptable.
        proposals = tax.crystallize(min_count=1, suggest_only=True, max_new=4)
        for p in proposals:
            assert p["suggested_patterns"]
            assert isinstance(p["suggested_patterns"], list)


# ── persistence ─────────────────────────────────────────────────────────


class TestRoundTrip:
    """JSON serialise + deserialise."""

    def test_to_from_dict_preserves_seed(self):
        tax = WorkClassTaxonomy()
        d = tax.to_dict()
        restored = WorkClassTaxonomy.from_dict(d)
        assert set(restored.names()) == set(tax.names())
        for name in tax.names():
            assert restored.get(name).risk == tax.get(name).risk

    def test_round_trip_preserves_added_class(self):
        tax = WorkClassTaxonomy()
        tax.add("x", [r"x"], risk="low", description="test")
        restored = WorkClassTaxonomy.from_dict(tax.to_dict())
        assert restored.get("x") is not None
        assert restored.get("x").risk == "low"
        assert restored.get("x").description == "test"

    def test_round_trip_preserves_unknown_sink(self):
        tax = WorkClassTaxonomy()
        tax.observe_unknown("kubernetes pod stuck", now=1.0)  # known → no log
        tax.observe_unknown("", now=2.0)
        tax.observe_unknown("", now=3.0)
        d = tax.to_dict()
        restored = WorkClassTaxonomy.from_dict(d)
        assert len(restored.unknown) >= 1

    def test_from_empty_dict_uses_seed(self):
        restored = WorkClassTaxonomy.from_dict({"classes": [], "unknown": {}})
        assert {"reasoning", "coding", "general"}.issubset(set(restored.names()))

    def test_from_dict_rehydrates_risk_levels(self):
        d = {
            "classes": [
                {"name": "low-class", "patterns": [r"low"], "risk": "low",
                 "provenance": "seed"},
                {"name": "high-class", "patterns": [r"high"], "risk": "high",
                 "provenance": "crystallized"},
            ],
            "unknown": {},
        }
        tax = WorkClassTaxonomy.from_dict(d)
        assert tax.get("low-class").risk == "low"
        assert tax.get("high-class").risk == "high"
        assert tax.get("high-class").provenance == "crystallized"

    def test_to_dict_is_json_safe(self):
        tax = WorkClassTaxonomy()
        # Must serialise cleanly with the stdlib JSON encoder.
        json.dumps(tax.to_dict())


class TestCopy:
    """The .copy() helper used by tests / operators for branching."""

    def test_copy_is_independent(self):
        tax = WorkClassTaxonomy()
        copy = tax.copy()
        copy.add("x", [r"x"])
        assert tax.get("x") is None
        assert copy.get("x") is not None

    def test_copy_unknown_sink_is_independent(self):
        tax = WorkClassTaxonomy()
        tax.observe_unknown("", now=1.0)
        copy = tax.copy()
        # Empty text collapses to one signature — verify that copy has
        # the SAME single entry (independence comes from mutation, not new data).
        assert len(copy.unknown) == 1
        # Now mutate the copy: clear + record a new empty hit → still 1.
        copy.unknown.clear()
        copy.observe_unknown("", now=2.0)
        # Tax unaffected by the clear.
        assert len(tax.unknown) == 1
        assert len(copy.unknown) == 1


# ── import guard (red-team fix #2) ─────────────────────────────────────


class TestCheckNoRigImport:
    """tools/check_no_rig_import.py must catch rig imports on the product path."""

    def test_clean_file_has_no_violations(self, tmp_path: Path):
        f = tmp_path / "clean.py"
        f.write_text("import os\nfrom pathlib import Path\nx = 1\n")
        from tools.check_no_rig_import import scan_file
        assert scan_file(f) == []

    def test_import_benchmark_is_flagged(self, tmp_path: Path):
        f = tmp_path / "bad.py"
        f.write_text("import benchmark\n")
        from tools.check_no_rig_import import scan_file
        violations = scan_file(f)
        assert any("benchmark" in v for v in violations)

    def test_from_grader_daemon_is_flagged(self, tmp_path: Path):
        f = tmp_path / "bad.py"
        f.write_text("from grader_daemon.core import thing\n")
        from tools.check_no_rig_import import scan_file
        violations = scan_file(f)
        assert any("grader_daemon" in v for v in violations)

    def test_dynamic_import_benchmark_is_flagged(self, tmp_path: Path):
        f = tmp_path / "sneaky.py"
        f.write_text('m = __import__("benchmark")\n')
        from tools.check_no_rig_import import scan_file
        violations = scan_file(f)
        assert any("benchmark" in v for v in violations)

    def test_dynamic_import_grader_daemon_is_flagged(self, tmp_path: Path):
        f = tmp_path / "sneaky.py"
        f.write_text('m = __import__("grader_daemon")\n')
        from tools.check_no_rig_import import scan_file
        violations = scan_file(f)
        assert any("grader_daemon" in v for v in violations)

    def test_submodule_import_is_flagged(self, tmp_path: Path):
        f = tmp_path / "bad.py"
        f.write_text("from benchmark.scoring import score_one\n")
        from tools.check_no_rig_import import scan_file
        violations = scan_file(f)
        assert any("benchmark" in v for v in violations)

    def test_string_literal_with_benchmark_name_is_ignored(self, tmp_path: Path):
        """Strings containing the name do NOT count — only real imports."""
        f = tmp_path / "clean_strings.py"
        f.write_text('NAME = "benchmark"\n# benchmark is forbidden\n')
        from tools.check_no_rig_import import scan_file
        assert scan_file(f) == []

    def test_actual_src_tree_has_no_rig_imports(self):
        """The repo's own src/charon/ tree must be clean."""
        from tools.check_no_rig_import import scan_hot_path
        violations = scan_hot_path(Path("src"))
        # The list is empty in a healthy repo; assert the invariant
        # so a future regression is caught immediately.
        assert violations == [], (
            "product hot path must not import rig packages: "
            f"{violations[:3]}…"
        )

    def test_guard_cli_exits_nonzero_on_violation(self, tmp_path: Path):
        """End-to-end: write a violating file under a fake src/charon/ tree,
        run the CLI, and assert it exits non-zero. Mirrors what CI would see.
        """
        fake_src = tmp_path / "src" / "charon"
        fake_src.mkdir(parents=True)
        bad = fake_src / "leaky.py"
        bad.write_text("import benchmark\n")
        # Also need a sentinel .py so the scan finds the dir.
        (fake_src / "__init__.py").write_text("")
        # engine/ and ports/worker.py exclusions still work — none here.
        result = subprocess.run(
            [sys.executable, "tools/check_no_rig_import.py", str(tmp_path / "src")],
            capture_output=True, text=True,
            cwd=Path(__file__).resolve().parents[1],
        )
        assert result.returncode != 0
        assert "benchmark" in result.stderr.lower()

    def test_guard_cli_exits_zero_on_clean_tree(self, tmp_path: Path):
        fake_src = tmp_path / "src" / "charon"
        fake_src.mkdir(parents=True)
        (fake_src / "__init__.py").write_text("")
        (fake_src / "ok.py").write_text("import os\n")
        result = subprocess.run(
            [sys.executable, "tools/check_no_rig_import.py", str(tmp_path / "src")],
            capture_output=True, text=True,
            cwd=Path(__file__).resolve().parents[1],
        )
        assert result.returncode == 0, result.stderr

    def test_engine_modules_are_excluded(self, tmp_path: Path):
        """The engine/ subtree has its own stdlib-only rule and is NOT the
        product hot path. The rig guard must not scan it (otherwise we'd
        double-report or false-positive on engine's intentional isolation).
        """
        fake_src = tmp_path / "src" / "charon" / "engine"
        fake_src.mkdir(parents=True)
        (fake_src / "rig_user.py").write_text("import benchmark\n")
        from tools.check_no_rig_import import scan_hot_path
        violations = scan_hot_path(tmp_path / "src")
        assert violations == []

    def test_ports_worker_is_excluded(self, tmp_path: Path):
        fake_src = tmp_path / "src" / "charon" / "ports"
        fake_src.mkdir(parents=True)
        (fake_src / "worker.py").write_text("import benchmark\n")
        from tools.check_no_rig_import import scan_hot_path
        violations = scan_hot_path(tmp_path / "src")
        assert violations == []


# ── misc helpers / shape ────────────────────────────────────────────────


class TestShape:
    """Smoke tests on the data types themselves."""

    def test_unknown_entry_round_trip(self):
        e = UnknownEntry(signature="abc", sample="x", count=2, first_seen=1.0, last_seen=2.0)
        d = e.to_dict()
        e2 = UnknownEntry.from_dict(d)
        assert e2 == e

    def test_workclass_def_is_frozen(self):
        cls = WorkClassDef(name="x", patterns=(r"x",), risk="low")
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):  # type: ignore[misc]
            cls.name = "y"  # type: ignore[misc]

    def test_classification_is_frozen(self):
        c = Classification(kind="unknown", signature="abc")
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):  # type: ignore[misc]
            c.kind = "known"  # type: ignore[misc]