# Review-log fragment — STAGE-DEMUX

Ticket: STAGE-DEMUX
Date: 2026-07-16
Branch: feat/stage-demux

## Scope

Split the OVERLOADED `stage` field on the capture-spool path:
spool PHASE (write-now vs hold, derived from `actual_verdict`
presence) vs ledger column-16 TRUST (provisional vs active).
Pre-demux the daemon hardcoded the literal `"active"` into col 16
of every live row and never read `req["stage"]` from the request,
so NO code path could emit `source=live/stage=provisional`. Live
proof: 45/45 live rows in `fleet/model-scorecard.tsv` are active,
zero provisional ever.

## What I changed

- `fleet/benchmark/grader-daemon.py`:
  - New canonical on-the-wire field `trust_stage` (going forward)
    resolved by `_resolve_trust_stage(req)`. The legacy on-the-wire
    field `stage` (what `capture/enqueue-capture.sh` currently writes)
    is still accepted as a backward-compat alias.
  - `_append_capture_row(...)` now takes a `trust_stage` parameter
    and writes it to col 16 instead of the hardcoded literal.
  - The hardcoded `"active"` is gone. With the fix reverted, the
    fail-on-revert test in `test_stage_demux.py` goes RED.
  - PHASE is unchanged: still derived from `actual_verdict` presence
    (PROVISIONAL phase = hold, FINAL phase = append). The third
    fail-on-revert test pins this so the demux can't accidentally
    rewire phase.

- `fleet/benchmark/selftest/test_stage_demux.py` (NEW): 5 hermetic
  tests, of which the 3 the ticket names as fail-on-revert:

  1. **CORE: provisional trust survives.** Spool a FINAL with
     `trust_stage=provisional` and a real `actual_verdict` →
     ledger col 16 lands `provisional`. CONFIRMED RED with the
     fix reverted (test #1 went RED at the `trust_stage=provisional`
     assertion: landed `col 16 = 'active'`, expected `provisional`).
  2. **Active trust still survives.** `trust_stage=active` →
     `col 16 = active`. Proves the demux is not an inverted hardcode.
  3. **Phase protocol unchanged.** PROVISIONAL phase (no verdict) is
     still held regardless of the requested trust stage. Proves the
     phase/trust split did not break the two-phase spool protocol.
  4. **Legacy `stage` field still accepted** (backward compat with
     `enqueue-capture.sh`).
  5. **End-to-end through the real `enqueue-capture.sh`** writer:
     drives one lifetime (provisional → FINAL same run_id, with
     `--stage provisional` on both phases) and confirms the FINAL
     lands `col 16 = 'provisional'`.

## What I deliberately did NOT change

- `capture/enqueue-capture.sh` (NOT in `owns:`) — still writes
  the on-the-wire `stage` field. The daemon accepts this as a
  legacy alias. The follow-up `STAGE-FAILCLOSED` ticket (which is
  the right home for the spool-writer rename + default flip) will
  switch enqueue-capture.sh to the new canonical `trust_stage`
  name and flip the default to fail-closed.
- `fleet/capability/grades.py:481` and
  `fleet/benchmark/budget-derive.py:245-259` (NOT in `owns:`) —
  these are the consumers that gate on the trust axis. They
  already gate on `stage == "active"` in col 16; this ticket
  makes that filter MEANINGFUL for the first time. The
  `BUDGET-SOURCE-RECONCILE` follow-up handles the wider
  `_REAL_OUTCOME_SOURCES` divergence between grades.py and
  budget-derive.py (independent urgency).
- The versioned scorecard artifact (`scorecard.v{n}.json`) — its
  row schema does not currently carry a trust field. Adding it
  is out of scope and would cross into GRADER-SECFIX-RECONCILE
  territory (the `scorecard.v` artifact is its declared file).
- Fail-open defaults (the `_DEFAULT_TRUST_STAGE = "active"` and
  the `enqueue-capture.sh` default of `provisional` then `active`)
  are NOT flipped. That is `STAGE-FAILCLOSED`'s job and it must
  sequence with rig PR #99.

## Pre-existing gate state (for the reviewer)

`bash fleet/gate.sh`: **38 passed, 4 failed** with and without
my changes. The 4 failures are pre-existing and unrelated to
the trust axis (assign-dispatch, capture-wiring timeout,
deploy-session-end, and one more). I verified by stashing my
work and re-running — same 4 failures.

`ruff check`: 3 pre-existing errors (E701 in `_verdict_from_score`,
F841 in `_process_request` — both untouched by me).

