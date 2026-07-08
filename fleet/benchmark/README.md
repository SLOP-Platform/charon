# fleet/benchmark — model-benchmark harness

Runnable implementation of `fleet/MODEL-BENCHMARK-SPEC.md` (see
`fleet/TICKET-BENCHMARK-HARNESS.md` for the build ticket). Build-rig only —
does not ship with the Charon product.

## Layout

- `fixtures/sections/s0` .. `s5/` — self-contained backend Python fixtures,
  one per section, each already in that section's injected-bug starting
  state (mirrors Charon's `gateway/*.py` shape).
- `fixtures-fe/` — the S6 frontend fixture: a bare Vite+Svelte toolchain
  (`npm run build` → `dist/bundle.js`) with a placeholder `App.svelte` that
  renders nothing yet, plus `fixtures/status.json` / `status.mutated.json`
  mock API responses.
- `graders/s0.py` .. `s5.py`, `graders/s6.js` — one deterministic grader per
  section (`common.py` holds shared diff/pytest/swap-and-rerun helpers). Each
  grader's CLI contract: `<grader> --worktree <dir> --baseline <fixture-dir>`
  → one JSON line `{"score","verdict","gate","reason"}` on stdout.
- `selftest/goldens/sN/{golden,inert,...}/` — full worktree snapshots used
  only to prove each grader discriminates a correct solution from a
  buggy/dodging one. `selftest/run_selftests.py` runs every grader against
  every golden/inert pair and asserts the expected score. **Run this before
  trusting any grader change:**
  ```
  python3 selftest/run_selftests.py
  ```
- `lib/grade_state.py` — per-(model,section) run state (start timestamp,
  correction-round counter, finalization) so `time_s`/`corrections` in the
  ledger are always runner-captured, never hand-typed.
- `lib/sections.sh` — section metadata (grader/fixture/timebox/work_class/
  backend-tier) shared by both drivers below, so they can never drift.
- `lib/detect_model.py` — auto-detects the model the CURRENT opencode
  session is running as (see "Running a model" below for the method).
- `lib/tier_chart.py` — computes the section→grade table + ONE overall tier
  (across all 7 sections) + intra-tier rank printed at the end of a
  `bench.sh` run.
- `bench.sh` — **the runner** (single in-session, one-paste driver — see
  below). `run.sh`, `run-many.sh` — superseded/legacy manual drivers, kept
  for scripted bulk-provisioning; see their own file headers.
- `RUN-BENCHMARK.md` — durable self-drive instructions so kicking off a full
  run is a one-liner: `read this and execute: <absolute path>`.

## Running a model — one paste, all 7 sections, auto-tiered

`bench.sh` is built for exactly one workflow: the operator picks a model in
opencode with `/model`, then pastes ONE prompt into that SAME session. From
there the agent (running AS the selected model — it IS the thing being
benchmarked) drives itself through every section with no further input from
the operator.

**The one-liner kickoff** — after `/model`, paste this into the opencode tab
(the full self-drive prompt lives in the durable file below, so this is all
the operator ever has to type):

```
read this and execute: /home/stack/charon-private/fleet/benchmark/RUN-BENCHMARK.md
```

That's the operator's entire manual action for a full 7-section calibration
run — no typing the model name (auto-detected), no per-section shuttling,
no re-pasting the driving instructions each time (they're durable in
`RUN-BENCHMARK.md`, an absolute path so it works regardless of the opencode
session's cwd). See that file for the exact instructions the agent follows
(run `bench.sh start`, implement, `bench.sh grade`, loop, show the final
tier chart).

**Model detection** (`lib/detect_model.py`): reads
`~/.local/share/opencode/opencode.db` (SQLite, read-only) — every opencode
session persists its own `model` column, updated live on every `/model`
switch — and takes the most-recently-updated session (reliable *because*
the operator just switched models and immediately pasted into that same
tab, so its row is the freshest in the whole DB at that instant) *provided*
it's unambiguous. A 15-minute staleness guard refuses a stale row.
**RECOMMENDED: always pass `--model <id>` explicitly instead of relying on
auto-detect** — `RUN-BENCHMARK.md` now leads with this. Auto-detect is
fundamentally unreliable in this rig's normal multi-tab operating mode,
since `session.time_updated` bumps on ANY tab activity, not only a
`/model` switch: some OTHER, unrelated concurrent tab (manager session,
another droid tab) can easily be touched more recently than the operator's
own freshly-picked bench tab. Confirmed incident
(`bench-model-misdetect`, fleet/reds.tsv, P1): after an opencode restart, a
restored prior session read as "freshest", auto-detect announced the WRONG
model, saw it already finalized, and silently SKIPPED the run with no
error. Fixed two ways:
  1. `detect()` now collects every session updated within the staleness
     window and looks at the DISTINCT set of models among them — if 2+
     DIFFERENT models were set recently (i.e. genuine ambiguity, not just
     "some other row exists"), it REFUSES to guess (exit 2) rather than
     silently trusting rank-1.
  2. `bench.sh start`'s ANNOUNCE banner now includes an explicit
     **STOP - VERIFY** block telling the operator/agent to confirm the
     announced id matches their own `/model` pick before implementing
     anything, and how to re-run with `--model` if not.
**Fallback** if nothing fresh is found, or if it's ambiguous: the agent is
asked to self-report its own model name and re-invoke with
`bench.sh start --model <id>`. See the module docstring for the other
methods investigated (global `model.json`, CLI, env vars) and why each was
rejected in favor of the DB.

**Subcommands** (`bench.sh` needs no section/model args in the common
path — see its header for full docs):
- `bench.sh start [--model <id>]` — detect + announce the model, prepare
  the next un-finalized section in the fixed S0..S6 queue. **Prefer the
  explicit `--model <id>` form** (see "Model detection" above) — plain
  `start` auto-detects and now refuses instead of guessing whenever it's
  ambiguous, but the explicit form never has that failure mode at all.
- `bench.sh grade [--model <id>]` — grade whatever is currently in flight,
  auto-append the row, then automatically prepare the next section (or
  print the final tier chart if that was S6). **Always pass `--model <id>`
  (the id `start` announced) when more than one bench.sh tab may be
  active on this box** — without it, the model is read from a single
  on-disk pointer shared by every concurrent tab, which a DIFFERENT tab's
  `start` can silently overwrite (`bench-run-collision`, fleet/reds.tsv);
  `RUN-BENCHMARK.md` always uses the explicit form.
- `bench.sh status [--model <id>]` — where the current run is, no side
  effects.
- `bench.sh chart [<model>]` — (re-)print the tier chart standalone. This
  is the ONLY place the chart is rendered (`lib/tier_chart.py`) — never
  hand-render/re-type a copy of it.
- `bench.sh reset --model <id> [--force]` — **operator-facing, not part of
  the agent's S0..S6 loop.** Re-benchmarking a model whose 7 sections are
  already finalized (e.g. moving it to v2 scoring) needs a clean slate
  first — `start`/`grade` treat a fully-finalized model as "run complete"
  and never overwrite it. `reset` backs up (to
  `runs/.reset-backups/<id>-<timestamp>/`) then clears ONLY that model's
  `runs/<id>/` state and its `bench`/`bench2`-sourced rows in
  `model-scorecard.tsv` — any `source=live` rows for that model (real
  production grades, not harness output) are always kept. Refuses if that
  model has a genuinely active in-flight section right now (pass `--force`
  to override — not recommended while a bench may really be running).
  Never touches any other model's data. After it completes,
  `bench.sh start --model <id>` begins a fresh S0..S6 run.

**Run isolation / staleness**: each section's on-disk state
(`runs/<model>/<section>/meta.json`) now tracks whether it's still
genuinely active (within its own current correction round's timebox) or
stale/abandoned; `bench.sh` only resumes state that `lib/grade_state.py`'s
`is_active` reports as active, otherwise it reinitializes fresh (new
worktree, new `start_ts`) instead of silently inheriting a poisoned clock
from an abandoned run. `init`/`record` also hold a short non-blocking
`flock` on the state dir as a last-line defense against a genuinely
simultaneous double invocation. See `lib/grade_state.py`'s module
docstring for the full incident writeup.

**Grading is gated on worktree mtime-stability** (`bench-premature-grade`,
fleet/reds.tsv): `bench.sh grade`/`run.sh --grade` both wait
(`lib/sections.sh` `wait_for_worktree_stable`) until the worktree's newest
file mtime has been unchanged for a few seconds before invoking the grader,
so a model's own in-flight file-write doesn't get graded a split second
too early.

The **tier chart** printed at the end shows a section→grade table plus ONE
**OVERALL TIER** computed across all 7 sections (S0-S6 together, no separate
backend/frontend axes) and this model's **rank** (`#N of M`) against every
other model already in `model-scorecard.tsv` that landed in the same tier.

- S0 stays a pass/fail sanity gate (must score exactly 100, else the whole
  run is **INVALID** — investigate the harness/model-plumbing before
  trusting any other section).
- Once S0 is clean, the **composite** = the unweighted mean of every graded
  section's score in S1..S6.
- That composite maps onto a simple, plain-word ladder — no compound or
  parenthetical jargon:

  | Tier | Composite |
  |---|---|
  | Frontier | ≥ 90 |
  | Strong | 75-89 |
  | Capable | 60-74 |
  | Basic | 50-59 |
  | **No Tier** | < 50 — too weak to place |

- Rank is by composite score against every other model in the same tier,
  ties broken by lower mean `time_s` across all graded sections. `INVALID`
  and `No Tier` runs are never ranked — the chart says so plainly instead.

No `fleet/tiers.json` exists in this repo — the formula/ladder above is this
chart's own definition, documented in full in `lib/tier_chart.py`'s module
docstring (including why it replaced the old two-axis backend-tier/
frontend-tier chart: S6 now counts as just another equally-weighted
capability section instead of a parallel axis).

Same auto-scoring guarantees as before: a `grade` call that comes back
`gate=fail` doesn't append anything — fix the same worktree and re-run
`bench.sh grade` (counted as one correction round, capped at 3 per
`MODEL-BENCHMARK-SPEC.md` §5a, after which the row is appended but capped
below the MERGE band). A `grade` call after the section's time-box elapsed
auto-scores 0 with `note="timeout"` — a hung model never hangs the run.

### Legacy manual flow (superseded) / bulk-provisioning many models

`run.sh`/`run-many.sh` still work (they share the exact same on-disk state
as `bench.sh` via `lib/grade_state.py` + `lib/sections.sh`, so a worktree
prepared by either can be graded by the other), but for the interactive
single-model flow use `bench.sh` instead — it's what the target UX above
describes. `run.sh` remains useful standalone for scripted subset re-checks
(`--sections S0,S2,S6`), and `run-many.sh` remains the only tool that bulk
*prepares* fixture worktrees for a whole roster of models in one invocation
(e.g. to stage several opencode tabs at once):

```
./run.sh glm-5.2 --sections S0,S2,S6     # manual per-section shuttling (legacy)
./run.sh --grade S0 glm-5.2

./run-many.sh glm-5.2 deepseek-v4-pro    # bulk-prepare worktrees for a roster
./run-many.sh --models-file roster.txt -- --sections S0,S2,S6
```

## Time-box budget (from MODEL-BENCHMARK-SPEC.md §1)

| Section | Budget | Full 7-section run |
|---|---|---|
| S0 | ~3 min |
| S1 | ~6 min |
| S2 | ~10 min |
| S3 | ~8 min |
| S4 | ~12 min |
| S5 | ~10 min |
| S6 | ~12 min |
| **Total** | | **~61 min** |

Use `--sections S0,S2,S6` for a quick smoke/re-check instead of paying for
the full budget every time.

## Ledger mapping

Each finalized section appends one `bench` row via
`fleet/model-scorecard.sh append <date> bench <ref> <work_class> <tier>
<model> <verdict> <gate> <score> <time_s> <cost_usd> <corrections> <note>` —
this is always the runner's own last step, never a separate manual entry.
`verdict` is derived from score (`>=90 MERGE`, `50-89 FIXES`, `<50 BLOCK`).
`work_class=frontend` was added to `model-scorecard.sh`'s enum for S6 (it
was missing — required for S6's append to validate).
`cost_usd` is always `-` today (best-effort; populated only once a
gateway-attributed driving flow exists per SR-5b — never estimated).

## Known spec/ticket reconciliation

`TICKET-BENCHMARK-HARNESS.md`'s acceptance criteria say a hardcoded/static S6
solution should self-test to `0`. `MODEL-BENCHMARK-SPEC.md`'s own §3 S6
rubric is more specific and caps that exact case at **75** ("renders
correctly once, doesn't react to changed data — hardcoded/static"), which is
the literal rubric number this grader implements (mirrors S2's identical
"feature-inert" case, which the spec itself caps at 50, not 0). The
self-test (`selftest/run_selftests.py`) asserts the hardcoded case scores
`< 90` (clear of the MERGE band) rather than exactly `0`, and documents this
here so the discrepancy isn't silent.
