"""EFFORT-WIRE — the EFFORT axis hooked into the DECOMPOSE-DEFAULT-GATE.

These tests exercise the effort axis on the REAL intake path (``intake`` → ``analyze`` —
the same code production uses; there is no side function), exactly like
``test_decompose_default_gate``.

The load-bearing claim (see ``test_effort_axis_catches_what_surface_misses`` and
``test_effort_hook_is_load_bearing``): a SINGLE-FILE ticket that is over-scope by EFFORT
(high difficulty + many required behaviours) is provably invisible to the SURFACE axis —
a one-file ticket never even builds the import graph, so the surface axis always admits
it. The EFFORT axis is therefore the ONLY thing that can refuse it. Revert the effort
hook (or disable the gate) → the over-effort single-file ticket is admitted silently →
these tests go RED.
"""
from __future__ import annotations

import pathlib

import pytest

from charon import decompose
from charon import decompose_effort as eff
from charon import intake as I

ALPHA = "src/charon/alpha.py"
TEST_ALPHA = "tests/test_alpha.py"


def _write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _one_domain_fixture(tmp_path: pathlib.Path) -> tuple[str, str]:
    """One source module + its own mapped test → ONE domain / ONE independence group.
    The surface axis admits this untouched (proven by
    ``test_decompose_default_gate.test_single_domain_ticket_admitted_untouched``), so any
    refusal here is the EFFORT axis, and the effort SIZE signal reuses the surface the
    surface axis already computed for it."""
    _write(tmp_path / ALPHA, "ALPHA = 1\n\n\ndef fa():\n    return ALPHA\n")
    _write(
        tmp_path / TEST_ALPHA,
        "from charon.alpha import fa\n\n\ndef test_a():\n    assert fa() == 1\n",
    )
    return str(tmp_path), str(tmp_path / "no_such_config_dir")


def _md(title: str, files: list[str], *, difficulty: int | None, behaviors: int) -> str:
    """A single work item owning ``files`` with a declared ``difficulty`` and ``behaviors``
    distinct accept commands (each backtick span is one behaviour)."""
    files_line = ", ".join(f"`{f}`" for f in files)
    lines = ["# Product acceptance\nIt all works.\n", f"## {title}", f"files: {files_line}"]
    if difficulty is not None:
        lines.append(f"difficulty: {difficulty}")
    for n in range(behaviors):
        lines.append(f"accept: `pytest -q -k case_{n}`")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------- the core proof
def test_single_file_over_effort_is_refused_by_effort_axis(tmp_path):
    """FAIL-ON-REVERT: a single-file ticket that is high-difficulty + many-behaviour is
    REFUSED at intake by the EFFORT axis, with a fail-loud, actionable message naming the
    effort reason (score vs hard band + the signals). One file → the surface axis cannot be
    what refused it."""
    md = _md("Rewrite the whole thing in one file", ["src/charon/big.py"],
             difficulty=5, behaviors=7)

    with pytest.raises(I.IntakeError) as excinfo:
        I.intake(md, repo_root=str(tmp_path))

    msg = str(excinfo.value)
    assert "DECOMPOSE-EFFORT-AXIS" in msg
    assert "OVER-SCOPE by EFFORT" in msg
    assert "difficulty=5" in msg and "behaviors=7" in msg
    assert "hard threshold" in msg
    # Actionable: tells the operator how to proceed (split or bypass).
    assert "single-domain: true" in msg or "no-decompose" in msg


def test_effort_axis_catches_what_surface_misses(tmp_path):
    """Prove the EFFORT axis is the discriminator, not the surface axis. The SAME one-file
    ticket is ADMITTED when its effort is low and REFUSED only when its effort is high — the
    surface axis (which admits every single-file ticket) cannot explain the flip."""
    path = "src/charon/big.py"

    # Low effort → admitted (this is exactly what the surface axis alone would do to the
    # over-effort ticket too, since both are single-file).
    admit = I.intake(_md("Small edit", [path], difficulty=1, behaviors=1),
                     repo_root=str(tmp_path))
    assert [u.goal for u in admit.units] == ["Small edit"]

    # High effort → refused, and the refusal is the EFFORT axis, NOT the surface gate.
    with pytest.raises(I.IntakeError) as excinfo:
        I.intake(_md("Rewrite the whole thing", [path], difficulty=5, behaviors=7),
                 repo_root=str(tmp_path))
    msg = str(excinfo.value)
    assert "DECOMPOSE-EFFORT-AXIS" in msg
    # The surface gate provably did NOT fire — a single file never trips it.
    assert "DECOMPOSE-DEFAULT-GATE" not in msg
    assert "SINGLE-DOMAIN" not in msg


