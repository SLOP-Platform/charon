"""WIRING tests: check_catalog_case_quant registered + functional in the gate.

Tests that the detector is wired into the gate infrastructure (gates.json,
gate_runner.py CHECKS) and correctly produces RED on catalog mismatches and
GREEN on a clean catalog.  No new detector logic — this is wiring only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from charon.model_catalog import CatalogEntry, catalog

# The detector lives under tools/ (a gate enforcer, not an importable package).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from check_catalog_case_quant import find_mismatches  # noqa: E402
from check_catalog_case_quant import main as run_tool_main

# ── RED: seeded mismatch → tool exits 1 ──────────────────────────────────────


def test_gate_red_on_seeded_non_canonical_id() -> None:
    """Monkey-patch a catalog entry with an upper-case id → gate RED (exit 1)."""
    bad = CatalogEntry(
        id="Kimi-K2.8-Code", tier_hint="med",
        access="test", note="seeded mismatch",
    )
    with patch("charon.model_catalog.catalog", return_value=[bad]):
        assert run_tool_main([]) == 1


def test_gate_red_on_seeded_quant_suffix() -> None:
    """Monkey-patch a catalog entry with a quant suffix → gate RED (exit 1)."""
    bad = CatalogEntry(
        id="glm-5.2-fp8", tier_hint="med",
        access="test", note="seeded mismatch",
    )
    with patch("charon.model_catalog.catalog", return_value=[bad]):
        assert run_tool_main([]) == 1


def test_gate_red_on_seeded_collision() -> None:
    """Two entries normalizing to the same id → gate RED (exit 1)."""
    entries = [
        CatalogEntry(id="glm-5.2", tier_hint="med", access="test", note="a"),
        CatalogEntry(id="GLM-5.2-FP8", tier_hint="med", access="test", note="b"),
    ]
    with patch("charon.model_catalog.catalog", return_value=entries):
        assert run_tool_main([]) == 1


def test_find_mismatches_red_on_non_canonical() -> None:
    """Seeded strings with case/quant defects → problems list non-empty."""
    problems = find_mismatches(["kimi-k2.7-code", "Kimi-K2.8-Code", "glm-5.2-fp8"])
    assert len(problems) >= 1
    assert any("Kimi-K2.8-Code" in m for m in problems)


def test_find_mismatches_red_on_collision() -> None:
    """Two ids folding to the same canonical form → collision flagged."""
    problems = find_mismatches(["glm-5.2", "GLM-5.2-FP8"])
    assert any("collision" in m for m in problems)


# ── GREEN: clean catalog → tool exits 0 ──────────────────────────────────────


def test_gate_green_on_clean_catalog_via_find_mismatches() -> None:
    """The live curated catalog has only canonical ids → find_mismatches = []."""
    problems = find_mismatches(e.id for e in catalog())
    assert problems == []


def test_gate_green_on_clean_catalog_via_main() -> None:
    """Running main() against the real live catalog → GREEN (exit 0)."""
    assert run_tool_main([]) == 0


def test_find_mismatches_green_on_clean_canonical_ids() -> None:
    """Canonical-only ids → empty problems list."""
    assert find_mismatches(["glm-5.2", "kimi-k2.7-code", "claude-opus-4-8"]) == []


# ── FAIL-ON-REVERT: previously-green seeded data goes RED after revert ───────


def test_fail_on_revert_seeded_clean_then_non_canonical() -> None:
    """If a caller reverts the wiring to skip the detector, a seeded mismatch
    that was caught would silently pass.  This test asserts the DETECTOR itself
    still catches it, so any revert causes the gate-wiring test to fail."""
    clean = find_mismatches(["claude-opus-4-8", "deepseek-v4-flash"])
    assert clean == []
    dirty = find_mismatches(["Claude-Opus-4-8", "deepseek-v4-flash"])
    assert len(dirty) >= 1


# ── Gate-registry presence check (meta: the gate knows about this gate) ──────


def test_gate_registered_in_gates_json() -> None:
    """The gate entry exists in tools/gates.json."""
    import json
    gates = json.loads(
        Path(__file__).resolve().parents[1].joinpath("tools", "gates.json").read_text()
    )
    ids = [g["id"] for g in gates]
    assert "catalog-case-quant" in ids, (
        f"catalog-case-quant not in gates.json ids: {ids}"
    )


def test_gate_registered_in_gate_runner_checks() -> None:
    """The check appears in gate_runner.py CHECKS."""
    src = Path(__file__).resolve().parents[1].joinpath(
        "src", "charon", "gate_runner.py"
    ).read_text()
    assert "check_catalog_case_quant" in src, (
        "check_catalog_case_quant.py not referenced in gate_runner.py CHECKS"
    )
