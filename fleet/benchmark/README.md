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
- `lib/tier_chart.py` — computes the section→grade table + backend/frontend
  tier reach + intra-tier rank printed at the end of a `bench.sh` run.
- `bench.sh` — **the runner** (single in-session, one-paste driver — see
  below). `run.sh`, `run-many.sh` — superseded/legacy manual drivers, kept
  for scripted bulk-provisioning; see their own file headers.

## Running a model — one paste, all 7 sections, auto-tiered

`bench.sh` is built for exactly one workflow: the operator picks a model in
opencode with `/model`, then pastes ONE prompt into that SAME session. From
there the agent (running AS the selected model — it IS the thing being
benchmarked) drives itself through every section with no further input from
the operator.

**Paste this into the opencode tab right after `/model`:**

```
You are being benchmarked. In THIS session, run: fleet/benchmark/bench.sh start
Read its output (it announces which model it thinks you are, plus the first
section's prompt and worktree path). Implement that section's task yourself,
directly in the printed worktree, using your own tools. When you're done,
run: fleet/benchmark/bench.sh grade
If it says a correction round failed, fix the same worktree and run
bench.sh grade again. Once it reports the section's FINAL score, it will
automatically print the next section's prompt+worktree if any remain, or a
tier chart with your rank if all 7 sections (S0-S6) are complete. Keep
looping (implement -> bench.sh grade) through every section without asking
me anything in between, and show me the final tier chart when it appears.
```

That's the operator's entire manual action for a full 7-section calibration
run — no typing the model name (auto-detected), no per-section shuttling.

**Model detection** (`lib/detect_model.py`): reads
`~/.local/share/opencode/opencode.db` (SQLite, read-only) — every opencode
session persists its own `model` column, updated live on every `/model`
switch — and takes the single most-recently-updated session (reliable
*because* the operator just switched models and immediately pasted into
that same tab, so its row is the freshest in the whole DB at that instant).
A 15-minute staleness guard refuses a stale row. **Fallback** if nothing
fresh is found (e.g. DB missing, or the operator waited too long): the
agent is asked to self-report its own model name and re-invoke with
`bench.sh start --model <id>`. See the module docstring for the other
methods investigated (global `model.json`, CLI, env vars) and why each was
rejected in favor of the DB.

**Subcommands** (`bench.sh` needs no section/model args in the common
path — see its header for full docs):
- `bench.sh start [--model <id>]` — detect + announce the model, prepare
  the next un-finalized section in the fixed S0..S6 queue.
- `bench.sh grade` — grade whatever is currently in flight, auto-append the
  row, then automatically prepare the next section (or print the final
  tier chart if that was S6).
- `bench.sh status` — where the current run is, no side effects.
- `bench.sh chart [<model>]` — (re-)print the tier chart standalone.

The **tier chart** printed at the end shows a section→grade table, this
model's **BACKEND TIER** (0-4, highest tier reached with every section at or
below it scoring ≥50 and S0=100 sanity-clean — "NO TIER" if S0 fails), and
its **FRONTEND TIER** (S6, scored as its own parallel axis per
`MODEL-BENCHMARK-SPEC.md` §4: tier 3 at ≥90, tier 2 at 60-89, no frontend
tier below that) — each with this model's **rank** (`#N of M`) against every
other model already in `model-scorecard.tsv` that landed in the same tier,
by composite score (mean section score, tie-broken by lower mean `time_s`).
No `fleet/tiers.json` exists in this repo — the tier names/cuts come
straight from the spec's own §0/§1/§4, documented in `lib/tier_chart.py`'s
module docstring.

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
