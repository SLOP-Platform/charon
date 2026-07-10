# Adversarial review — benchmark harness hardening (bench-run-collision P1 / bench-premature-grade P2 / chart dedup)

Date: 2026-07-06. Read-only. Diffs reviewed: `benchmark/{bench.sh,run.sh,lib/sections.sh,lib/grade_state.py,RUN-BENCHMARK.md,README.md}` + new `selftest/run_isolation_selftest.py`. Ran the new selftest (temp-dir only) — **PASS, exit 0**. Token-fix (`charon_cost.snapshot_usage`/`int_delta_str`, grade_state token capture, bench.sh token env, scorecard cols 14/15) is present and preserved.

## FIX A — run-collision (P1) — PARTIAL (substantially mitigated; fallback not fail-closed)

The real poison mechanism is closed for a COMPLIANT caller:
- Staleness: `is_section_active` = `now - round_start_ts <= timebox`; bench.sh `section_in_progress` gates on it, so start/prepare no longer resumes a ~25h-abandoned `start_ts` — it re-`init`s fresh (rm -rf worktree, new start_ts/round_start_ts, attempts=0). This is the direct fix for the observed 25.5h/score=0 incident. Verified by selftest part1.
- `--model` override on grade/status bypasses the shared `.current_model` entirely; RUN-BENCHMARK.md now mandates it on every call.
- `flock` + opt-in `BENCH_GUARD_ACTIVE_RUN=1` are real defense-in-depth (selftest parts 2/4 exercise both).

Per attack:
- **(a) model omits `--model` → clobberable `.current_model` fallback → collide again: STILL A HOLE (the load-bearing residual).** `do_grade`/`do_status` still fall back to the single global `runs/.current_model` file, and the grade path has NO staleness gate — `cmd_record` finalizes any non-finalized state and computes `timed_out` unconditionally. So if an LLM forgets `--model` AND a concurrent tab overwrote `.current_model`, grade lands on the wrong model's section and can STILL emit exactly the poisoned score=0/huge-time_s row this ticket is about. The only guard is instructional (RUN-BENCHMARK.md). The driver is an LLM, so "forgets the flag" is a live failure mode, not hypothetical.
- **(b) two tabs think they're different models → shared worktree: NON-ISSUE.** Different model ids ⇒ different `runs/<model>/<section>/` dirs ⇒ no worktree sharing; flock isn't even needed. (The genuinely dangerous inverse — two *different* models both detected as the *same* id — would collide, but that's an upstream detect_model.py problem the flock also can't solve; out of scope here.)
- **(c) staleness-reinit wipes a legitimately-slow active run: LOW RISK.** Wipe only fires when `is_active=false` (round past its timebox) AND someone re-runs `start`. A past-timebox round scores 0 via cmd_record anyway, so nothing recoverable is lost; and bench.sh auto-advances (models don't re-`start` mid-work). Minor edge, acceptable.
- **(d) round_start_ts reset each round → never times out: BOUNDED, CLOSED.** Reset is capped by `CORRECTIONS_CAP=3`; after 3 rounds it finalizes `min(score,89)`. A single slow round IS still caught (next `record` sees `round_elapsed > timebox`). Total budget widens to ~3×timebox by design — that's the intended fix, `time_s` still reports true total. Selftest part3 exercises it.
- **(e) run.sh/run-many.sh don't set the guard: MINOR GAP, documented.** Preserves their always-reset PREPARE contract; but a run.sh batch run concurrent with a live bench.sh tab on the same model can still clobber it (flock serializes the write but doesn't refuse). Acceptable for the "batch, not concurrent-with-tabs" usage; worth a one-line doc caveat.

## FIX B — premature-grade (P2) — CLOSED with caveat

- `wait_for_worktree_stable` (12s stable, 60s cap) wired into BOTH bench.sh and run.sh grade paths. Selftest part5 genuinely exercises all three cases (already-stable returns fast, fresh-write waits ~stable_for, continuous-touch hits the cap with warning).
- **Inert never-written worktree → NO 60s hang.** Fixture files are tar-copied at prepare time so their mtime already pre-dates grading (returns immediately); an empty worktree returns immediately (`newest` empty). Only a *continuously-touched* dir hits the cap. Good.
- **12s vs observed ~37s: heuristic, residual window.** If settling is continuous writes (gaps <12s) the gate correctly waits it out (up to 60s cap) — fine. But a lone late flush arriving after a >12s quiet gap would be graded early and missed. The "37s" in reds is the manual re-grade delay, not a proven write-burst length, so 12s is probably adequate — but it's a tuned constant, not a proof. Consider raising the default toward the observed value or documenting the residual.
- Race between wait-return and grader read: negligible (a later write only adds content; not a scoring-correctness hole).

## FIX C — chart dedup — CLOSED (advisory)

Wording fix only, which is correct — there was no code duplication (bench.sh auto-prints once via tier_chart.py). RUN-BENCHMARK.md step 6 now forbids hand-rendering and points at `bench.sh chart <id>` as the sole reprint; README marks it the ONLY render site. Can't technically *prevent* an LLM re-typing it, but the ticket ("minimax printed it 3×") was an instruction problem and this is the right lever.

## Regressions — none found

- run.sh sources lib/sections.sh (line 52) so `wait_for_worktree_stable` resolves; bench.sh sources it too (64). run-many.sh unchanged (thin PREPARE loop). Contracts intact.
- Token-fix preserved: charon_cost has `snapshot_usage`/`int_delta_str`; grade_state stores tokens_in/out_start + final_tokens_in/out and emits them; bench.sh passes `CHARON_SCORECARD_TOKENS_{IN,OUT}` env; scorecard appends trailing cols 14/15 with validation, defaulting "-". Backward-compat argument (tier_chart reads cols[:13], render uses $1-$12) holds.
- Selftest is NON-trivial: real subprocess invocations, real fcntl contention, real 2s sleep for round-timeout, real background toucher for the cap. Exercises the claims, not trivial asserts.

## VERDICT: SHIP-WITH-FIXES

Core P1/P2 mechanisms are sound, tested, and regression-free. One residual directly re-enables the exact P1 under a plausible LLM mistake.

### Must-fix before landing
1. **Close the grade-path fallback (FIX A residual (a)).** Cheapest belt-and-suspenders: gate `cmd_record` (or `do_grade`) with the same `is_active` staleness check so a misattributed grade on stale state CANNOT silently emit a score=0/huge-time_s row — refuse/warn instead. Optionally make the no-`--model` fallback fail-closed (per-tab/PID pointer, or loud warn when `.current_model` mtime looks contended). This is the one hole that reproduces the original incident if the LLM omits the flag.

### Defer (land-then-improve)
2. Tune/justify the 12s stability constant vs the observed ~37s (raise default or document the lone-late-write residual).
3. One-line doc caveat: don't run run.sh/run-many.sh concurrently with a live bench.sh tab on the same model (guard intentionally off there).
4. Note the (c) edge: re-running `start` on a slow past-timebox section rm -rf's its worktree.
