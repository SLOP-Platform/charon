# EVAL-PIPELINE-CONSOLIDATE — Review Log

## Ticket
EVAL-PIPELINE-CONSOLIDATE (review F9 + F12, operator ask #2): collapse
the 4–5 overlapping harnesses (preflight.sh T1–T12, dogfood-eval,
honest-battery-sweep, canary R0, bench.sh S0–S6) into ONE pipeline.
See the full design at `fleet/state/EVAL-PIPELINE-DESIGN.md`.

## What was done (files owned by this ticket)
- `fleet/benchmark/item-bank/` — the consolidated item bank
  - `manifest.tsv` (one row per item, 19 items total covering all 6
    canonical work classes from `fleet/state/EVAL-TAXONOMY.md`).
  - `README.md` (the bank contract).
  - `grade.py` (OOB dispatcher; mirrors `graders.preflight.grade()`'s
    contract so the daemon can route `kind=="preflight"` to it).
  - `graders/_item_base.py` (shared fail-closed helpers).
  - `graders/<item_id>.py` (one OOB grader per item; fail-closed;
    never trusts model prose).
  - `items/<item_id>/` (the fixtures: PROMPT.md + seed code +
    tests/ for pytest-based items; answer.txt for non-pytest items).
  - `pipeline.py` (the adaptive runner — the SOLE writer of
    `source=live` rows; CLI: `place` / `run-all` / `enqueue-live` /
    `self-test`).
- `fleet/benchmark/preflight.sh` (now a delegating shim to
  `pipeline.py place`; preserves the historical CLI for backward
  compatibility; legacy T1–T12 manifest retired).
- `fleet/benchmark/dogfood-eval.sh` (`finalize_live_capture` now
  routes through `pipeline.py enqueue-live` instead of calling
  `enqueue-capture.sh` directly — same single-capture-path the
  runner uses; removes the dogfood/preflight/sweep fork).
- `fleet/board/MODEL-PREFLIGHT.md` (reconciled to point at the
  design; this ticket is the CANDIDATE SLATE + design-of-record
  pointer only; the battery/runner/capture-path are owned by
  EVAL-PIPELINE-CONSOLIDATE).
- `fleet/state/EVAL-PIPELINE-DESIGN.md` (the one-pipeline
  architecture doc).

## Key decisions

### D1 — One item bank, not five
The 4–5 overlapping harnesses (F12) all measure "can this model do a
small Python code task correctly" with different test sets, different
calibrations, and different source=live writers. The consolidated
bank is ONE registry (`manifest.tsv`), ONE set of fixtures
(`items/<id>/`), ONE OOB grader path (`grade.py` -> `graders/<id>.py`),
and ONE source=live writer (the runner's `_enqueue_capture`). The
legacy T1–T12 / S1–S6 / canary / sweep / dogfood forks are retired;
S0 survives as the item-bank's `cod-bugfix-typo` smoke (the only
synthetic section the ticket names as kept).

### D2 — Every canonical work_class has >=1 discriminating item (F5 fix)
The honest-battery was 3 small-Python charon edits mislabeled
`bugfix/refactor/routing` — "3 skills are 1 skill" (F5). The bank has
≥1 saturated item per canonical work class (reasoning / coding /
translation / creative / analysis / general), so the runner can grade
a model on EVERY axis the product router keys on, not just one
ill-defined "small code change" skill. The `saturated` column on
`manifest.tsv` is the discrimination proof (a MUST-PASS control
clears it AND a MUST-FAIL control misses it); an unsaturated item is
in the bank on a calibration promise and is enqueued as
`stage=provisional` (never `active`) until the split is measured.

### D3 — Per-skill adaptive placement (F9 fix)
The legacy ladder was a fixed N≥3 climb from R1 to R3 (4 fixed rungs,
no adaptive placement, no per-skill elimination). The new runner
places each candidate near its cost-band rung range (TIER-CANON.md:
economy D1–D2, strong D1–D3, frontier D1–D4), then climbs per
canonical work_class with a per-skill break — a model that FAILS an
item at difficulty D stops being tested at D+1 in the SAME
work_class (F9: "peak in one skill, keep testing others"). The
output is a fine-grained per-(model, work_class) ceiling grade —
"send refactor to X, never routing" — which is exactly what
`assign.py` consumes.

### D4 — Token/tok_s-normalized budgets (F8 fix)
Per-run wall-clock comes from `budgets.tsv` (EVAL-DERIVED-BUDGETS):
`wall_for_leg = token_budget / measured_tok_s + 20s_overhead`. A
slow-but-correct leg gets proportionally more wall time; only a model
that needs MORE tokens than the good-model p95 (thrashing) or stalls
fails. A `(work_class, difficulty)` bucket with `insufficient-data`
falls back to a conservative `wall_budget_s=900s` (safe default, NOT
presented as derived) so the DETAIN threshold is never absent on an
uncalibrated class. A run that exceeds `1.5 * wall_for_leg` is
FAIL with `wall-clock-exceeded` — the latency-as-failure-class
discipline EVAL-LATENCY-GATE established (F1/F4 invariant).

### D5 — The runner is the SOLE writer of `source=live` rows (F12 fix)
The runner's `_enqueue_capture(enqueue, spool_req, ...)` is the
single Python function that drops a paired FINAL into the
grader-daemon maildrop. Both the runner (`cmd_place`) and the
legacy dogfood-eval shim (`finalize_live_capture` in
`dogfood-eval.sh`) call this same function. A direct
`open("model-scorecard.tsv", "w")` anywhere in `pipeline.py` is
the regression the FAIL-ON-REVERT (b) grep catches — the F12
"exactly ONE capture path writes source=live" guarantee. The
runner NEVER appends to `model-scorecard.tsv` directly; the daemon
owns the ledger write.

### D6 — OOB grading, fail-closed
Every item's grader is OOB: it inspects the worktree's OBJECTIVE
state, NEVER the model's prose. The grader returns
`{"score","verdict","gate","reason"}`; `grade.py`'s dispatcher
mirrors `graders.preflight.grade()`'s schema so the daemon can
route `kind=="preflight"` requests to it. The dispatcher fails
CLOSED: an unknown `item_id`, a missing grader, a crashed grader,
or a wall-clock breach ALL return BLOCK. A flaky grader that
defaults to PASS is worse than one that defaults to FAIL — the F2
BLOCKER (battery fails closed for every model) is the inverse
bug we explicitly avoid.

### D7 — Red-proof design (no fix-don't-delete)
The bank items use seeded RED tests + an OOB grader that runs
pytest in the worktree. The `cod-regression-fix` grader adds a
spec-text identity check: the test the model is supposed to make
green is committed as the spec; the grader compares the worktree's
test file to the canonical spec text and FAILs if the model edited
the test instead of the implementation. The
`EVAL-PIPELINE-CONSOLIDATE` ticket's `fix-don't-delete` invariant.

### D8 — Disguise invariant (item dir copy, no registry leak)
The runner's `_stage_session(item_dir, snapshot)` copies ONLY the
fixture's own files (PROMPT.md + seed code + tests/ for pytest
items, answer.txt for non-pytest items) into a fresh session
worktree. The manifest, the README, the grader scripts, and the
registry's traps are denylisted — a model cannot read its own
answer key. The disguise invariant is inherited from
`preflight.sh`'s original `copy_session_files`; the new
implementation is the same pattern (denylist on copy), preserved
verbatim in `_stage_session`.

## FAIL-ON-REVERT proof (`pipeline.py self-test`)

Five assertions (hermetic, no live network, no live model):

1. **(a) F5 fix held** — every canonical work_class has ≥1 saturated
   item in `manifest.tsv`. Revert by removing a row from the
   manifest → the assertion FAILS.
2. **(b) F12 single-capture-path held** — `pipeline.py`'s own
   source has no `open("model-scorecard.tsv", "w")` / `with
   open(...)` (the regression where the runner writes the scorecard
   directly, bypassing the daemon's maildrop). A grep proves it;
   reverting the `_enqueue_capture` path to call `enqueue-capture.sh`
   directly from elsewhere makes the assertion FAIL.
3. **(c) S0 smoke end-to-end** — `cod-bugfix-typo` PASSES on a
   known-good worktree (the typo fixed). Revert the dispatcher /
   the fixture / the grader → the assertion FAILS.
4. **(d) Per-skill elimination structural check** — the placement
   loop's per-skill `break` is in place. Revert the break → a model
   that fails D2 in `coding` would be tested at D3 in `coding`
   (waste of rungs; the F9 violation).
5. **(e) Adaptivity sanity** — a known-good worktree for the S0
   item produces a ceiling signal (the runner reports
   `ceiling_difficulty >= 1` for at least one work_class). A
   runner that returns "pass/fail" without locating a ceiling fails
   this assertion.

Plus the MUST-FAIL control end-to-end run: `pipeline.py place
deepseek-v4-flash --tier economy --work-class coding --dry-run`
reports `ceiling_difficulty: null` for `coding` (the OOB grader
returns FAIL on the unfixed worktree, so no ceiling is recorded).
This is the discrimination proof: a known-bad model produces no
live-grade row.

## Scope check (changed paths vs owns)
- `fleet/benchmark/preflight.sh` — in `owns:`
- `fleet/benchmark/dogfood-eval.sh` — in `owns:`
- `fleet/benchmark/item-bank/` — in `owns:`
- `fleet/board/MODEL-PREFLIGHT.md` — in `owns:`
- `fleet/state/EVAL-PIPELINE-DESIGN.md` — in `owns:`
- `docs/review-log/EVAL-PIPELINE-CONSOLIDATE.md` — this fragment (allowed)

No other files touched.

## Gate
- `PYTHONPATH=src python3 -m pytest -q` → 54 passed (no new failures;
  the existing fleet tests are unchanged by this ticket).
- `ruff check fleet/benchmark/item-bank/` → all checks passed (the
  pre-existing 17 ruff errors in the legacy `fleet/benchmark/`
  files are unchanged — they predate this ticket and are out of
  scope; the item-bank is clean).
- `mypy fleet/benchmark/item-bank/grade.py fleet/benchmark/item-bank/pipeline.py` →
  no issues found. The pre-existing mypy error in
  `fleet/benchmark/fixtures/sections/s0/gateway/` is a fixture
  duplication issue (two `gateway/__init__.py` files at adjacent
  paths) that pre-dates this ticket and is out of scope.
- `bash fleet/tests/budget-derive.test.sh` → 18 passed, 0 failed
  (EVAL-DERIVED-BUDGETS self-test is unchanged; the runner reads
  budgets.tsv but does not modify it).
- `python3 fleet/benchmark/item-bank/pipeline.py self-test` → 10
  passed, 0 failed (the FAIL-ON-REVERT self-test).
- `python3 fleet/benchmark/item-bank/pipeline.py place
  deepseek-v4-flash --tier economy --work-class coding --dry-run` →
  MUST-FAIL control full placement end-to-end; reports
  `ceiling_difficulty: null` for `coding` (the discrimination
  proof).

## Residual / blast radius
- `preflight-tasks/` (the legacy T1–T12 fixtures + manifest) is
  unchanged. A future ticket can retire it once operators trust the
  item-bank end-to-end; this ticket's `pipeline.py` could route to
  it via the `grade.py` dispatcher in principle but uses the
  item-bank exclusively today.
- `bench.sh` S0–S6 is unchanged at the file level (out of `owns:`).
  The S0 smoke the ticket requires is the item-bank's
  `cod-bugfix-typo`; the legacy `bench.sh` S0 still exists but is
  no longer the canonical smoke path.
- `fleet/board/EVAL-PIPELINE-CONSOLIDATE.md` (the original
  ticket) is unchanged; it's the ticket prompt, not a design doc.
- The grader-daemon (`fleet/benchmark/grader-daemon.py`) is
  unchanged. The item-bank dispatcher (`item-bank/grade.py`) is a
  drop-in grader the daemon can route to via the existing
  `kind=preflight` branch; the daemon's grader dispatch is not
  modified here.
- `enqueue-capture.sh` (in `fleet/capture/`) is unchanged. The
  runner's `_enqueue_capture` is the only Python code that calls it
  for `source=live` rows.
