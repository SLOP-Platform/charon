# Benchmark harness hardening report (bench-run-collision / bench-premature-grade / chart dedup)

Date: 2026-07-06. Code-only pass against `fleet/benchmark/` (+ `fleet/model-scorecard.sh`,
`fleet/benchmark/RUN-BENCHMARK.md`). No commit, no push. `model-scorecard.tsv` data rows and
everything under `benchmark/runs/` were NOT touched (separate data-cleanup pass owns those).

STEP 0 safety gate: `pgrep -fa 'bench.sh|grade_state|run.sh'` returned nothing (only my own
shell-snapshot wrapper matched the regex, not a real bench/run process) both before and after
the edit pass — harness was idle throughout. Confirmed real `benchmark/runs/` tree's newest
file was already ~20 min old before I started (leftover from a finished run, unrelated to me)
and remained untouched afterward (all testing ran against `tempfile.TemporaryDirectory` scratch
copies, never the real tree).

Preserved as required: the uncommitted TOKEN-CAPTURE fix already in the tree
(`charon_cost.py::snapshot_usage()`, `grade_state.py` token capture, `bench.sh` token env vars,
`model-scorecard.sh` trailing cols 14/15, `selftest/token_capture_selftest.py`) — not reverted,
not touched further; re-ran its selftest at the end to confirm it's still green.

## Files changed

- `benchmark/lib/grade_state.py` — core fix (locking, staleness/`is_active`, round-based timeout).
- `benchmark/bench.sh` — wires the above in, adds `--model` override to `grade`/`status`, adds
  the mtime-stability wait before grading.
- `benchmark/lib/sections.sh` — new shared `wait_for_worktree_stable()` (used by both bench.sh
  and run.sh).
- `benchmark/run.sh` — one-line wire-up of the same mtime-stability wait (shares state/grading
  path with bench.sh; left its PREPARE-mode always-reset contract untouched).
- `benchmark/RUN-BENCHMARK.md` — self-drive instructions updated: explicit `--model` on every
  call, no hand-rendering the final chart.
- `benchmark/README.md` — subcommand docs updated to match (light touch, for consistency).
- `benchmark/selftest/run_isolation_selftest.py` — new selftest (see Verification).

## FIX A — bench-run-collision (P1)

**Root cause, confirmed by re-reading the code plus the real contaminated `deepseek-v4-pro` rows
in `model-scorecard.tsv` (all `score=0`, `time_s≈91700s`≈25.5h, exactly matching reds.tsv):**
`bench.sh do_grade`/`do_status` resolved "which model am I" purely from a single GLOBAL file
(`runs/.current_model`), written unconditionally by `do_start`. Any concurrent `bench.sh start`
call from a *different* opencode tab (a normal fleet pattern — multiple tabs benchmarking
different models at once) silently overwrote that file mid-run. A subsequent `grade` call in the
*original* tab then read back the wrong model, resumed *that* model's on-disk state — which,
separately, had no staleness check at all (`section_in_progress` was a bare file-existence test)
— and inherited its ~25h-old abandoned `start_ts`, forcing `timed_out=True, score=0` on every
section via the existing timeout path.

Two independent bugs compounded: (1) unguarded cross-tab identity clobber via one shared mutable
file, (2) no distinction between "genuinely in-flight" and "abandoned" state before resuming it.

**Fix, in `lib/grade_state.py`:**
- `is_section_active(model, section)` / `is_active` subcommand: a section is ACTIVE only while
  `now - round_start_ts <= timebox_sec` (see below for `round_start_ts`) and not yet finalized;
  otherwise it's STALE. `bench.sh`'s `section_in_progress` now calls this instead of a bare
  file-existence check — a stale section falls through to the fresh-`init` path (new worktree,
  new `start_ts`/`round_start_ts`, `attempts=0`) instead of being silently resumed. This is the
  direct fix for the observed incident.
