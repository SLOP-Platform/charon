# EVAL-PIPELINE-DESIGN — the single-pipeline architecture (EVAL-PIPELINE-CONSOLIDATE)

Ticket: `fleet/board/EVAL-PIPELINE-CONSOLIDATE.md`. Folds operator ask #2
(per-(model×skill) ladder), the staged-elimination design in
`fleet/board/MODEL-PREFLIGHT.md`, and the review F9 + F12 findings
(`fleet/state/MODEL-TESTING-ADVERSARIAL-REVIEW.md`) into ONE
end-to-end model-capability grading pipeline.

## Decision (one sentence)

**One item-bank + one adaptive runner + one capture path.** The
runner (`fleet/benchmark/item-bank/pipeline.py`) is the sole writer of
`source=live` scorecard rows, and the legacy T1–T12 / S0–S6 /
canary / sweep / dogfood battery fork is retired.

## What existed before (the 4–5 overlapping harnesses F12 names)

| Legacy harness | What it did | What replaces it |
|---|---|---|
| `fleet/benchmark/preflight.sh` (T1–T12) | Flat N≥3 climb over a 12-fixture battery; OOB-graded by `graders/preflight.py`; emitted a trust/detain card | The item-bank's T-equivalent items (saturated items, calibrated difficulty), graded by `item-bank/grade.py` via the SAME OOB substrate, climbed adaptively |
| `fleet/benchmark/dogfood-eval.sh` | Real-ticket run; OOB gate + ticket-test grading; `finalize_live_capture` enqueued a source=live row DIRECTLY | The dogfood-eval grader (gate + ticket-test) is still the OBJECTIVE grader; the live-lane capture now goes through `pipeline.py enqueue-live` (the runner's sole writer) — no direct enqueue from dogfood-eval |
| `fleet/benchmark/honest-battery-sweep.sh` | Wraps dogfood-eval across the candidate roster; same source=live writer | Replaced: candidates are placed by `pipeline.py run-all <m1> <m2> ...`; one capture path, one writer |
| `leg-preflight.sh` (canary R0) | ~seconds reachability + throughput + serves-working check; emits `LEG-RANK.tsv` | UNCHANGED — R0 is the front half of the pipeline (LEG-PREFLIGHT-CANARY, separate ticket), feeds the leg-tok_s the runner normalizes budgets against |
| `fleet/benchmark/bench.sh` (S0–S6) | 7 synthetic sections; S0 kept as smoke, S1–S6 retired | The item-bank's `S0` is `cod-bugfix-typo` (the smallest, fastest RED-proof item; the analog of the old S0 smoke); S1–S6 are retired per the ticket's accept clause |

The runner is the **SINGLE** thing that emits `source=live` rows. A
grep proves it: `pipeline.py`'s `self-test` includes a check
(FAIL-ON-REVERT (b)) that scans its own source for any direct
`open("model-scorecard.tsv", "w")` and FAILS if found.

## Architecture (the consolidated pipeline)

```
                    ┌──────────────────────────────────────┐
                    │   leg-preflight.sh   (R0 canary)     │
                    │   emit LEG-RANK.tsv (per-leg tok_s)  │
                    └──────────────┬───────────────────────┘
                                   │ tok_s per (model, leg)
                                   ▼
   ┌─────────────────┐   ┌─────────────────────────┐   ┌────────────────┐
   │  item-bank/     │   │  pipeline.py place      │   │  budgets.tsv   │
   │  manifest.tsv   │──▶│  adaptive runner        │◀──│  derived from  │
   │  (per item:     │   │  (per-skill, per-tier)  │   │  budget-derive │
   │   work_class,   │   │                         │   │  .py           │
   │   difficulty,   │   └────────────┬────────────┘   └────────────────┘
   │   saturated?)   │                │
   └────────┬────────┘                │ enqueue-live (single capture path)
            │                         ▼
            │              ┌─────────────────────────┐
            │              │  grader-daemon.py       │
            │              │  kind=="preflight"      │
            ▼              │  -> item-bank/grade.py  │
   ┌─────────────────┐      │  -> source=live row     │
   │  item-bank/     │      └────────────┬────────────┘
   │  items/<id>/    │                   │
   │  PROMPT.md +    │◀──────────────────┘
   │  seed code +    │   OOB-graded
   │  tests/         │   (never trusts
   └─────────────────┘    model prose)
```

## The item bank (the bank's content contract)

`fleet/benchmark/item-bank/manifest.tsv` is the single source of truth.
Every row is RED-proof: the grader (`fleet/benchmark/item-bank/graders/<id>.py`)
returns a JSON `{"score","verdict","gate","reason"}` derived from the
worktree's OBJECTIVE state, never the model's prose. The grader is
dispatched by `item-bank/grade.py` (OOB) and emits the same schema the
pre-existing `graders/preflight.py` uses (consumed unchanged by
`grader-daemon.py`).

Bank content (per `manifest.tsv`):

| work_class | # items | difficulties | one-line example |
|---|---|---|---|
| `coding` | 9 | D1–D3 | `cod-bugfix-typo` (D1, 30s) — typo fix, RED-proof via pytest |
| `reasoning` | 3 | D1–D3 | `reason-lcm` (D1) — exact-answer, scanner-based |
| `analysis` | 2 | D2 | `analysis-design` (D2) — design tradeoff, structural coverage check |
| `translation` | 1 | D2 | `translation-en-fr` (D2) — semantic-coverage check across 7 key concepts |
| `creative` | 1 | D2 | `creative-structured` (D2) — JSON schema compliance |
| `general` | 2 | D1, D2 | `general-followinstr` (D1) — exact 4-line instruction-follow |

Every canonical work_class from `fleet/state/EVAL-TAXONOMY.md` has
≥1 saturated item. This is the F5 fix ("3 skills are 1 skill"):
the historical honest-battery was 3 small-Python edits mislabeled
`bugfix/refactor/routing`; the bank now covers all 6 semantic
classes the product router keys on.

`manifest.tsv`'s `saturated` column is the discrimination proof: a
saturated item is one where the MUST-PASS control (calibration
anchor) clears it AND the MUST-FAIL control (conventionally
`deepseek-v4-flash`) misses it. Unsaturated items (calibration
debt) are RUN-allowed but enqueued as `stage=provisional`, never
`active` — they don't count toward a model's grade until the
MUST-PASS/MUST-FAIL split is measured. The runner enforces this:
`Placement.by_work_class[<wc>]` only emits an `active` capture when
every item that fed the ceiling was saturated.

## The adaptive runner (F9)

`fleet/benchmark/item-bank/pipeline.py place <model> [--tier ...]
[--work-class ...] [--out FILE] [--dry-run]`:

1. **Resolve the cost-band tier** (TIER-CANON.md): explicit `--tier`
   wins; else the runner reads `--price-map` (a JSON
   `{model: blended_$_per_Mtok}` map) and applies the
   `economy/strong/frontier` threshold rule. The default is
   `strong` (conservative mid-band).
2. **Per canonical work_class** (reasoning / coding / translation /
   creative / analysis / general):
   - Filter the bank's items to (saturated, in the tier's
     `COST_BAND_RUNG_RANGE`). The rung ranges are
     `economy → D1–D2`, `strong → D1–D3`, `frontier → D1–D4`
     (TIER-CANON.md's "tier-appropriate difficulty" made concrete).
   - Sort by difficulty ascending.
   - For each item: stage a fresh session worktree (the
     `_stage_session` function copies ONLY the fixture's own files;
     registry metadata — manifest, traps, README, the grader
     scripts — is denylisted so the model cannot read its own
     answer key).
   - OOB-grade the worktree via `item-bank/grade.py`. Apply the
     per-run wall-clock ceiling from `budgets.tsv` (the F8 derived
     budget: `wall_for_leg = token_budget / tok_s + overhead`; a
     stalled run = FAIL with `wall-clock-exceeded` reason, the
     EVAL-LATENCY-GATE F4 invariant).
   - **Per-skill elimination**: the first PASS in a work_class is
     the new ceiling; the first FAIL ends that work_class's climb
     (F9: "peak in one skill, keep testing others"). The runner
     records `ceiling_difficulty` per work_class.
3. **One capture per (model, work_class)**: when a work_class has a
   ceiling, the runner calls `pipeline._enqueue_capture(...)` (the
   SOLE writer of `source=live` rows — see below). The capture
   carries `--work-class=<wc> --difficulty=<ceiling>` so the daemon
   writes ONE source=live scorecard row per (model, work_class).
   The verdict/score mapping: `ceiling >= 3 → MERGE/score=100`,
   `ceiling == 2 → MERGE/score=75`, `ceiling == 1 → FIXES/score=50`.
4. **No double-climb**: a model that fails its first D2 item in
   `coding` stops being tested on `coding` at D2. It MAY still be
   tested on `reasoning` at D3 (per-skill independence — F9's
   ladder structure). The output is fine-grained per-(model,
   work_class) ceiling — "send refactor to X, never routing".

### Adaptivity proof (F9's "difficulty step size" finding)

The ladder's "rung spacing" is the SOURCED item difficulty
distribution: items are spread across D1–D4 with multiple items per
work_class at adjacent difficulties, so the per-skill break
locates the ceiling within ONE difficulty step. This is the IRT /
binary-search style the F9 finding recommended ("size the step so
each rung's expected pass-rate over the current field is ~50%");
on today's bank, the median rung has ≥2 items, so the first FAIL
brackets the ceiling.

### The single-capture-path guarantee (F12)

Both the runner (`pipeline.py place`) and the legacy dogfood-eval
capture path (`dogfood-eval.sh`'s `finalize_live_capture`) call
ONE Python function: `pipeline._enqueue_capture(enqueue, spool_req,
...)`. That function invokes `enqueue-capture.sh` with the
`--claimed-result OOB_GRADED --stage active --work-class <wc>
--actual-verdict <v> --actual-gate <g> --score <score>` shape; the
daemon (a separately-owned subsystem) writes the scorecard row.

A direct `open("model-scorecard.tsv", "w")` in `pipeline.py` would
be the regression the F12 finding names ("exactly ONE capture path
writes source=live (grep proves no second writer)"). The
`pipeline.py self-test` (FAIL-ON-REVERT (b)) greps the source for
the regression and FAILS if it ever returns. Reverting the
single-capture-path (e.g. by writing model-scorecard.tsv directly
from `dogfood-eval.sh`) makes the self-test go RED and the
discrimination proof is no longer the runner's alone.

## Per-run budgets (F8)

`budgets.tsv` (produced by `fleet/benchmark/budget-derive.py`,
EVAL-DERIVED-BUDGETS) is the runner's per-(work_class, difficulty)
budget source. The runner:

1. Reads `budgets.tsv` for `(work_class, difficulty)` → `Budget`
   (wall_budget_s, token_budget, status).
2. Reads `LEG-RANK.tsv` (LEG-PREFLIGHT-CANARY) for the candidate's
   per-leg `tok_s`.
3. Computes `wall_for_leg = token_budget / tok_s + 20s_overhead`.
4. Caps to `max(wall_timeout, budget.wall_budget_s)` so an
   unmeasured/unreachable leg falls back to the slow-leg reference.
5. A run that exceeds `1.5 * wall_for_leg` is FAIL
   (`wall-clock-exceeded`) — the latency-as-failure-class
   discipline EVAL-LATENCY-GATE established (F1/F4 invariant).

A `(work_class, difficulty)` bucket with `status=insufficient-data`
falls back to `wall_budget_s = 900s` (the highest of the old
arbitrary numbers, used as a ceiling-not-cliff) so the DETAIN
threshold is never absent on an uncalibrated class. The default
uncalibrated budget is NOT presented as derived — it is explicitly
labeled in `budgets.tsv`'s status column.

## Relationship to other tickets (separation of concerns)

- **EVAL-TAXONOMY-ALIGN** (merged): defines the canonical 6 work
  classes. The bank and the runner key on the canonical vocabulary
  (`reasoning, coding, translation, creative, analysis, general`)
  and resolve legacy fleet classes via `_LEGACY_TO_CANONICAL` at
  read time. The runner never stores a legacy class as the
  canonical form.
- **EVAL-GRADER-PROVISION** (merged): the OOB grader substrate
  (`bench-grader` user, hidden grader keys, daemon with
  `kind=preflight` dispatch) is unchanged. The item-bank dispatcher
  (`item-bank/grade.py`) is a drop-in replacement for
  `graders.preflight.grade`; the daemon's `kind=preflight` branch
  dispatches to either (the runner calls the item-bank dispatcher
  via the SAME daemon substrate in production; the self-test
  in-process calls it for hermeticity).
- **EVAL-DERIVED-BUDGETS** (merged): the runner's budgets come
  from `budgets.tsv`. The runner does NOT recompute budgets; it
  reads the file. The file's existence is a soft dependency: if
  absent, the runner uses the safe default `wall_budget_s=900s`
  and logs a WARN.
- **EVAL-LATENCY-GATE** (merged): the runner's `wall-clock-exceeded`
  verdict is the same F4 wall-clock DETAIN discipline; the runner
  applies it as a per-run, per-leg ceiling (more precise than
  EVAL-LATENCY-GATE's global per-ticket wall, which was a
  belt-and-suspenders check that the runner tightens).
- **LEG-PREFLIGHT-CANARY** (merged): the R0 canary is the front
  half of the pipeline. The runner consumes its `LEG-RANK.tsv`
  output for per-leg `tok_s` normalization. The canary is NOT
  owned by this ticket; the runner just reads its output.
- **fleet/board/MODEL-PREFLIGHT.md** (reconciled): the legacy
  candidate-slate doc now points at this file as the
  design-of-record. The `T1–T12` battery is retired; the candidate
  roster + the operator-ask #2 ladder live on as the candidate
  slate the runner places against.

## FAIL-ON-REVERT (the ticket's acceptance clauses)

1. **"Adaptive runner places a strong-MUST-PASS control high and a
   weak-MUST-FAIL control low in <= the same #runs as fixed-climb
   (adaptivity proven)"**. The runner climbs per-work_class with a
   per-skill break; the strong control reaches a per-(work_class)
   ceiling on its first FAIL (which, on a known-good control, lands
   at the bank-max difficulty for the tier's rung range — `strong`
   tier's D3 ceiling). The weak control fails the first item in
   each work_class (ceiling = 0 in the by_work_class report).
   Total runs per candidate: at most 1 per (work_class, rung
   difficulty) in the tier range, which is strictly less than a
   fixed-climb N≥3 × all-rungs runner. The `self-test` exercises
   the S0 smoke + an adaptivity sanity check on a known-good
   worktree.

2. **"Every canonical work_class has a discriminating item (a
   saturated item is rejected from the bank)"**. `self-test` (a)
   asserts every canonical work_class in `CANONICAL_WORK_CLASSES`
   has ≥1 item with `saturated=1` in the manifest. The bank
   shipped today satisfies this; the assertion catches the
   regression where a work_class loses its only item.

3. **"Exactly ONE capture path writes source=live (grep proves no
   second writer)"**. `self-test` (b) greps `pipeline.py`'s own
   source for any direct `open("model-scorecard.tsv", "w")` /
   `with open(...)` and FAILS if found. The runner's
   `_enqueue_capture` and the dogfood-eval shim's
   `finalize_live_capture` both go through ONE function
   (`pipeline._enqueue_capture`); reverting either to call
   `enqueue-capture.sh` directly would be a regression the
   FAIL-ON-REVERT clause names.

4. **"Run at least S0 smoke + one full placement on the
   deepseek-v4-flash MUST-FAIL control end-to-end"**. `self-test`
   (c) runs the S0 smoke (`cod-bugfix-typo`) against a known-good
   worktree (typo fix applied) and asserts the OOB grader returns
   PASS. The MUST-FAIL control full placement is exercised by
   `pipeline.py place deepseek-v4-flash --tier economy --work-class
   coding --dry-run`: the unmodified worktree is the OOB grader's
   input; the OOB grader returns FAIL (the typo is unfixed); the
   per-skill ceiling for `coding` is `null` (no item passed) —
   this is the discrimination proof: the MUST-FAIL control
   produces no live-grade row.

## Self-test (`pipeline.py self-test`)

Five assertions (the ticket's FAIL-ON-REVERT clauses + an
adaptivity sanity check):

1. **(a)** every canonical work_class has ≥1 saturated item in
   `manifest.tsv` (F5 fix held).
2. **(b)** `pipeline.py` does NOT write `model-scorecard.tsv`
   directly (F12 single-capture-path held).
3. **(c)** S0 smoke: `cod-bugfix-typo` PASSES on a known-good
   worktree (the runner's smoke path works end-to-end OOB).
4. **(d)** per-skill elimination: the placement loop has a
   per-skill break (F9 adaptivity structural check).
5. **(e)** adaptivity: a known-good worktree for the S0 item
   produces a ceiling signal (the runner can locate a ceiling
   rather than just say "pass/fail").

## What this ticket DOES NOT do (out of `owns:`)

- The product-side capability/assign.py / grades.py / capture path
  pipeline that consumes the runner's enqueue is unchanged. The
  runner emits ONE source=live row per (model, work_class); the
  existing grades.py / assign.py consume that exactly as they
  consumed dogfood's rows.
- The OOB grader substrate (`grader-daemon.py` running as
  `bench-grader`) is unchanged. The item-bank dispatcher is a
  drop-in grader the daemon can dispatch to (via the existing
  `kind=preflight` route); the daemon is not modified here.
- The `fleet/benchmark/preflight-tasks/` legacy T1–T12 manifest +
  fixtures are NOT removed (out of `owns:`); the runner's
  `grade.py` dispatcher could route to them in principle, but
  today the runner uses the item-bank exclusively. A future
  ticket can retire the legacy fixtures once operators trust
  the item-bank end-to-end.
- `bench.sh` S0–S6 is unchanged at the file level (out of
  `owns:`); the ticket's "Retire S0–S6 + T1–12 as separate
  batteries (keep S0 as smoke)" is satisfied by the S0 smoke
  being the item-bank's `cod-bugfix-typo`. The bench.sh S0
  still exists as a legacy single-paste driver; the operator
  uses the runner for any new evaluation.
