"""Proven-red tests for tools/check_decisions.py.

Each "bad" test plants a specific defect and asserts --check exits non-zero.
The clean test asserts a well-formed register passes.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from tools.check_decisions import lint

# ── helpers ────────────────────────────────────────────────────────────────────


def _docs(
    tmp_path: Path,
    register: str,
    adrs: dict[str, str] | None = None,
) -> Path:
    """Create a minimal docs/ layout under tmp_path."""
    d = tmp_path / "docs"
    d.mkdir()
    (d / "REVIEW-LOG.md").write_text("# Review Log\n")
    (d / "DECISIONS.md").write_text(register)
    adr_dir = d / "adr"
    adr_dir.mkdir()
    for name, text in (adrs or {}).items():
        (adr_dir / name).write_text(text)
    return d


_ACCEPTED_ADR = textwrap.dedent("""\
    # ADR-0001 — Test
    Status: **Accepted** (2026-01-01).
    ## Decisions
    ### D1 — Something
""")

_PROPOSED_ADR = textwrap.dedent("""\
    # ADR-0002 — Test
    Status: **Proposed** (2026-01-01).
    ## Decisions
    ### D1 — Something
""")

_HDR = (
    "| ID | Decision | Owner | Status | Source |\n"
    "|----|----------|-------|--------|--------|\n"
)


def _row(id_: str, status: str, source: str) -> str:
    return f"| {id_} | a decision | OP | {status} | {source} |\n"


# ── clean baseline ─────────────────────────────────────────────────────────────


def test_clean_register_passes(tmp_path: Path) -> None:
    register = "# D\n" + _HDR + _row("D001", "Settled", "ADR-0001")
    docs = _docs(tmp_path, register, {"0001-test.md": _ACCEPTED_ADR})
    assert lint(docs) == []


# ── proven-red: bad Source ─────────────────────────────────────────────────────


def test_standalone_dtc_flagged(tmp_path: Path) -> None:
    """A bare 'DTC <date>' token with no ADR anchor must be flagged."""
    register = "# D\n" + _HDR + _row("D001", "Settled", "ADR-0001, DTC 2026-06-26")
    docs = _docs(tmp_path, register, {"0001-test.md": _ACCEPTED_ADR})
    issues = lint(docs)
    assert any("DTC" in i for i in issues), f"expected DTC issue; got {issues}"


def test_dtc_in_parens_is_not_flagged(tmp_path: Path) -> None:
    """A DTC note inside parentheses after an ADR ref is contextual — not an error."""
    register = "# D\n" + _HDR + _row("D001", "Settled", "ADR-0001 (DTC 2026-06-26)")
    docs = _docs(tmp_path, register, {"0001-test.md": _ACCEPTED_ADR})
    assert lint(docs) == []


def test_missing_adr_file_flagged(tmp_path: Path) -> None:
    register = "# D\n" + _HDR + _row("D001", "Settled", "ADR-0099")
    docs = _docs(tmp_path, register)
    issues = lint(docs)
    assert any("ADR-0099" in i for i in issues), f"expected missing-ADR issue; got {issues}"


# ── proven-red: non-monotonic IDs ─────────────────────────────────────────────


def test_out_of_order_id_flagged(tmp_path: Path) -> None:
    """D003 appearing before D002 must be flagged as out-of-order."""
    register = (
        "# D\n" + _HDR
        + _row("D001", "Settled", "ADR-0001")
        + _row("D003", "Settled", "ADR-0001")
        + _row("D002", "Settled", "ADR-0001")
    )
    docs = _docs(tmp_path, register, {"0001-test.md": _ACCEPTED_ADR})
    issues = lint(docs)
    assert any("out-of-order" in i or "gap" in i for i in issues), (
        f"expected order/gap issue; got {issues}"
    )


def test_id_gap_flagged(tmp_path: Path) -> None:
    """D001 → D003 with no D002 must be flagged as a gap."""
    register = (
        "# D\n" + _HDR
        + _row("D001", "Settled", "ADR-0001")
        + _row("D003", "Open", "ADR-0001")
    )
    docs = _docs(tmp_path, register, {"0001-test.md": _ACCEPTED_ADR})
    issues = lint(docs)
    assert any("gap" in i for i in issues), f"expected gap issue; got {issues}"


def test_duplicate_id_flagged(tmp_path: Path) -> None:
    register = (
        "# D\n" + _HDR
        + _row("D001", "Settled", "ADR-0001")
        + _row("D001", "Open", "ADR-0001")
    )
    docs = _docs(tmp_path, register, {"0001-test.md": _ACCEPTED_ADR})
    issues = lint(docs)
    assert any("duplicate" in i for i in issues), f"expected duplicate issue; got {issues}"


# ── proven-red: off-enum Status ───────────────────────────────────────────────


def test_off_enum_status_flagged(tmp_path: Path) -> None:
    """'Open (deferred)' is not in the allowed Status enum."""
    register = "# D\n" + _HDR + _row("D001", "Open (deferred)", "ADR-0001")
    docs = _docs(tmp_path, register, {"0001-test.md": _ACCEPTED_ADR})
    issues = lint(docs)
    assert any("invalid Status" in i for i in issues), f"expected Status issue; got {issues}"


def test_valid_superseded_status_passes(tmp_path: Path) -> None:
    register = "# D\n" + _HDR + _row("D001", "Superseded→D002", "ADR-0001")
    docs = _docs(tmp_path, register, {"0001-test.md": _ACCEPTED_ADR})
    # Superseded→D002 is valid; no status issue expected.
    issues = [i for i in lint(docs) if "invalid Status" in i]
    assert issues == []


# ── proven-red: register-ahead-of-ADR ─────────────────────────────────────────


def test_settled_with_proposed_adr_flagged(tmp_path: Path) -> None:
    """Settled register row citing a Proposed ADR must be flagged."""
    register = "# D\n" + _HDR + _row("D001", "Settled", "ADR-0002")
    docs = _docs(tmp_path, register, {"0002-test.md": _PROPOSED_ADR})
    issues = lint(docs)
    assert any("Proposed" in i for i in issues), f"expected Proposed-ADR issue; got {issues}"


def test_open_with_proposed_adr_passes(tmp_path: Path) -> None:
    """Open row citing a Proposed ADR is fine — only Settled rows are checked."""
    register = "# D\n" + _HDR + _row("D001", "Open", "ADR-0002")
    docs = _docs(tmp_path, register, {"0002-test.md": _PROPOSED_ADR})
    issues = [i for i in lint(docs) if "Proposed" in i]
    assert issues == []