- `exclusive_lock(model, section)`: a non-blocking `flock` on `<state_dir>/.lock`, held for the
  duration of a single `init`/`record` call. Fails fast with a clear stderr message if another
  process holds it right now — defense-in-depth against a genuinely simultaneous double
  invocation (e.g. the TOCTOU window between bench.sh's `is_active` check and its `init` call).
- `cmd_init` additionally refuses to clobber a genuinely ACTIVE (not stale) section when the
  caller opts in via `BENCH_GUARD_ACTIVE_RUN=1` — `bench.sh` sets this; `run.sh`/`run-many.sh`
  deliberately do **not**, so their existing always-reset PREPARE-mode contract is unchanged.
- `bench.sh do_grade`/`do_status` gained an explicit `--model <id>` override (mirroring
  `do_start`'s existing one). `RUN-BENCHMARK.md` now instructs the agent to capture the model id
  from `start`'s own ANNOUNCE line and pass it back explicitly on every subsequent call — a
  self-report captured at run start, per the ticket's own suggested remedy — eliminating reliance
  on the shared file entirely for anyone who uses it. The shared-file fallback still exists
  unchanged for legacy single-tab/manual use.
- Timeout: `cmd_record`'s timeout decision is now judged against `round_start_ts` (reset at the
  top of every NEW correction round), not the cumulative `elapsed` from the section's original
  `start_ts` — a model spread across 2-3 legitimate correction rounds is no longer false-zeroed
  just because their sum exceeds one round's `timebox_sec`. The ledger's reported `time_s` is
  still the total elapsed from the original `start_ts` (unchanged audit semantics).

## FIX B — bench-premature-grade (P2)

Added `wait_for_worktree_stable()` to `lib/sections.sh` (shared by both drivers): blocks until
the worktree's newest file mtime has been unchanged for `BENCH_MTIME_STABLE_SEC` seconds
(default 12s), capped at `BENCH_MTIME_MAX_WAIT_SEC` total wait (default 60s) so a continuously-
touched worktree (e.g. a leftover watch/build process) can't hang the run forever — it grades
anyway past the cap, with a clear stderr warning. Wired in immediately before the grader
invocation in both `bench.sh do_grade` and `run.sh grade_section`.

## FIX C — inconsistent/duplicate final chart (cosmetic)

The chart is already script-emitted exactly once by `bench.sh`'s auto-print (`lib/tier_chart.py`
via `bench.sh chart`) the instant the last section finalizes — there was no code duplication bug
here; the duplication was the *model in the tab* re-rendering its own copy in its final message,
per the ticket ("minimax-m3 printed it 3×"). Fixed by rewording `RUN-BENCHMARK.md` step 6 to
explicitly forbid hand-rendering/reconstructing the chart and require pasting `bench.sh`'s own
printed output verbatim, pointing at `bench.sh chart <id>` as the single canonical reprint path
if ever needed. `README.md` updated to match.

## Verification

- `bash -n` on all edited/touched shell: `bench.sh`, `run.sh`, `run-many.sh` (unedited, checked
  for safety), `lib/sections.sh` — all OK.
- `python3 -m py_compile` on all edited/touched Python: `lib/grade_state.py`, `lib/charon_cost.py`
  (unedited by me, compiled to confirm the preserved token-fix still compiles),
  `lib/detect_model.py` (unedited), `lib/tier_chart.py` (unedited), all `selftest/*.py` — all OK.
