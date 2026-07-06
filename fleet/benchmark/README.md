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
- `run.sh`, `run-many.sh` — the runner (see below).

## Running a model

Driving the model is currently **manual** (matches the existing opencode-tab
workflow) — this is a deliberate seam so a future headless opencode/gateway
driver can slot in later without reworking any grader.

```
# 1. prepare one model, all 7 sections (or a subset)
./run.sh glm-5.2
./run.sh glm-5.2 --sections S0,S2,S6

# 2. for each section printed above: paste its prompt into an opencode tab
#    pointed at the printed WORKTREE path, let the model work.

# 3. grade + auto-append (never a separate manual scoring step)
./run.sh --grade S0 glm-5.2
```

If a `--grade` call comes back `gate=fail`, nothing is appended yet — tell
the model to fix it in the same worktree and re-run the same `--grade`
command. That is counted as one correction round automatically (capped at 3
per `MODEL-BENCHMARK-SPEC.md` §5a — a 4th round is cut off, the row still
gets appended, but the score is capped below the MERGE band). A `--grade`
call after the section's time-box has elapsed is auto-scored 0 with
`note="timeout"` — a hung model never hangs the run.

### Many models in one invocation

```
./run-many.sh glm-5.2 deepseek-v4-pro
./run-many.sh --models-file roster.txt -- --sections S0,S2,S6
```

Loops `run.sh`'s prepare step over the whole roster and prints one combined
summary (read live from `model-scorecard.tsv`) covering however many rows
have been graded so far for that roster.

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
