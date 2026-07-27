"""test_tier_classify.py — fail-on-revert guard for the work->tier classifier.

Guards the ONE tier rule (fleet/capability/tier_classify.py). Its only LIVE
consumer is the validate_board drift check; the litellm routing half is designed
but not wired (see the module docstring), and (d) below proves the tag would
resolve, not that anything in production calls it. The gate-executed red-proof
for the drift GATE itself lives in fleet/tests/tier-drift.test.sh (this pytest
file is run by no gate). Goes RED if:
  (a) the rubric anchors stop deriving their intended tier (rule regressed),
  (b) the board drift scan stops catching a deliberately mis-tiered ticket,
  (c) a rule REVERT stops changing a known ticket's derived tier (the drift
      check would then be blind — this is the fail-on-revert proof),
  (d) the LiteLLM tier tag stops resolving to a real Router model-group.

Run: python3 -m pytest fleet/capability/tests/test_tier_classify.py -q
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
CAP = HERE.parent.parent           # fleet/capability
FLEET = CAP.parent                 # fleet
sys.path.insert(0, str(CAP))
import tier_classify as tc  # noqa: E402


# ── (a) rubric anchors: each fixed case must derive its intended tier ─────────
@pytest.mark.parametrize("wc,d,owns,expect", [
    ("bugfix", 2, "src/charon/providers.py", "frontier"),                 # security ratchet
    ("money-path", 5, "src/charon/forwarder.py, tests/t.py", "frontier"), # live-forward + hard
    ("routing", 2, "src/charon/routing_policy/x.py", "strong"),           # money floor, never economy
    ("routing", 5, "src/charon/routing_policy/x.py,a.py,b.py,c.py", "frontier"),  # d5
    ("docs", 2, "docs/x.md", "economy"),                                  # trivial docs
    ("docs", 4, "docs/x.md", "strong"),                                   # hard docs escalate
    ("design-review", 4, "fleet/design.md", "frontier"),                 # architecture cognition
    ("design-review", 3, "fleet/design.md", "frontier"),                 # F11 review ratchet
    ("design-review", 2, "fleet/design.md", "strong"),                   # review floor: never economy
    ("rig-meta", 1, "fleet/x.sh", "economy"),                            # trivial single-surface
    ("rig-meta", 3, "fleet/a.sh, fleet/b.sh", "strong"),                 # middle band
])
def test_rubric_anchors(wc, d, owns, expect):
    tier, _why = tc.classify_tier(wc, d, owns)
    assert tier == expect, f"{wc} d{d} {owns!r} -> {tier}, expected {expect}"


# ── (b) drift scan catches a deliberately mis-tiered ticket ──────────────────
def test_drift_catches_wrong_tier(tmp_path):
    board = tmp_path / "board"
    board.mkdir()
    # security path MUST be frontier; declare it economy -> drift must flag frontier.
    (board / "BAD.md").write_text(
        "tier: economy\nwork_class: bugfix\ndifficulty: 2\nowns: src/charon/providers.py\n"
    )
    rows = tc.board_drift(str(board))
    assert rows == [("BAD", "economy", "frontier", rows[0][3])]
    assert "security" in rows[0][3]


def test_drift_clean_when_correct(tmp_path):
    board = tmp_path / "board"
    board.mkdir()
    (board / "OK.md").write_text(
        "tier: frontier\nwork_class: bugfix\ndifficulty: 2\nowns: src/charon/providers.py\n"
    )
    assert tc.board_drift(str(board)) == []


# ── (c) FAIL-ON-REVERT: reverting the rule changes a known ticket's tier ─────
def test_fail_on_revert(monkeypatch):
    """If the SEC pattern is reverted (security no longer forces frontier), a
    known security ticket's derived tier CHANGES — proving the drift check is
    live-wired to the rule, not a frozen snapshot."""
    wc, d, owns = "bugfix", 2, "src/charon/providers.py"
    good, _ = tc.classify_tier(wc, d, owns)
    assert good == "frontier"
    # revert the security rule to match nothing
    monkeypatch.setattr(tc, "SEC_RE", re.compile(r"(?!x)x"))
    reverted, _ = tc.classify_tier(wc, d, owns)
    assert reverted != good, "reverting SEC_RE did NOT change the tier — rule is not load-bearing"
    assert reverted == "strong"  # d2 bugfix, non-money -> middle band


# ── (d) LiteLLM tier tag resolves to a real Router model-group ───────────────
def test_litellm_tag_resolves_to_model_group():
    tsv = FLEET / "tier-models.tsv"
    proof = tc.validate_router(str(tsv))
    joined = "\n".join(proof)
    for tier in ("frontier", "strong", "economy"):
        assert f"tag '{tier}'" in joined, f"tier tag {tier} did not resolve as a model-group"


# ── EFFORT axis (F5): breadth alone must not reach frontier ──────────────────
def test_breadth_alone_never_promotes():
    """The rule the old `nsurf >= 3` clause broke. A d2 money ticket that owns
    MANY files is still `strong`; the same work at d3 with a real requirement
    list clears the ported HARD band and promotes. Reverting the effort clause
    back to a breadth test flips the first case."""
    wide = ", ".join(f"src/charon/routing_policy/m{i}.py" for i in range(12))
    tier, why = tc.classify_tier("money-path", 2, wide, "- one thing\n")
    assert tier == "strong", f"breadth alone promoted to {tier} ({why})"
    accept = "\n".join(f"- behaviour {i}" for i in range(10))
    tier2, _ = tc.classify_tier("money-path", 3, "src/charon/routing_policy/m0.py", accept)
    assert tier2 == "frontier", "a genuinely high-EFFORT money ticket must still promote"


def test_effort_constants_match_the_product_module():
    """PORT PARITY (option (b)'s one real cost). fleet/capability/effort.py is a
    port of the product's src/charon/decompose_effort.py; pin both sides."""
    import effort as ef
    assert (ef.DIFFICULTY_WEIGHT, ef.SIZE_WEIGHT, ef.BEHAVIOR_WEIGHT) == (2.0, 0.15, 1.0)
    assert (ef.SOFT_THRESHOLD, ef.HARD_THRESHOLD) == (10.0, 16.0)


# ── live board: derived-tier deltas are the REVIEWABLE OUTPUT, not silent ────
# This rule change deliberately does NOT rewrite fleet/board/*.md (that file set is
# owned by another live ticket). The tickets below are the ones whose DERIVED tier
# moved; they are pending a board-side re-tier. When that lands this set empties —
# which is exactly when this fence must be updated, not silently relaxed.
PENDING_RETIERS = {
    # F5 — EFFORT replaces the breadth proxy
    "FT-CATALOG-SEED": ("frontier", "strong"),
    "PRICE-REFRESHER": ("strong", "frontier"),
    # F11 — review-class ratchet (design-review d3 no longer demoted to strong)
    "BLAST-TIER-ENFORCEMENT-DESIGN": ("strong", "frontier"),
    "INERT-WIRING-ENFORCEMENT-DURABLE": ("strong", "frontier"),
    "REVIEW-RECONCILE-GATE-DESIGN": ("strong", "frontier"),
    "SUBAGENT-WORKTREE-SANDBOX": ("strong", "frontier"),
    "WORKLOOP-INTEGRITY-STACK-SPIKE": ("strong", "frontier"),
}


def test_live_board_drift_is_exactly_the_pending_retiers():
    board = FLEET / "board"
    if not board.exists():
        pytest.skip("board not present")
    got = {r[0]: (r[1], r[2]) for r in tc.board_drift(str(board))}
    assert got == PENDING_RETIERS, (
        "live board drift no longer matches the recorded pending re-tiers "
        f"(unexpected: {set(got) - set(PENDING_RETIERS)}; "
        f"resolved: {set(PENDING_RETIERS) - set(got)})"
    )


def test_no_review_class_downgrade():
    """F11 as an INVARIANT over the live board, not just two examples: no
    design-review ticket may derive a tier BELOW `strong`, ever."""
    board = FLEET / "board"
    if not board.exists():
        pytest.skip("board not present")
    for f in sorted(board.glob("*.md")):
        txt = f.read_text()
        if tc._field(txt, "work_class") != "design-review":
            continue
        tier, why = tc.classify_tier(
            "design-review", tc._field(txt, "difficulty"), tc._field(txt, "owns"),
            tc._block_field(txt, "accept"))
        assert tier in ("strong", "frontier"), f"{f.stem} review-class -> {tier} ({why})"