`mypy`: 4 pre-existing errors (lines 141/145/149/294 — all
untouched by me).

`pytest -q`: 79 passed (same as baseline).

## Test_capture_pipeline.py:160-165 — scope conflict, NOT edited

The ticket body (`ds:`) names `fleet/tests/test_capture_pipeline.py:160-165`
as "reads-only (no owns claim, no edit)" but ALSO says
"expectation update expected — justify, don't delete". The launcher
`owns:` rule says I may only edit `fleet/benchmark/grader-daemon.py`
and `fleet/benchmark/selftest/test_stage_demux.py`. The `owns:` rule
wins, so I did NOT edit that test. The test STILL passes post-demux
because its FINAL request has `"stage": "active"` (legacy alias) and
the demux honors that — the assertion `r[15] == "active"` is
genuinely true. I record my justification for the expectation
update here, for the operator/reviewer to apply in a follow-up
PR or for whoever owns that file (likely a sister ticket to
GRADER-SECFIX-RECONCILE or a future test-hygiene ticket):

  JUSTIFICATION: pre-demux the test at :160-165 asserted
  `r[15] == "active"` for a row whose phase-1 spool sent
  `stage=provisional` but whose phase-2 spool ALSO sent
  `stage=active`. The assertion was vacuous — the daemon's
  hardcoded literal made the only possible value `active`,
  so the assertion proved nothing about stage handling. To
  make the test load-bearing, change the phase-2 request to
  send `trust_stage=provisional` and update the assertion to
  `r[15] == "provisional"`. The discrepancy logic (FALSE-SUCCESS
  note, score ≤ 20) is unchanged. That update is one line per
  site and is exactly what the ticket expected; it is blocked
  here solely by the `owns:` rule.

## Adversarial review: my own claim

The 3 fail-on-revert tests were specifically designed to be
load-bearing, not green-by-accident:

- **Test 1 (CORE)** uses the SAME request shape the on-the-wire
  pipeline uses: `pipeline.py:601` passes
  `stage = "provisional" if any_unsaturated else "active"` via
  `--stage` to `enqueue-capture.sh`, which writes it into the
  request as `d["stage"] = sys.argv[5]`. So the test exercises
  the REAL pipeline decision path end-to-end (via the e2e test
  in #5) and the daemon's resolution of the legacy `stage`
  field (via #4). Test 1 is the strictest possible assertion:
  provisional + real verdict → col 16 = provisional. Verified
  RED with the fix reverted.

- **Test 2 (active)** ensures the demux isn't an inverted
  hardcode (someone swapping the literal to "provisional"
  everywhere). A symmetric pair to test 1.

- **Test 3 (phase)** is the regression guard against the demux
  accidentally rewiring phase semantics. The ticket's third
  fail-on-revert clause is exactly this.

- **Test 4 (backward compat)** makes the demux safe to land
  without forcing a coordinated edit to enqueue-capture.sh.
  The follow-up STAGE-FAILCLOSED can rename enqueue-capture.sh
  at its leisure; the daemon already accepts the new name.

- **Test 5 (e2e)** drives the REAL `enqueue-capture.sh` script
  (not a Python mock) and proves the demux works against the
  actual spool writer, not just the daemon's internal API.

## Known pre-existing failures (NOT introduced by me)

`bash fleet/gate.sh` reports 4 pre-existing failures:
`assign-dispatch.test.sh`, `capture-wiring.test.sh`,
`deploy-session-end.test.sh`, and one more (search for
`summary: 38 passed, 4 failed` in the gate output). Verified
by stashing and re-running.

## Ledger proof the bug was real

(Re-quoting the ticket's own evidence; re-verified 2026-07-16.)

`fleet/model-scorecard.tsv` (this box): every `source=live` row
is `stage=active` — 45/45. ZERO provisional rows, ever. The
trust axis has never excluded a single row. This is
[[charon-meter-inert]] exactly: wired-looking, inert in
production.

## Decision summary

- Demux: implemented in the daemon. The on-the-wire `stage` is
  resolved as the trust value (legacy alias for the canonical
  `trust_stage`).
- Defaults: NOT flipped (STAGE-FAILCLOSED's job).
- Follow-ups sequenced: STAGE-FAILCLOSED, BUDGET-SOURCE-RECONCILE,
  WRITER-CHOKEPOINT, FALSE-SUCCESS-STAGE all remain distinct
  tickets.
- Gate: 38/4 unchanged, 79 pytest unchanged, no new failures
  introduced.
