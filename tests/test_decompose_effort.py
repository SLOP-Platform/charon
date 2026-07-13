"""Tests for EFFORT-ESTIMATOR (decompose_effort) — the scoring brain for the
decompose gate's EFFORT axis (DECOMPOSE-EFFORT-AXIS).

These tests exercise the module in isolation (no intake.py wiring — that is a
separate ticket). The FAIL-ON-REVERT guard proves the verdict genuinely comes
from the combined difficulty/size/behavior computation, not a hardcode: with
the three signal functions "reverted" to a constant small reading, the exact
same over-effort ticket that should be flagged instead reads as "ok".
"""
from __future__ import annotations

import time

import pytest

from charon import decompose_effort as eff
from charon.capability.scorecard import ScorecardArtifact, ScorecardRow, ScorecardStore
from charon.decompose_effort import (
    EffortScore,
    effort_verdict,
    estimate_effort,
    tier_threshold,
)

# --------------------------------------------------------------------- fixtures

SMALL_TICKET = {
    "difficulty": 2,
    "owns": ["src/charon/widget.py"],
    "accept": [
        "widget() returns the configured default",
    ],
}

OVER_EFFORT_TICKET = {
    "difficulty": 5,
    "owns": ["src/charon/monolith.py"],
    "accept": (
        "Rewire the whole gateway routing table. Add a new balance tracker. "
        "Add per-provider drain state. Add a park-on-zero transition. "
        "Add a re-arm-on-topup transition. Add a ledger write path. "
        "Add a CLI surface for the new state. Add config migration for old "
        "installs."
    ),
}

ADVISORY_TICKET = {
    "difficulty": 4,
    "owns": ["src/charon/mid.py"],
    "accept": (
        "Add config parsing. Add validation. Add a default fallback. "
        "Add a CLI flag. Add a test fixture."
    ),
}


# ------------------------------------------------------------------- estimate

def test_estimate_effort_small_ticket_is_ok():
    score = estimate_effort(SMALL_TICKET)
    assert isinstance(score, EffortScore)
    assert effort_verdict(score) == "ok"


def test_estimate_effort_over_effort_ticket_is_flagged():
    score = estimate_effort(OVER_EFFORT_TICKET)
    verdict = effort_verdict(score)
    assert verdict in ("advise-split", "over-scope")


def test_high_difficulty_many_behaviors_single_file_is_over_scope():
    """The exact scenario the axis exists for: ONE file, but hard + many
    distinct required behaviors — the surface gate would never see this
    (single file => one independence group => no surface split)."""
    score = estimate_effort(OVER_EFFORT_TICKET)
    assert score.behaviors >= 5
    assert score.difficulty == 5
    assert effort_verdict(score) == "over-scope"


def test_normal_single_domain_ticket_is_untouched():
    score = estimate_effort(SMALL_TICKET)
    assert effort_verdict(score) == "ok"


def test_advisory_band_admits_with_a_warning_not_a_hard_block():
    score = estimate_effort(ADVISORY_TICKET)
    verdict = effort_verdict(score)
    assert verdict == "advise-split"
    # Advisory means NOT the hard verdict — the gate is still meant to admit it.
    assert verdict != "over-scope"


def test_estimate_accepts_object_ticket_via_duck_typing():
    class FakePlanUnit:
        difficulty = 2
        owned_paths = ["src/charon/widget.py"]
        accept = ["widget() returns the configured default"]

    score = estimate_effort(FakePlanUnit())
    assert effort_verdict(score) == "ok"


def test_size_uses_change_surface_when_given():
    surface = {
        "files": ["src/charon/a.py"],
        "call_edges": [["src/charon/a.py", "src/charon/b.py"]] * 6,
        "blast_radius": {"src/charon/a.py": ["src/charon/b.py", "src/charon/c.py"]},
        "independence_groups": [["src/charon/a.py"]],
    }
    ticket = {"difficulty": 2, "owns": ["src/charon/a.py"], "accept": ["one behavior"]}
    without = estimate_effort(ticket)
    with_surface = estimate_effort(ticket, surface=surface)
    assert with_surface.size > without.size
    assert with_surface.total > without.total


def test_missing_difficulty_degrades_to_default_midpoint():
    ticket = {"owns": ["src/charon/x.py"], "accept": ["one behavior"]}
    score = estimate_effort(ticket)
    assert score.difficulty == eff.DEFAULT_DIFFICULTY


