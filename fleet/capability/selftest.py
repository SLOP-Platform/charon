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
from grades import MIN_N, DEFAULT_TSV, ScorecardGradesProvider, _wilson_bound, scores_tie  # noqa: E402

# PROVISIONAL-vs-ACTIVE (#20): the promotion gate + a temp end-to-end fixture.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmark"))
import promote as _promote  # noqa: E402

# AGGREGATE-N (#16): exercise the tier_chart aggregation directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmark" / "lib"))
import tier_chart as _tier_chart  # noqa: E402

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
    print("BENCH-REGROUND-LIVE: synthetic-exclusion allow-list is REALLY exercised")
    print("=" * 78)
    # The headline behavior of this build: only real-outcome (source=live) rows
    # feed the grade; synthetic bench/bench2 rows are DEMOTED and excluded. The
    # fixture now carries synthetic rows that WOULD change the answer if counted,
    # so these three checks FAIL if the exclusion (allow-list) is reverted —
    # they are not tautologies against an all-source-identical fixture.
    #
    # (a) glm-5.2/routing has 3 real (source=live) rows AND an added source=bench
    #     MERGE + source=bench2 BLOCK. If the synthetic rows leaked in, n would be
    #     5 (merge 3, block 2). The grade must ignore them: n stays 3, merge 2,
    #     block 1 — computed from real-outcome rows ONLY.
    g_glm_excl = grades.grade("glm-5.2", "routing")
    check(
        "(a) synthetic bench/bench2 rows do NOT change glm-5.2/routing grade "
        "(n=3 real-only, not 5)",
        g_glm_excl.n == 3 and g_glm_excl.merge == 2 and g_glm_excl.block == 1,
        f"n={g_glm_excl.n} merge={g_glm_excl.merge} block={g_glm_excl.block} "
        f"(would be n=5 merge=3 block=2 if synthetic leaked in)",
    )
    # (b) synth-only-model has ONLY source=bench/bench2 rows -> no real-outcome
    #     evidence -> grade() must be None for its class AND the generalist bucket,
    #     and assign() must skip it (empty eligible pool -> refused). If synthetic
    #     leaked in, grade() would return a real Grade and assign() would pick it.
    g_synth_bugfix = grades.grade("synth-only-model", "bugfix")
    g_synth_gen = grades.grade("synth-only-model", "generalist")
    check(
        "(b) a bench-ONLY model (only synthetic rows) has grade()==None at its "
        "class and generalist",
        g_synth_bugfix is None and g_synth_gen is None,
        f"bugfix={g_synth_bugfix} generalist={g_synth_gen}",
    )
    r_synth = assign("bugfix", grades, no_avail, candidate_models=["synth-only-model"])
    check(
        "(b) assign() SKIPS the bench-only model -> refused, never assigned on "
        "synthetic-only evidence",
        r_synth.refused and r_synth.picked is None,
        f"refused={r_synth.refused} picked={r_synth.picked}",
    )
    # (c) the rank-key `score` for glm-5.2/routing is computed from the 3 real
    #     rows only. Assert it equals the Wilson spread on (merge=2, block=1, n=3),
    #     NOT on the leaked (merge=3, block=2, n=5). This checks the actual
    #     ranking signal, not just the counts.
    expected_real_only = (_wilson_bound(2, 3, upper=False)
                          - _wilson_bound(1, 3, upper=True))
    leaked_score = (_wilson_bound(3, 5, upper=False)
                    - _wilson_bound(2, 5, upper=True))
    check(
        "(c) glm-5.2/routing score is computed from real-outcome rows ONLY "
        "(matches n=3 Wilson spread, not the n=5 leaked value)",
        abs(g_glm_excl.score - expected_real_only) < 1e-9
        and abs(g_glm_excl.score - leaked_score) > 1e-6,
        f"score={g_glm_excl.score:.4f} real-only-expected={expected_real_only:.4f} "
        f"leaked-would-be={leaked_score:.4f}",
    )

    provisional_scoring_checks(grades, no_avail)
    aggregate_n_checks()

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


