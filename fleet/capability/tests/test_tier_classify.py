"""test_tier_classify.py — fail-on-revert guard for the work->tier classifier.

Guards the ONE tier rule (fleet/capability/tier_classify.py) that both the
validate_board drift check and the gateway routing path read. Goes RED if:
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
    ("design-review", 3, "fleet/design.md", "strong"),
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


# ── live board is drift-free after the balance pass (regression fence) ───────
def test_live_board_is_balanced():
    board = FLEET / "board"
    if not board.exists():
        pytest.skip("board not present")
    rows = tc.board_drift(str(board))
    assert rows == [], f"live board has {len(rows)} tier drift(s): {[r[0] for r in rows]}"
