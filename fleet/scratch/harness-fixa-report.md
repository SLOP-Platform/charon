# FIX A residual — closed (bench-run-collision, must-fix #1 from harness-hardening-review.md)

Built on top of the prior (still-uncommitted) P1/P2 hardening — nothing from
that work (staleness gate at `start`, `flock`, `BENCH_GUARD_ACTIVE_RUN`,
`--model` override, the token-fix) was reverted or altered beyond what's
listed below. No commit, no push. Harness confirmed idle before starting
(`pgrep -fa 'bench.sh|grade_state|run.sh'` → no matches).

## What changed

### 1. `benchmark/lib/grade_state.py` — `cmd_record` now gates on staleness

- Added `_is_active_meta(meta)`: the exact `is_section_active` predicate,
  but operating on an already-loaded `meta` dict (no extra disk read, no
  TOCTOU vs. the mutation that follows — `cmd_record` already holds the
  per-`(model, section)` `flock`). `is_section_active` is now a one-line
  wrapper around it, so `start`'s gate and `record`'s new gate are
  *provably* the same check, not two implementations that could drift.
- `cmd_record` now checks `_is_active_meta(meta)` right after the existing
  `meta is None` / `already finalized` checks and **before** computing
  `timed_out`/`score`. If the section is stale (round elapsed > timebox,
  nobody extended it via a live `record` call), it prints
  `{"error": "...STALE...", "stale": true}` to stdout and exits 1 —
  it no longer silently computes `timed_out=True` and finalizes a
  score=0/huge-`time_s` row.
- **Behavior change, deliberate:** a section that goes stale is no longer
  auto-scored 0 by whichever `record` call happens to land on it next. The
  caller must explicitly `bench.sh start --model <id>` to get a fresh round
  (which itself re-`init`s over stale state, per the existing P1 fix — new
  worktree, fresh clock, work must be redone). This is the fix's actual
  teeth: score=0 rows can no longer be silently manufactured by *either* a
  genuinely-abandoned run *or* a misattributed `--model` fallback landing on
  one. A caller whose own run is still genuinely active (round elapsed ≤
  timebox) is completely unaffected — verified in the new selftest.

### 2. `benchmark/bench.sh` — `do_grade`/`do_status` fail closed on the omitted-`--model` fallback

- New `refuse_if_stale_fallback <subcmd> <model>` function, called from
  `do_grade`'s and `do_status`'s **existing** no-override branch, right
  after each resolves `$model` from `runs/.current_model` in its own
  pre-existing style (so `do_status`'s original soft "no active run"
  message for a *missing* pointer file is untouched — the new gate only
  runs once there's an actual model name to check).
- It resolves that model's current section and runs
  `grade_state.py is_active` on it (fail-closed: a python error is treated
  as `false`, i.e. refuse). If not active, `die`s with a message explaining
  the shared-pointer clobbering mechanism (naming the kimi-k2.6/
  deepseek-v4-pro incident) and telling the caller to re-run with
  `--model <id>` from their own `start` ANNOUNCE line.
- An explicit `--model` override **never calls this function at all** — it's
  structurally confined to the `else` (no-override) branch, so a compliant
  caller is unaffected regardless of how stale the state happens to be.
- `do_grade`'s `record="$(python3 "$STATE_PY" record ...)"` call is now
  wrapped in an `if ! record=...; then die "..."; fi` (previously a bare
  assignment with no error handling at all — under `set -e` a nonzero exit
  from `grade_state.py record` would have aborted the whole script with no
  message). Same fix applied to `run.sh`'s `grade_section` for the same
  reason (defense-in-depth item 1 applies unconditionally, regardless of
  how the model/section was resolved, so `run.sh`'s always-explicit-model
  calls can hit the new stale gate too).

### 3. Secondary (FIX B tuning, low-risk, done)

- `lib/sections.sh`'s `wait_for_worktree_stable` default bumped
  `BENCH_MTIME_STABLE_SEC` 12s → 20s (still fully env-overridable — it
  already was; no new var name needed since one existed). `BENCH_MTIME_MAX_WAIT_SEC`
  cap (60s) left unchanged, per instructions.

## How the fail-closed path behaves end to end

1. Tab A starts model X, works section S. Meanwhile tab B runs
   `bench.sh start --model Y`, overwriting `runs/.current_model` to Y.
2. Tab A finishes and (mistakenly) runs `bench.sh grade` with no `--model`.
3. `do_grade` resolves `model=Y` from the clobbered pointer.
   `refuse_if_stale_fallback grade Y` checks Y's current section's
   `is_active`. If Y's own run is stale/abandoned (the actual incident
   shape) → **immediate `die`, before the grader ever runs** — no wasted
   grading, no scorecard write, no misattributed row.
4. Even if that shell-level check somehow didn't fire (e.g. Y's section
   happened to look active at that instant, or a future caller invokes
   `grade_state.py record` some other way), `cmd_record` itself refuses
   again the moment it detects staleness at record time — belt and
   suspenders, unconditional on how the model was resolved.