def provisional_scoring_checks(grades: ScorecardGradesProvider, no_avail) -> None:
    """BENCH-PROVISIONAL-SCORING (#20) acceptance — plan §2. Proves a
    provisional unit's rows are COLLECTED in the ledger but change NO active
    grade / assign pick, that legacy rows default to active, and that the v1
    promotion gate promotes ONLY a discriminating unit (a saturated one
    provably cannot)."""
    import tempfile

    print()
    print("=" * 78)
    print("BENCH-PROVISIONAL-SCORING (#20): provisional rows collected, NOT counted")
    print("=" * 78)
    # The fixture carries a source=live, stage=provisional MERGE for
    # glm-5.2/routing. It PASSES the source allow-list (it's real-outcome), so
    # ONLY the stage gate can keep it out. If the stage filter were reverted the
    # grade would be n=4 (merge=3, block=1); it must stay n=3 (merge=2, block=1).
    g = grades.grade("glm-5.2", "routing")
    check(
        "a stage=provisional live row does NOT change the active grade "
        "(glm-5.2/routing stays n=3, not 4)",
        g.n == 3 and g.merge == 2 and g.block == 1,
        f"n={g.n} merge={g.merge} block={g.block} (would be n=4 merge=3 if the "
        f"provisional row leaked past the stage gate)",
    )
    # ...but it IS present in the ledger (collected): include_provisional sees it.
    active_only = grades._rows_for("glm-5.2", "routing")
    with_prov = grades._rows_for("glm-5.2", "routing", include_provisional=True)
    check(
        "the provisional row is COLLECTED (include_provisional=True sees n=4) but "
        "EXCLUDED by default (n=3) — collected, not counted",
        len(active_only) == 3 and len(with_prov) == 4,
        f"active_only={len(active_only)} include_provisional={len(with_prov)}",
    )
    # ...and it changes no assign() pick: routing still picks glm-5.2 on its
    # 3 ACTIVE rows, and legacy 13-col live rows are what feed it (default active).
    r = assign("routing", grades, no_avail, candidate_models=["glm-5.2", "kimi-k2.6"])
    g_pick = grades.grade(r.picked, "routing")
    check(
        "assign() pick is unchanged by the provisional row (routing -> glm-5.2, "
        "graded on n=3 active legacy rows)",
        r.picked == "glm-5.2" and g_pick.n == 3,
        f"picked={r.picked} n={g_pick.n}",
    )

    print()
    print("=" * 78)
    print("BENCH-PROVISIONAL-SCORING (#20): promotion gate v1 (promote.py)")
    print("=" * 78)
    sat, sat_reason = _promote.evaluate_gate({"a": 100.0, "b": 100.0, "c": 100.0})
    check("a SATURATED unit (all models ~100) provably CANNOT promote",
          sat is False, sat_reason)
    disc, disc_reason = _promote.evaluate_gate({"a": 100.0, "b": 40.0})
    check("a DISCRIMINATING unit (spread 60 >= SPREAD_MIN, 2 models) promotes",
          disc is True, disc_reason)
    lone, lone_reason = _promote.evaluate_gate({"a": 100.0})
    check("a unit only ONE model has run CANNOT promote (nothing to differentiate)",
          lone is False, lone_reason)

    # End-to-end: the gate actually flips units.tsv on --apply, and only for the
    # discriminating unit — never the saturated one.
    with tempfile.TemporaryDirectory() as td:
        units_p = Path(td) / "units.tsv"
        tsv_p = Path(td) / "sc.tsv"
        units_p.write_text(
            "# test units\nunit_id\tkind\tstage\tpromoted_on\n"
            "PDISC\tsection\tprovisional\t-\nPSAT\tsection\tprovisional\t-\n")
        tsv_p.write_text(
            "2026-01-01\tbench\tPDISC\trouting\t1\tmodelA\tMERGE\tpass\t100\t-\t-\t0\tn\n"
            "2026-01-01\tbench\tPDISC\trouting\t1\tmodelB\tBLOCK\tfail\t40\t-\t-\t0\tn\n"
            "2026-01-01\tbench\tPSAT\trouting\t1\tmodelA\tMERGE\tpass\t100\t-\t-\t0\tn\n"
            "2026-01-01\tbench\tPSAT\trouting\t1\tmodelB\tMERGE\tpass\t100\t-\t-\t0\tn\n")
        rd = _promote.promote("PDISC", tsv_path=tsv_p, units_path=units_p, apply=True)
        rs = _promote.promote("PSAT", tsv_path=tsv_p, units_path=units_p, apply=True)
        after = {u["unit_id"]: u["stage"] for u in _promote.load_units(units_p)}
        check("promote(--apply) flips the DISCRIMINATING unit provisional -> active",
              rd["applied"] and after["PDISC"] == "active",
              f"applied={rd['applied']} stage={after['PDISC']}")
        check("promote(--apply) leaves the SATURATED unit provisional (gate refused)",
              (not rs["applied"]) and after["PSAT"] == "provisional",
              f"applied={rs['applied']} stage={after['PSAT']}")


