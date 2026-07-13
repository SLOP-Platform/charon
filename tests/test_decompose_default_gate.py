"""DECOMPOSE-DEFAULT-GATE — the capstone that makes auto-decomposition the DEFAULT
way work is created for Charon Gateway.

These tests exercise the gate on the REAL intake path (``intake`` / ``intake_file`` →
``analyze`` — the same code production uses; there is no side function), pointing the
DEC-AST-WRAP change-surface engine at a small fixture repo (the pattern from
``test_decompose_surface``).

FAIL-ON-REVERT contract (see ``test_gate_is_load_bearing``): a broad fixture ticket
that crosses two modules is REJECTED at intake unless it is decomposed or explicitly
bypassed; a genuinely single-domain ticket passes untouched; the bypass flag admits
with the reason recorded. Delete/disable the gate → the broad ticket is admitted
un-decomposed → these tests go RED.
"""
from __future__ import annotations

import pathlib

import pytest

from charon import intake as I

ALPHA = "src/charon/alpha.py"
BETA = "src/charon/beta.py"
TEST_ALPHA = "tests/test_alpha.py"


def _write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _fixture(tmp_path: pathlib.Path) -> tuple[str, str]:
    """Two independent standalone modules (each with its own mapped test, required by
    the engine's signal-4). Returns (repo_root, empty_config_dir)."""
    _write(tmp_path / ALPHA, "ALPHA = 1\n\n\ndef fa():\n    return ALPHA\n")
    _write(tmp_path / BETA, "BETA = 2\n\n\ndef fb():\n    return BETA\n")
    _write(
        tmp_path / TEST_ALPHA,
        "from charon.alpha import fa\n\n\ndef test_a():\n    assert fa() == 1\n",
    )
    _write(
        tmp_path / "tests/test_beta.py",
        "from charon.beta import fb\n\n\ndef test_b():\n    assert fb() == 2\n",
    )
    return str(tmp_path), str(tmp_path / "no_such_config_dir")


def _md(title: str, files: list[str], *, extra: str = "") -> str:
    """A minimal markdown work-item list: a product acceptance + ONE work item owning
    ``files`` (all in a single unit → the broad-vs-single-domain axis the gate judges)."""
    files_line = ", ".join(f"`{f}`" for f in files)
    body = f"files: {files_line}\naccept: `pytest -q`\n"
    if extra:
        body += extra if extra.endswith("\n") else extra + "\n"
    return f"# Product acceptance\nIt all works.\n\n## {title}\n{body}"


def _stub_planner(_prompt: str) -> dict:
    """A DEC-PLANNER model stub: split the broad {alpha, beta} surface into two disjoint
    single-domain sub-tickets. No network — proves the real ``plan_decomposition`` engine
    is wired into the gate."""
    return {
        "units": [
            {"id": "sub-alpha", "goal": "edit alpha", "owns": [ALPHA],
             "depends_on": [], "accept": ["pytest tests/test_alpha.py"], "tier": "high"},
            {"id": "sub-beta", "goal": "edit beta", "owns": [BETA],
             "depends_on": [], "accept": ["pytest tests/test_beta.py"], "tier": "high"},
        ]
    }


# --------------------------------------------------------------------- rejection
def test_broad_ticket_rejected_at_intake(tmp_path):
    """A broad ticket crossing two independent modules is REFUSED on the real intake
    path — it can never enter the board un-decomposed."""
    root, cfg = _fixture(tmp_path)
    md = _md("Broaden everything", [ALPHA, BETA])

    with pytest.raises(I.IntakeError) as excinfo:
        I.intake(md, repo_root=root, config_dir=cfg)

    msg = str(excinfo.value)
    assert "DECOMPOSE-DEFAULT-GATE" in msg
    assert "SINGLE-DOMAIN" in msg
    # The refusal names the two domains / independence groups that tripped it.
    assert "alpha" in msg and "beta" in msg
    # Actionable: it tells the operator how to proceed.
    assert "single-domain: true" in msg


def test_broad_ticket_rejected_via_intake_file(tmp_path):
    """Same rejection through ``intake_file`` — the CLI/product front door."""
    root, cfg = _fixture(tmp_path)
    md_path = tmp_path / "work.md"
    md_path.write_text(_md("Broaden everything", [ALPHA, BETA]))

    with pytest.raises(I.IntakeError):
        I.intake_file(str(md_path), repo_root=root, config_dir=cfg)