def test_effort_hook_is_load_bearing(tmp_path):
    """Revert analog: with the gate disabled (``decompose_gate=False``) the over-effort
    single-file ticket is admitted SILENTLY — proving the effort hook is what refuses it
    when the gate is on. Removing the hook reproduces this silent admission → RED."""
    md = _md("Rewrite the whole thing", ["src/charon/big.py"], difficulty=5, behaviors=7)

    silent = I.intake(md, repo_root=str(tmp_path), decompose_gate=False)
    assert len(silent.units) == 1  # admitted, no refusal — the hole the effort axis closes


# --------------------------------------------------------------------- normal ticket
def test_normal_single_file_ticket_admitted_untouched(tmp_path):
    """A normal ticket (low difficulty, one behaviour) is admitted with no effort advisory
    recorded — the axis does not perturb ordinary work."""
    md = _md("Fix a bug", ["src/charon/small.py"], difficulty=2, behaviors=1)

    plan = I.intake(md, repo_root=str(tmp_path))

    assert len(plan.units) == 1
    unit = plan.units[0]
    assert unit.effort_advisory == ""
    assert not any("effort advisory" in f for f in unit.flags)
    assert not unit.propose_only


# --------------------------------------------------------------------- advisory band
def test_advisory_band_admits_with_warning_recorded(tmp_path):
    """A soft-band ticket is ADMITTED and STAYS RUNNABLE (never blocked — irreducible
    one-file-but-big work is allowed) but records a recoverable advisory warning on the
    unit's DEDICATED ``effort_advisory`` field, which cannot hide. Critically, the advisory
    must NOT be laundered through ``flags`` — that field also drives ``propose_only`` and
    ``decompose.assess_plan``'s low-confidence check, so putting it there would silently
    turn a warn-only soft-band call into a hard block, violating the axis's contract."""
    md = _md("Chunky but coupled", ["src/charon/chunky.py"], difficulty=4, behaviors=3)

    # Confirm the fixture actually lands in the advise-split band (not ok, not over-scope),
    # so this test proves the SOFT branch and not something else.
    plan = I.intake(md, repo_root=str(tmp_path))
    unit = plan.units[0]
    score = eff.estimate_effort(unit)
    assert eff.effort_verdict(score, tier=unit.tier) == "advise-split"

    assert "effort advisory" in unit.effort_advisory
    assert "advise-split band" in unit.effort_advisory
    # The advisory is NOT recorded on ``flags`` — that would (silently) block the unit.
    assert not any("effort advisory" in f for f in unit.flags)

    # ADMITTED and RUNNABLE: a soft-band advisory must never behave like a hard refusal.
    assert not unit.propose_only
    confidence = decompose.assess_plan(plan)
    assert confidence.runnable
    # Carried through to the emitted artifact too — cannot hide there either.
    assert unit.to_dict()["effort_advisory"] == unit.effort_advisory


# --------------------------------------------------------------------- escape hatch
def test_bypass_admits_over_effort_ticket_with_reason_recorded(tmp_path):
    """The SAME escape hatch bypasses the EFFORT axis too: an over-effort ticket carrying
    ``no-decompose: <reason>`` is admitted, and the reason is recorded (cannot hide)."""
    md = _md("Rewrite everything", ["src/charon/big.py"], difficulty=5, behaviors=7)
    md += "no-decompose: irreducible one-file rewrite, tracked separately\n"

    plan = I.intake(md, repo_root=str(tmp_path))

    assert len(plan.units) == 1
    unit = plan.units[0]
    assert unit.decompose_bypass == "irreducible one-file rewrite, tracked separately"
    # Bypass skips the axis entirely — no advisory is layered on top of an explicit override.
    assert unit.effort_advisory == ""
    assert not any("effort advisory" in f for f in unit.flags)


# --------------------------------------------------------------------- surface reuse
def test_effort_axis_reuses_the_surface_axis_change_surface(tmp_path):
    """A MULTI-FILE single-domain ticket (one module + its own test → one independence
    group) is admitted by the surface axis, which computes a ``change_surface`` for it. When
    that same ticket is over-effort, the EFFORT axis refuses it — reusing the ALREADY-computed
    surface for its SIZE signal (no second change_surface pass on the intake path)."""
    root, cfg = _one_domain_fixture(tmp_path)
    md = _md("Overhaul alpha", [ALPHA, TEST_ALPHA], difficulty=5, behaviors=8)

    with pytest.raises(I.IntakeError) as excinfo:
        I.intake(md, repo_root=root, config_dir=cfg)

    msg = str(excinfo.value)
    # Refused by EFFORT (the surface axis admitted this one-domain unit).
    assert "DECOMPOSE-EFFORT-AXIS" in msg
    # SIZE was read off the surface facts, not the compute-free owned-path fallback.
    assert "surface:" in msg
