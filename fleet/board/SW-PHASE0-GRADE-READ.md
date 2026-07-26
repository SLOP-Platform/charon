repo: charon-private
tier: strong
difficulty: 2
work_class: rig-meta
priority: 0
branch: fix/sw-phase0-grade-read
depends_on:
owns: fleet/capability/grades.py, fleet/capability/tests/test_grades_no_control_admit.py
serial_justified: |
  ONE read-path predicate plus its proof. The defect is a single admission rule in
  `fleet/capability/grades.py:544-559`; splitting the rule from the test that pins it reproduces the
  exact failure mode being fixed (a silent zero-row filter nobody can see).
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session (charon/* gateway model), NOT Claude.
  The run IS a graded sample: record it into fleet/model-scorecard.tsv with the work_class above.
  Wall-clock, retries and any fabricated-success must be logged as scorecard evidence.
  One checkout, one agent — its OWN worktree, never a shared checkout.
source: |
  Grading-path verification, 2026-07-26 (manager session kit-fisto), report at
  fleet/handoff-notes/GRADING-PATH-VERIFY-2026-07-26.md. Facts pre-verified — do NOT re-derive.
note: |
  ## THE DEFECT — the ledger WRITES but the ranking READS NOTHING
  `fleet/capability/grades.py:544-559` requires >= 3 `strong-control` rows per ref before a model's
  rows count. `grep -c strong-control fleet/model-scorecard.tsv` = **0**. So `_rows_for` drops EVERY
  live row, `GradesProvider().grade()` returns `None` for all models, and
  `python3 fleet/capability/assign.py <ticket>` answers `REFUSED — no eligible candidate` for every
  ticket — including with explicit `--work-class` and `--candidates`.

  The ledger itself is healthy: 64 rows, all `source=live`/`stage=active`, newest 2026-07-25. The data
  is there. Nothing can read it.

  ## WHY THIS IS PRIORITY 0
  Every graded run recorded until this is fixed is recorded into a ledger that no assignment decision
  consults. Model ranking is currently theater: the rows accumulate and change nothing. The whole
  point of routing real work to non-Anthropic models is to learn which ones are good — that learning
  is presently discarded at the read.

  ## THE FIX ALREADY EXISTS — PORT IT, DO NOT REDESIGN
  The no-control->admit fallback landed PRODUCT-side at
  `src/charon/capability/grades.py:149` (`_is_fallback_admit`, commit 0947401, "no-control→admit
  fallback so EVAL-PROMOTION-GATE grades live refs"). The RIG copy has **zero** occurrences of it.
  This is a straight port of a reviewed, landed fix into the rig's copy of the same logic — NOT a new
  admission policy. If the port appears to need a different rule than the product's, STOP and report:
  a divergence between the two copies is itself the finding.

  ## KNOWN, DELIBERATELY OUT OF SCOPE (do not touch)
  `fleet/done.sh:175` hardcodes `MERGE/pass/score=100` (63 MERGE vs 1 BLOCK — no discriminating
  signal). That is a REAL second defect but `fleet/done.sh` is owned by four other live tickets with a
  documented single-writer chain. It is dispositioned separately. Fixing the READ here is still
  correct and independently valuable: it is the blocker, and it unblocks every later signal
  improvement.
accept: |
  DONE-CONTRACT (observable, by EXECUTION — not "code written"):
  - `python3 fleet/capability/assign.py <a real live ticket id>` returns an actual candidate instead of
    `REFUSED — no eligible candidate`. Paste the before and after output.
  - `GradesProvider().grade()` returns a non-None grade for at least one model that has live rows.
    Name the model and the row count it drew on.
  - FAIL-ON-REVERT, red-proofed by execution: revert the admission predicate -> the new test goes RED
    and names the zero-control case. Report BOTH exit codes. A green you did not first make fail is
    not evidence.
  - NON-VACUOUS: the test must fail if the scorecard has zero rows — never a silent pass on an empty
    ledger.
  - State explicitly what you proved by RUNNING vs by READING, and which git ref you measured on.
  - No change to the scorecard DATA — this ticket fixes the READ only. A diff touching
    fleet/model-scorecard.tsv is out of contract [[session-end-hardening]].

## Dependencies & sequence

- **Depends on: NOTHING. Startable immediately.** Rig-side, disjoint from the entire Switchboard
  product wave — runs fully concurrent with SW-IDENTITY-FOLD and its fan-out.
- **Blocks (grading correctness, not build):** the recorded grade of every ticket in the Switchboard
  wave. Grading is written at `done.sh` time, AFTER merge — so this must land before `done.sh` is run
  on SW-IDENTITY-FOLD, not before SW-IDENTITY-FOLD starts.
- **Wave:** phase 0, parallel lane.
- **Concurrency safety:** `fleet/capability/grades.py` is owned by NO other live board ticket
  (verified against the full `owns:` set of fleet/board/*.md, 2026-07-26 — the other
  fleet/capability owners are assign.py, availability.py, tier_classify.py, effort.py).
- **Do NOT duplicate:** this is a PORT of commit 0947401, not a new policy. Read the product-side
  implementation first.