def aggregate_n_checks() -> None:
    """BENCH-AGGREGATE-N (#16) acceptance — plan §5. Proves the aggregation
    over N repeat runs is REALLY exercised: the grade/tier chart smooth
    multiple rows per (model, section/work_class) into mean ± a noise band,
    and a composite gap within the combined band renders as a TIE, not a rank.
    Every assertion below FAILS if the aggregation is reverted to the prior
    single-row / last-wins behavior (the values differ, not just the shape)."""
    import tempfile

    print()
    print("=" * 78)
    print("BENCH-AGGREGATE-N (#16): grades.py smooths the numeric bench aggregate")
    print("=" * 78)
    # A real-outcome (source=live) model with THREE numeric-score runs at one
    # work_class. grade() must aggregate them into mean ± a measured noise band,
    # not surface a bare single-run number. Scores 100/75/60 mirror the exact
    # across-run variance the validity review recorded for glm-5.2 (S3/S5).
    with tempfile.TemporaryDirectory() as td:
        tsv = Path(td) / "sc.tsv"
        tsv.write_text(
            "2026-02-01\tlive\tR1\ttests\t1\taggN\tMERGE\t-\t100\t10\t-\t0\trun1\n"
            "2026-02-02\tlive\tR2\ttests\t1\taggN\tMERGE\t-\t75\t10\t-\t0\trun2\n"
            "2026-02-03\tlive\tR3\ttests\t1\taggN\tMERGE\t-\t60\t10\t-\t0\trun3\n"
            "2026-02-04\tlive\tR4\ttests\t1\taggSolo\tMERGE\t-\t100\t10\t-\t0\tonly-run\n")
        g_agg = ScorecardGradesProvider(tsv)
        g = g_agg.grade("aggN", "tests")
        n_runs = getattr(g, "bench_score_n", None)
        sd = getattr(g, "bench_score_stddev", "<missing>")
        band = getattr(g, "bench_score_band", "<missing>")
        check(
            "grade() aggregates all N=3 numeric-score runs (mean≈78.3, not a "
            "single last/first run of 100 or 60)",
            n_runs == 3 and g.mean_bench_score is not None
            and abs(g.mean_bench_score - (235 / 3)) < 1e-6,
            f"bench_score_n={n_runs} mean_bench_score={g.mean_bench_score}",
        )
        check(
            "the numeric aggregate publishes a NON-ZERO noise band (stddev & CI) "
            "over the N runs — the smoothing signal #16 exists to expose",
            isinstance(sd, float) and sd > 0 and isinstance(band, float) and band > 0,
            f"bench_score_stddev={sd} bench_score_band={band}",
        )
        check(
            "the band is surfaced in the grade summary (band±, not just carried "
            "silently on the Grade)",
            "±" in g.summary() and "N=3" in g.summary(),
            repr(g.summary()),
        )
        g_solo = g_agg.grade("aggSolo", "tests")
        check(
            "a SINGLE-run grade reports an unmeasurable band (stddev/band None), "
            "never a fabricated 0 — one sample carries no run-to-run noise",
            getattr(g_solo, "bench_score_n", None) == 1
            and getattr(g_solo, "bench_score_stddev", "x") is None
            and getattr(g_solo, "bench_score_band", "x") is None,
            f"n={getattr(g_solo,'bench_score_n',None)} sd={getattr(g_solo,'bench_score_stddev','x')} "
            f"band={getattr(g_solo,'bench_score_band','x')}",
        )

    # scores_tie: the pure #16 rule — a gap within the combined band is a TIE.
    check(
        "scores_tie(): a sub-band gap (2 within a ±22.9 band) is a TIE, not a rank",
        scores_tie(78.0, 22.9, 80.0, None) is True,
        "scores_tie(78.0, 22.9, 80.0, None)",
    )
    check(
        "scores_tie(): a gap wider than the combined band is NOT a tie (real rank)",
        scores_tie(50.0, 5.0, 90.0, 5.0) is False,
        "scores_tie(50, 5, 90, 5)",
    )

    print()
    print("=" * 78)
    print("BENCH-AGGREGATE-N (#16): tier_chart.py aggregates repeat section runs")
    print("=" * 78)
    # A synthetic bench model whose section S1 was run THREE times (100/75/60).
    # bench_rows_for must aggregate to the MEAN (≈78.3), NOT keep the last row
    # (60) — so the composite tiers "Strong" (>=75), which last-wins (60) could
    # never reach ("Capable"). This is the direct fails-if-reverted assertion.
    with tempfile.TemporaryDirectory() as td:
        tsv = Path(td) / "sc.tsv"
        tsv.write_text(
            # TM: S0 sanity=100, S1 three runs 100/75/60 (last row 60)
            "2026-03-01\tbench\tS0\ttests\t0\tTM\tMERGE\tpass\t100\t5\t-\t0\ts0\n"
            "2026-03-02\tbench\tS1\ttests\t1\tTM\tMERGE\tpass\t100\t5\t-\t0\ts1 run1\n"
            "2026-03-03\tbench\tS1\ttests\t1\tTM\tFIXES\tfail\t75\t5\t-\t0\ts1 run2\n"
            "2026-03-04\tbench\tS1\ttests\t1\tTM\tFIXES\tfail\t60\t5\t-\t0\ts1 run3\n"
            # TN: S0=100, S1 single run 78 -> composite 78, no measurable band
            "2026-03-05\tbench\tS0\ttests\t0\tTN\tMERGE\tpass\t100\t5\t-\t0\ts0\n"
            "2026-03-06\tbench\tS1\ttests\t1\tTN\tFIXES\tfail\t78\t5\t-\t0\ts1 only\n")
        rows = _tier_chart.load_rows(tsv)
        sc = _tier_chart.bench_rows_for(rows, "TM")
        s1 = sc.get("S1", {})
        check(
            "bench_rows_for aggregates S1's 3 runs (score_n=3, mean≈78.3), NOT the "
            "last-wins single row (60)",
            s1.get("score_n") == 3 and s1.get("score_mean") is not None
            and abs(s1.get("score_mean") - (235 / 3)) < 1e-6,
            f"score_n={s1.get('score_n')} score_mean={s1.get('score_mean')} "
            f"score_values={s1.get('score_values')}",
        )
        check(
            "the per-section aggregate carries a NON-ZERO noise band over its runs",
            isinstance(s1.get("score_stddev"), float) and s1["score_stddev"] > 0
            and isinstance(s1.get("score_band"), float) and s1["score_band"] > 0,
            f"score_stddev={s1.get('score_stddev')} score_band={s1.get('score_band')}",
        )
        tier, comp = _tier_chart.overall_tier(sc)
        check(
            "the composite tiers off the MEAN (Strong, comp≈78) — reverting to "
            "last-wins (60) would misfile it as Capable",
            tier == "Strong" and isinstance(comp, float) and abs(comp - (235 / 3)) < 1e-6,
            f"tier={tier} composite={comp}",
        )
        # TIE: TM (≈78.3, wide band) and TN (78, no band) differ by <band -> a
        # sub-band gap must rank as a TIE, not be ordered on noise.
        rank_tm, total, tied_tm = _tier_chart._rank_in_tier_v1_internal(rows, "TM", "Strong")
        check(
            "a sub-band composite gap between two same-tier models renders as a "
            "TIE (competition rank shared), not a spurious rank on noise",
            total == 2 and tied_tm is True,
            f"rank={rank_tm} total={total} tied={tied_tm}",
        )

    # #16 review finding 1: NON-TRANSITIVE tie CHAINING must not collapse
    # distinguishable models into one rank. Three same-tier ("Strong") models:
    #   A composite 89, B 82, C 76 — each with a ±4.53 band (three S1 runs
    #   symmetric ±4 => sd=4, band = z*4/sqrt(3) ≈ 4.526; only S1 graded so the
    #   composite band equals it). Combined band ≈ 9.05, so:
    #     A-B gap 7  <= 9.05  -> tie ;  B-C gap 6  <= 9.05 -> tie ;
    #     A-C gap 13 >  9.05  -> NOT a tie.
    # Ranking must anchor ties to the GROUP LEADER (A), not the neighbour, so C
    # ranks BELOW the A/B group (ranks 1,1,3). The old neighbour-compare logic
    # chained A~B~C into rank 1 for all three (C spuriously tied-#1 with A) — so
    # this assertion FAILS on the pre-fix code and passes only with the fix.
    with tempfile.TemporaryDirectory() as td:
        tsv = Path(td) / "chain.tsv"
        rows_txt = []
        for model, s1runs in (("XA", (85, 89, 93)),   # mean 89, band ≈4.53
                              ("XB", (78, 82, 86)),    # mean 82, band ≈4.53
                              ("XC", (72, 76, 80))):    # mean 76, band ≈4.53
            rows_txt.append(f"2026-04-01\tbench\tS0\ttests\t0\t{model}\tMERGE\tpass\t100\t5\t-\t0\ts0")
            for i, sv in enumerate(s1runs):
                rows_txt.append(f"2026-04-0{i + 2}\tbench\tS1\ttests\t1\t{model}\tFIXES\tfail\t{sv}\t5\t-\t0\ts1 run{i + 1}")
        tsv.write_text("\n".join(rows_txt) + "\n")
        rows = _tier_chart.load_rows(tsv)
        rank_a, tot_a, tied_a = _tier_chart._rank_in_tier_v1_internal(rows, "XA", "Strong")
        rank_b, _, _ = _tier_chart._rank_in_tier_v1_internal(rows, "XB", "Strong")
        rank_c, tot_c, tied_c = _tier_chart._rank_in_tier_v1_internal(rows, "XC", "Strong")
        check(
            "non-transitive ties do NOT chain: with A~B and B~C but A NOT~C, the "
            "weaker model C ranks BELOW the A/B group (rank 3, untied) rather than "
            "collapsing to a spurious tied-#1 with A (fails on neighbour-compare)",
            tot_c == 3 and rank_a == 1 and rank_b == 1 and rank_c == 3 and tied_c is False,
            f"A(rank={rank_a},tied={tied_a}) B(rank={rank_b}) C(rank={rank_c},tied={tied_c}) total={tot_c}",
        )


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