- Existing selftests, run after all edits — **all still PASS, no regressions**:
  - `selftest/run_selftests.py` (all 20 grader golden/adversarial cases) — PASS.
  - `selftest/session_cost_selftest.py` — PASS.
  - `selftest/token_capture_selftest.py` (the preserved token-fix's own selftest) — PASS.
- New `selftest/run_isolation_selftest.py` (entirely against `tempfile.TemporaryDirectory` scratch
  copies of `lib/grade_state.py`/`lib/charon_cost.py` — never the real `runs/` tree) — **PASS**,
  proving:
  1. `init` always stamps a fresh `start_ts`==`round_start_ts`.
  2. `is_active` correctly flags a freshly-init'd section as active and a hand-aged
     (simulated 25h-old, mirroring the real incident) one as stale; re-`init` over the stale one
     stamps a brand-new fresh `start_ts` and resets `attempts` to 0.
  3. `BENCH_GUARD_ACTIVE_RUN=1` refuses to clobber a genuinely active section but allows
     reclaiming a stale one.
  4. `record`'s timeout is judged per-correction-round (a round 2s into a fresh 3s round budget,
     after round 1 already used most of a prior 3s window, is correctly NOT timed out).
  5. A per-`(model,section)` `flock` makes a concurrent `init`/`record` fail fast with a clear
     lock-related stderr message while another process holds it, and succeeds once released.
  6. `wait_for_worktree_stable` returns immediately on an already-stable worktree, waits out a
     fresh write, and respects its max-wait cap against a continuously-touched directory (never
     hangs).
- Backward-compat with existing scorecard rows: ran `tier_chart.py` against the REAL
  `model-scorecard.tsv` (read-only) — renders without error, correctly reproduces the known-bad
  `deepseek-v4-pro` row as `INVALID` (S0 not clean) with the same contaminated
  `time_s≈91700s`/`score=0` figures reds.tsv describes — confirms the historical data reads back
  identically (no schema/format change was made to the TSV or its readers) and that these are
  exactly the rows flagged `DISCARD` for the separate data-cleanup pass.

## Scope check

`git status`/`git diff --stat` confirms only the intended files changed:
`benchmark/{README.md,RUN-BENCHMARK.md,bench.sh,run.sh,lib/sections.sh,lib/grade_state.py}` plus
the new `benchmark/selftest/run_isolation_selftest.py`. `model-scorecard.tsv`, `reds.tsv`,
`model-scorecard.sh`, `board/*.parked`, `validate_board.sh`, and everything under `benchmark/runs/`
show only the SAME pre-existing uncommitted diffs that were present before this session started
(token-fix + bench-run-collision/bench-premature-grade red entries) — nothing new added to any of
them by this pass.

## Proposed commit message

```
fix(benchmark): harden harness against run-collision + premature-grade races

bench-run-collision (P1): bench.sh's `grade`/`status` resolved "which
model" from a single file shared by every concurrent tab, and resumed
any existing state with no staleness check - a different tab's `start`
could silently overwrite that pointer, and a genuinely abandoned
section's ~25h-old start_ts would then poison a new run into a
false score=0 timeout on every section (see fleet/reds.tsv). Fix:
grade_state.py now distinguishes ACTIVE (within its current
correction round's timebox) from STALE state before resuming it,
resetting to a fresh start_ts/round_start_ts instead of inheriting a
poisoned clock; a per-(model,section) flock + opt-in active-run guard
add defense-in-depth against genuinely simultaneous double
invocation; bench.sh grade/status gained an explicit --model override
(RUN-BENCHMARK.md now always uses it) so identity no longer depends
on a single mutable file. record()'s timeout is also now judged
per-correction-round rather than cumulatively, so legitimate
multi-round work isn't false-zeroed.

bench-premature-grade (P2): grading could fire before a model's
worktree file-write had settled, producing false-low scores. Both
bench.sh and run.sh now wait for worktree mtime-stability
(lib/sections.sh wait_for_worktree_stable, capped) before invoking
the grader.

Cosmetic: RUN-BENCHMARK.md now explicitly forbids the model
hand-rendering its own copy of the final tier chart - bench.sh
already prints it exactly once, automatically; paste it verbatim.

Adds selftest/run_isolation_selftest.py proving the fresh-timestamp/
staleness/lock/round-timeout/mtime-gate behavior, run entirely
against scratch copies. All existing selftests (run_selftests.py,
session_cost_selftest.py, token_capture_selftest.py) still pass -
no regressions. Preserves the uncommitted TOKEN-CAPTURE fix already
in the tree, untouched. No changes to model-scorecard.tsv data rows
or benchmark/runs/ (separate data-cleanup pass).
```