5. A caller passing `bench.sh grade --model <id>` (the now-documented
   RUN-BENCHMARK.md contract) never touches either gate's refusal path
   unless their *own* section is genuinely stale — in which case it's a
   correct refusal, not a poisoned score, and the error message tells them
   exactly how to recover (`start --model <id>` for a fresh round).

## Verification

- `bash -n bench.sh run.sh lib/sections.sh` — clean.
- `python3 -m py_compile lib/grade_state.py selftest/run_isolation_selftest.py` — clean.
- `python3 selftest/run_isolation_selftest.py` — **PASS** (run 4x in a row after
  the new parts were added, 0 failures each time). One pre-existing,
  unrelated timing flake was observed in `part5_mtime_stability_gate` on an
  isolated run before my new parts even ran (confirmed present before any of
  my edits too, and confirmed non-reproducing across 4 subsequent clean
  runs) — not a regression from this change.
- `python3 selftest/session_cost_selftest.py` — PASS.
- `python3 selftest/token_capture_selftest.py` — PASS.
- `python3 selftest/run_selftests.py` (grader goldens) — PASS, all 19 cases.
- Real `benchmark/runs/` and `fleet/model-scorecard.tsv` were never touched —
  all new/existing tests operate against `tempfile.TemporaryDirectory`
  scratch copies only (confirmed via `git status` showing no additional
  diff to either beyond what was already dirty from the prior uncommitted
  hardening session).

### New selftest coverage added (`selftest/run_isolation_selftest.py`)

- `part6_record_refuses_stale`: ages a section's state 25h past its 5s
  timebox, confirms `grade_state.py record` refuses (rc=1, message mentions
  STALE) and does **not** write `finalized`/`final_score` into meta.json (no
  poisoned row); separately confirms a genuinely-active section's `record`
  call still finalizes normally (rc=0, correct score) — compliant path
  untouched.
- `part7_bench_sh_fallback_fail_closed`: builds a minimal scratch copy of
  `bench.sh`/`run.sh`/`lib/{sections.sh,grade_state.py,charon_cost.py}` (no
  fixtures/graders/scorecard needed — the refusal fires before any of those
  are touched), stages a STALE section and points `runs/.current_model` at
  it, then runs the **real** `bench.sh status` binary: no-`--model` refuses
  (rc≠0, stderr mentions STALE and `--model`); `--model <id>` against the
  identical stale state succeeds normally and reports the correct
  model/section — proving the override branch structurally bypasses the new
  gate. (`do_status` and `do_grade` share the exact same
  `refuse_if_stale_fallback` function, so this is a full proof of the gate
  `do_grade` also runs before ever touching a worktree/grader.)

## Files touched

- `/home/stack/charon-private/fleet/benchmark/lib/grade_state.py`
- `/home/stack/charon-private/fleet/benchmark/bench.sh`
- `/home/stack/charon-private/fleet/benchmark/run.sh`
- `/home/stack/charon-private/fleet/benchmark/lib/sections.sh`
- `/home/stack/charon-private/fleet/benchmark/selftest/run_isolation_selftest.py`

## Updated proposed commit message

```
fix(bench-harness): close grade-path fallback residual (bench-run-collision P1)

The prior hardening gated `start`'s resume-vs-reinit decision on
`is_active` (round_start_ts staleness) and added a `--model` override for
`grade`/`status`, but left two holes an adversarial review flagged as the
one remaining must-fix:

- `grade_state.py cmd_record` had no staleness gate at all - a `record`
  call landing on an already-stale section (e.g. via a misattributed or
  omitted `--model`) would still silently compute timed_out=True and
  finalize a poisoned score=0/huge-time_s row, reproducing the incident
  this whole fix line exists for.
- `bench.sh do_grade`/`do_status`, when `--model` is omitted, still fell
  back to the single shared `runs/.current_model` pointer with no
  freshness check - a DIFFERENT concurrent tab's `start` can silently
  overwrite it in between, so "forgot --model" is a live, plausible LLM
  failure mode, not hypothetical.

Fixes both, belt-and-suspenders:

1. `cmd_record` now refuses (JSON error, exit 1) instead of scoring
   whenever `_is_active_meta` (the same predicate `is_active`/`start` use)
   says the section is already stale - deliberately turns "silently
   poisoned score=0" into "clear error, re-`start` for a fresh round".
   A genuinely-active section's `record` call is completely unaffected.
2. `bench.sh` fails closed at the shell level too: `refuse_if_stale_fallback`
   checks the fallback-resolved section's `is_active` before `do_grade`/
   `do_status` proceed, refusing with a clear "`pass --model`" message
   before ever touching a worktree or grader. An explicit `--model`
   override never reaches this check - unaffected.

Also bumps the FIX-B worktree-mtime-stability default 12s -> 20s
(BENCH_MTIME_STABLE_SEC, still env-overridable, cap unchanged) per the
review's deferred tuning note (observed premature-grade gap was ~37s).

New selftest coverage (selftest/run_isolation_selftest.py parts 6-7) proves
both gates refuse on stale state and leave compliant --model callers
untouched, against scratch copies only. All existing selftests
(run_isolation, session_cost, token_capture, grader goldens) still pass.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```