# ------------------------------------------------------------------- single-domain
def test_single_domain_ticket_admitted_untouched(tmp_path):
    """A genuinely single-domain ticket (one module + its own test → one domain, one
    independence group) passes the gate untouched."""
    root, cfg = _fixture(tmp_path)
    md = _md("Fix alpha", [ALPHA, TEST_ALPHA])

    plan = I.intake(md, repo_root=root, config_dir=cfg)

    assert [u.goal for u in plan.units] == ["Fix alpha"]
    unit = plan.units[0]
    assert unit.owned_paths == [ALPHA, TEST_ALPHA]
    assert unit.decompose_bypass == ""  # admitted on its own merits, no bypass


def test_single_file_ticket_never_trips_gate(tmp_path):
    """A one-file ticket is single-domain by construction and is admitted — even when
    the path does not resolve (the gate never builds the import graph for it)."""
    root, cfg = _fixture(tmp_path)
    md = _md("Touch one file", ["src/charon/does_not_exist.py"])

    plan = I.intake(md, repo_root=root, config_dir=cfg)
    assert len(plan.units) == 1


# ------------------------------------------------------------------- escape hatch
def test_single_domain_bypass_admits_with_reason_recorded(tmp_path):
    """``single-domain: true`` bypasses the gate for a broad surface, and the reason is
    RECORDED on the unit (and its dict) so the override cannot hide."""
    root, cfg = _fixture(tmp_path)
    md = _md("Broad but declared single", [ALPHA, BETA], extra="single-domain: true")

    plan = I.intake(md, repo_root=root, config_dir=cfg)

    unit = plan.units[0]
    assert unit.owned_paths == [ALPHA, BETA]
    assert unit.decompose_bypass == "single-domain: true (operator-declared)"
    assert unit.to_dict()["decompose_bypass"] == unit.decompose_bypass


def test_no_decompose_bypass_records_explicit_reason(tmp_path):
    """``no-decompose: <reason>`` bypasses AND preserves the operator's explicit reason."""
    root, cfg = _fixture(tmp_path)
    md = _md("Broad but coupled", [ALPHA, BETA],
             extra="no-decompose: alpha and beta are one atomic refactor")

    plan = I.intake(md, repo_root=root, config_dir=cfg)

    unit = plan.units[0]
    assert unit.decompose_bypass == "alpha and beta are one atomic refactor"


# ---------------------------------------------------------------- auto-decompose
def test_auto_decompose_runs_planner_and_names_subtickets(tmp_path):
    """With a planner wired, the gate AUTO-runs DEC-PLANNER over the change surface and
    surfaces the proposed disjoint single-domain sub-tickets in the (still fail-loud)
    refusal — proving ``plan_decomposition`` is on the real intake path."""
    root, cfg = _fixture(tmp_path)
    md = _md("Broaden everything", [ALPHA, BETA])

    with pytest.raises(I.IntakeError) as excinfo:
        I.intake(md, repo_root=root, config_dir=cfg,
                 auto_decompose=True, planner_ask=_stub_planner)

    msg = str(excinfo.value)
    assert "sub-alpha" in msg and "sub-beta" in msg
    assert "parent=broaden-everything" in msg


def test_no_suggestion_without_a_planner(tmp_path):
    """The default path stays network-free: no planner is run, so the refusal carries no
    concrete sub-ticket suggestion (but still rejects the parent)."""
    root, cfg = _fixture(tmp_path)
    md = _md("Broaden everything", [ALPHA, BETA])

    with pytest.raises(I.IntakeError) as excinfo:
        I.intake(md, repo_root=root, config_dir=cfg)
    assert "sub-alpha" not in str(excinfo.value)


# --------------------------------------------------------------- fail-on-revert
def test_gate_is_load_bearing(tmp_path):
    """FAIL-ON-REVERT proof: the SAME broad ticket that is rejected with the gate on is
    ADMITTED un-decomposed when the gate is disabled. So the gate — not some other
    check — is what rejects it; delete/disable the gate and the broad ticket flows
    straight onto the board (the regression this capstone forever forbids)."""
    root, cfg = _fixture(tmp_path)
    md = _md("Broaden everything", [ALPHA, BETA])

    # Gate ON (default): rejected.
    with pytest.raises(I.IntakeError):
        I.intake(md, repo_root=root, config_dir=cfg)

    # Gate OFF: the un-decomposed parent is admitted, owning BOTH modules — exactly the
    # state that reverting the gate would restore.
    plan = I.intake(md, repo_root=root, config_dir=cfg, decompose_gate=False)
    assert len(plan.units) == 1
    assert plan.units[0].owned_paths == [ALPHA, BETA]
