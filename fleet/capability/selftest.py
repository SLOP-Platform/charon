#!/usr/bin/env python3
"""PROOF-OF-EFFECT gate for assign() (anti-inert mechanization discipline —
see fleet/TICKET-BENCHMARK-HARNESS.md's "no manual scoring" precedent and
memory: charon-pools-redesign's decision-differentiation gate).

Three things must be TRUE for assign() to be a real recommender and not an
inert wrapper that always names the same model:

  1. DIFFERENTIATION: different work_classes route to DIFFERENT best models.
  2. AVAILABILITY CHANGES THE PICK: making the top-graded model unavailable
     causes assign() to fall through to the next-best eligible candidate,
     not silently keep recommending an unavailable model.
  3. CONFIDENCE-AWARE SCORING: a model with more evidence AND a real
     observed failure does NOT lose to a single lucky sample (the #14
     review's must-fix — fleet/scratch/ticket-assign-review.md Q1).

Per the #14 review's should-fix #2, all pinned/hard assertions below run
against a FROZEN synthetic fixture
(capability/testdata/scorecard-fixture.tsv), NOT the live, append-only
fleet/model-scorecard.tsv — so this gate asserts CODE behavior and stays
stable while the live scorecard keeps growing from ongoing benchmark runs.
A separate, non-asserting smoke check (smoke_check_live_scorecard()) still
exercises assign() against whatever the live scorecard currently contains,
tolerant of it changing under us.

Run: python3 fleet/capability/selftest.py
Exits 0 if every check passes, 1 otherwise (prints PASS/FAIL per check).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assign import assign  # noqa: E402
from availability import StaticAvailability  # noqa: E402
from grades import MIN_N, DEFAULT_TSV, ScorecardGradesProvider  # noqa: E402

FIXTURE_TSV = Path(__file__).resolve().parent / "testdata" / "scorecard-fixture.tsv"

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(label)


def main() -> int:
    if not FIXTURE_TSV.exists():
        print(f"FATAL: fixture missing at {FIXTURE_TSV}")
        return 1

    grades = ScorecardGradesProvider(FIXTURE_TSV)   # frozen fixture, not live data
    no_avail = StaticAvailability()                 # every model 'unknown' — pure grade-based ranking

    print("=" * 78)
    print("PROOF-OF-EFFECT: differentiation across work_classes (frozen fixture)")
    print("=" * 78)

    picks: dict[str, str] = {}
    for wc in ("ci-infra", "money-path", "routing", "refactor", "bugfix", "greenfield-feature", "frontend"):
        r = assign(wc, grades, no_avail)
        picks[wc] = r.picked
        print(f"  {wc:20s} -> {r.picked}")

    distinct = set(picks.values())
    check(
        "at least 2 distinct models win across the 7 work_classes (not inert)",
        len(distinct) >= 2,
        f"winners: {sorted(distinct)}",
    )

    # ci-infra (scoped candidate set: the fixture's 3 ci-infra rows only) —
    # glm-5.2 is the ONLY model with a clean MERGE; the others land FIXES.
    r_ci = assign("ci-infra", grades, no_avail,
                   candidate_models=["glm-5.2", "kimi-k2.6", "claude-opus-4-8"])
    check(
        "ci-infra picks glm-5.2 (only clean-MERGE model in the fixture for this class)",
        r_ci.picked == "glm-5.2",
        f"got {r_ci.picked}",
    )

    # money-path, scoped to its 3 direct-data models only (keeps this
    # assertion about the BLOCK penalty, not entangled with the separate
    # fallback-de-prioritization behavior tested below).
    r_money = assign("money-path", grades, no_avail,
                      candidate_models=["hy3-preview-or", "glm-5.2", "claude-opus-4-8"])
    money_rank = [c.model for c in r_money.ranked]
    check(
        "money-path never picks hy3-preview-or (its only BLOCK-verdict class)",
        r_money.picked != "hy3-preview-or",
        f"picked {r_money.picked}",
    )
    check(
        "money-path ranks hy3-preview-or LAST (real BLOCK penalty, not just excluded)",
        money_rank[-1] == "hy3-preview-or",
        f"ranking: {money_rank}",
    )

    print()
    print("=" * 78)
    print("PROOF-OF-EFFECT: availability changes the pick")
    print("=" * 78)

    top_pick = r_money.picked
    busy_avail = StaticAvailability({top_pick: "busy"}, note="[selftest] injected: top pick marked busy")
    r_money_busy = assign("money-path", grades, busy_avail,
                           candidate_models=["hy3-preview-or", "glm-5.2", "claude-opus-4-8"])

    check(
        f"marking the ungated top pick ({top_pick!r}) busy changes the recommendation",
        r_money_busy.picked != top_pick and r_money_busy.picked is not None,
        f"new pick: {r_money_busy.picked}",
    )
    excluded_ids = {c.model for c in r_money_busy.ranked if c.excluded_reason}
    check(
        f"{top_pick!r} is visibly EXCLUDED in the ranked list (auditable, not silently dropped)",
        top_pick in excluded_ids,
        f"excluded set: {excluded_ids}",
    )

    print()
    print("=" * 78)
    print("PROOF-OF-EFFECT: D&S — a blocked ticket is refused, never assigned")
    print("=" * 78)
    r_blocked = assign("routing", grades, no_avail, blockers=["SOME-UNMET-DEP"])
    check("blocked ticket returns refused=True with no pick", r_blocked.refused and r_blocked.picked is None,
          f"refused={r_blocked.refused} picked={r_blocked.picked}")

    print()
    print("=" * 78)
    print("MUST-FIX #1: confidence-aware score fixes the small-N-over-trust inversion")
    print("=" * 78)
    # This is the exact case the #14 review demonstrated as broken: a model
    # with n=3 real evidence including a genuine BLOCK (glm-5.2/routing)
    # must NOT rank below a model with a single lucky MERGE (kimi-k2.6/routing,
    # n=1). Old formula: glm-5.2 scored 33.3, kimi-k2.6 scored 100 -> inverted.
    g_glm = grades.grade("glm-5.2", "routing")
    g_kimi = grades.grade("kimi-k2.6", "routing")
    check("fixture reproduces the review's shape: glm-5.2/routing has n=3 with a real BLOCK",
          g_glm.n == 3 and g_glm.block == 1 and g_glm.merge == 2,
          f"n={g_glm.n} merge={g_glm.merge} block={g_glm.block}")
    check("fixture reproduces the review's shape: kimi-k2.6/routing is a lucky n=1 MERGE",
          g_kimi.n == 1 and g_kimi.merge == 1 and g_kimi.block == 0,
          f"n={g_kimi.n} merge={g_kimi.merge} block={g_kimi.block}")
    check(
        "glm-5.2/routing (n=3, real BLOCK) does NOT rank below kimi-k2.6/routing (n=1 lucky MERGE)",
        g_glm.score >= g_kimi.score,
        f"glm-5.2 score={g_glm.score:.2f}  kimi-k2.6 score={g_kimi.score:.2f}",
    )
    r_routing = assign("routing", grades, no_avail, candidate_models=["glm-5.2", "kimi-k2.6"])
    check(
        "assign() picks glm-5.2 for routing (more evidence wins over one lucky sample)",
        r_routing.picked == "glm-5.2",
        f"picked {r_routing.picked}; ranking: {[c.model for c in r_routing.ranked]}",
    )
    check("both routing candidates are flagged LOW_CONFIDENCE (n < MIN_N=%d)" % MIN_N,
          g_glm.low_confidence and g_kimi.low_confidence,
          f"glm.low_confidence={g_glm.low_confidence} kimi.low_confidence={g_kimi.low_confidence}")
    check("LOW-CONFIDENCE flag is printed in the rationale, not just carried silently on Grade",
          "LOW-CONFIDENCE" in r_routing.rationale,
          repr(r_routing.rationale))

    g_sonnet_tests = grades.grade("claude-sonnet-5", "tests")
    check(
        "a high-n grade (n=5 >= MIN_N) is NOT flagged LOW_CONFIDENCE (contrast case)",
        g_sonnet_tests.n >= MIN_N and not g_sonnet_tests.low_confidence,
        f"n={g_sonnet_tests.n} low_confidence={g_sonnet_tests.low_confidence}",
    )

    print()
    print("=" * 78)
    print("SHOULD-FIX #2 coverage: tier-exclusion path")
    print("=" * 78)
    # money-path, required_tier=high: claude-opus-4-8 (tier=high) matches;
    # glm-5.2 (tier=med) must be excluded for tier mismatch even though it
    # has an equal-or-better score; hy3-preview-or has no catalog tier_hint
    # (unknown, documented as "pass through, not excluded" — see
    # availability.py-adjacent get_tier_hint() docstring in grades.py).
    r_tier = assign("money-path", grades, no_avail, required_tier="high",
                     candidate_models=["claude-opus-4-8", "glm-5.2", "hy3-preview-or"])
    tier_excluded = {c.model: c.excluded_reason for c in r_tier.ranked if c.excluded_reason}
    check(
        "glm-5.2 (tier=med) is excluded for tier mismatch when required_tier=high",
        "glm-5.2" in tier_excluded and "tier mismatch" in tier_excluded["glm-5.2"],
        f"excluded: {tier_excluded}",
    )
    check(
        "the tier-matching candidate (claude-opus-4-8, tier=high) is picked",
        r_tier.picked == "claude-opus-4-8",
        f"picked {r_tier.picked}",
    )
    check(
        "the tier exclusion is surfaced in the rationale (auditable, not silent)",
        "glm-5.2" in r_tier.rationale and "EXCLUDED" in r_tier.rationale,
        repr(r_tier.rationale),
    )

    print()
    print("=" * 78)
    print("SHOULD-FIX #2 coverage: generalist-fallback path")
    print("=" * 78)
    # greenfield-feature has NO direct rows for any model in the fixture ->
    # every candidate must fall back to its own cross-class generalist
    # aggregate, and assign() must still produce a pick (not refuse).
    r_fallback_only = assign("greenfield-feature", grades, no_avail)
    check(
        "no-direct-data class still produces a pick via generalist fallback",
        r_fallback_only.picked is not None and not r_fallback_only.refused,
        f"picked={r_fallback_only.picked} refused={r_fallback_only.refused}",
    )
    g_pick_fallback = grades.grade(r_fallback_only.picked, "greenfield-feature")
    check(
        "the picked grade for the no-data class is explicitly flagged fallback_used",
        g_pick_fallback.fallback_used and g_pick_fallback.used_work_class == "generalist",
        f"fallback_used={g_pick_fallback.fallback_used} used_work_class={g_pick_fallback.used_work_class}",
    )

    print()
    print("=" * 78)
    print("SHOULD-FIX #3: generalist fallback is de-prioritized vs. direct evidence")
    print("=" * 78)
    # frontend: claude-opus-4-8 and glm-5.2 have DIRECT frontend rows.
    # claude-sonnet-5 has none for frontend (its only fixture data is under
    # "tests", n=5, all but one MERGE) -> claude-sonnet-5's generalist score
    # is objectively HIGHER than claude-opus-4-8's direct score (more,
    # cleaner evidence, just for the wrong class). Without de-prioritization
    # claude-sonnet-5 would win frontend on raw score alone despite zero
    # direct frontend evidence — that's exactly the "ranked as an equal
    # peer" defect should-fix #3 flagged.
    g_sonnet_fb = grades.grade("claude-sonnet-5", "frontend")
    g_opus_direct = grades.grade("claude-opus-4-8", "frontend")
    check(
        "fixture reproduces the review's shape: fallback candidate outscores the direct candidate on raw score",
        g_sonnet_fb.fallback_used and g_sonnet_fb.score > g_opus_direct.score,
        f"sonnet(fallback) score={g_sonnet_fb.score:.2f}  opus(direct) score={g_opus_direct.score:.2f}",
    )
    r_frontend = assign("frontend", grades, no_avail,
                         candidate_models=["claude-opus-4-8", "glm-5.2", "claude-sonnet-5"])
    check(
        "assign() still picks the DIRECT-evidence model (claude-opus-4-8), not the "
        "higher-raw-scoring fallback model (claude-sonnet-5)",
        r_frontend.picked == "claude-opus-4-8",
        f"picked {r_frontend.picked}; ranking: {[c.model for c in r_frontend.ranked]}",
    )
    check(
        "the de-prioritized higher-scoring fallback candidate is surfaced in the rationale",
        "claude-sonnet-5" in r_frontend.rationale and "generalist fallback" in r_frontend.rationale,
        repr(r_frontend.rationale),
    )

    print()
    print("=" * 78)
    print("HONESTY CHECK: live session-bridge board today has no model-tagged sessions")
    print("=" * 78)
    print("  See availability.py's SessionBridgeAvailability docstring — the live board")
    print("  (checked via mcp__session-bridge__board during grounding) carries exactly one")
    print("  session ('yoda', the manager), no live droid/model sessions. So the")
    print("  availability-changes-the-pick proof above uses an INJECTED StaticAvailability")
    print("  fake, not a live-board assertion — stated plainly, not silently substituted.")

    smoke_check_live_scorecard()

    print()
    if FAILURES:
        print(f"SELFTEST: {len(FAILURES)} FAILURE(S): {FAILURES}")
        return 1
    print("SELFTEST: ALL CHECKS PASS — assign() differentiates on a frozen fixture, "
          "confidence-aware scoring fixes the small-N inversion, and "
          "availability demonstrably changes the pick.")
    return 0


def smoke_check_live_scorecard() -> None:
    """Non-asserting, tolerant smoke check against the LIVE, append-only
    fleet/model-scorecard.tsv (per #14 review should-fix #2: "keep ONE
    separate lightweight real-scorecard smoke check"). This intentionally
    does NOT assert specific picks/scores — the live file is being appended
    by ongoing benchmark runs and reading it as ground truth here would
    make this gate flaky against data changes, not code regressions (that's
    the whole reason the hard assertions above moved to the frozen fixture).
    This just proves assign() doesn't crash against real-shaped live data.
    """
    print()
    print("=" * 78)
    print("SMOKE (non-asserting): assign() against the LIVE model-scorecard.tsv")
    print("=" * 78)
    try:
        live_grades = ScorecardGradesProvider(DEFAULT_TSV)
        models = live_grades.all_models()
        if not models:
            print(f"  [SKIP] {DEFAULT_TSV} not found or has no rows yet — nothing to smoke-test")
            return
        no_avail = StaticAvailability()
        for wc in ("ci-infra", "money-path", "routing"):
            r = assign(wc, live_grades, no_avail)
            print(f"  [INFO] live {wc:12s} -> {r.picked} (informational only, not asserted)")
    except Exception as e:  # never fail the gate on live-data shape surprises
        print(f"  [INFO] live smoke check raised {type(e).__name__}: {e} (non-fatal, informational only)")


if __name__ == "__main__":
    raise SystemExit(main())