def test_difficulty_is_clamped_to_1_5():
    hi = estimate_effort({"difficulty": 99, "owns": ["a.py"], "accept": ["x"]})
    lo = estimate_effort({"difficulty": -3, "owns": ["a.py"], "accept": ["x"]})
    assert hi.difficulty == 5
    assert lo.difficulty == 1


# --------------------------------------------------------------- tier thresholds

def test_same_score_differs_by_tier_with_default_multipliers():
    """No actuals supplied: the sane per-tier defaults still make the SAME
    score land in different bands for a weak vs. a strong tier."""
    score = estimate_effort(ADVISORY_TICKET)  # lands in the default advisory band
    ok_or_split_strong = effort_verdict(score, tier="strong")
    over_weak = effort_verdict(score, tier="weak")
    assert over_weak == "over-scope"
    assert ok_or_split_strong in ("ok", "advise-split")
    assert over_weak != ok_or_split_strong


def test_unknown_tier_name_does_not_scale():
    score = estimate_effort(ADVISORY_TICKET)
    assert effort_verdict(score, tier="totally-unknown-tier") == effort_verdict(score)


def test_tier_threshold_scales_from_a_plain_actuals_map():
    actuals = {"strong": 10.0, "weak": 30.0}  # weak tier takes 3x as long
    strong = tier_threshold("strong", actuals=actuals)
    weak = tier_threshold("weak", actuals=actuals)
    assert weak.soft < strong.soft
    assert weak.hard < strong.hard
    assert weak.soft == pytest.approx(strong.soft / 3, rel=1e-3)


def test_tier_threshold_scales_from_row_like_iterable():
    rows = [
        {"tier": "strong", "avg_minutes": 12.0},
        {"tier": "strong", "avg_minutes": 8.0},
        {"tier": "weak", "avg_minutes": 40.0},
    ]
    strong = tier_threshold("strong", actuals=rows)
    weak = tier_threshold("weak", actuals=rows)
    assert weak.soft < strong.soft


def test_tier_threshold_scales_from_scorecard_path(tmp_path):
    store = ScorecardStore(tmp_path)
    artifact = ScorecardArtifact(
        seq=1,
        timestamp=time.time(),
        rows=[
            ScorecardRow(
                model="big-model", work_class="codegen", score=0.9, samples=5,
                metadata={"tier": "strong", "avg_minutes": 10.0},
            ),
            ScorecardRow(
                model="small-model", work_class="codegen", score=0.5, samples=5,
                metadata={"tier": "weak", "avg_minutes": 35.0},
            ),
        ],
    )
    store.freeze(artifact)

    strong = tier_threshold("strong", actuals=tmp_path)
    weak = tier_threshold("weak", actuals=tmp_path)
    assert weak.soft < strong.soft
    assert weak.hard < strong.hard


def test_scorecard_path_missing_degrades_to_default_and_never_creates_dir(tmp_path):
    missing = tmp_path / "no-such-scorecard-root"
    assert not missing.exists()
    threshold = tier_threshold("strong", actuals=missing)
    assert threshold == tier_threshold("strong")  # sane default fallback
    assert not missing.exists()  # never a filesystem side effect


def test_no_actuals_and_no_tier_is_the_flat_default():
    assert tier_threshold(None) == eff.EffortThreshold(
        soft=eff.DEFAULT_SOFT_THRESHOLD, hard=eff.DEFAULT_HARD_THRESHOLD
    )


# -------------------------------------------------------------- fail-on-revert

def test_fail_on_revert_constant_effort_misclassifies_over_effort_as_ok(monkeypatch):
    """FAIL-ON-REVERT: with the real signal computation, the over-effort ticket
    is flagged. "Revert" the computation to a constant small reading (as if
    ``estimate_effort`` ignored the ticket and always returned a trivial
    score) and the SAME ticket now reads "ok" — proving the verdict genuinely
    depends on the combined difficulty/size/behavior computation, not a
    hardcode."""
    real_score = estimate_effort(OVER_EFFORT_TICKET)
    assert effort_verdict(real_score) == "over-scope"

    def _reverted_difficulty(_ticket):
        return 1

    def _reverted_size(_ticket, _surface):
        return 1.0, "size=1 (reverted)"

    def _reverted_behaviors(_ticket):
        return 1, "behaviors=1 (reverted)"

    monkeypatch.setattr(eff, "_difficulty", _reverted_difficulty)
    monkeypatch.setattr(eff, "_size", _reverted_size)
    monkeypatch.setattr(eff, "_behaviors", _reverted_behaviors)

    reverted_score = estimate_effort(OVER_EFFORT_TICKET)
    assert effort_verdict(reverted_score) == "ok"
    assert reverted_score.total != real_score.total
