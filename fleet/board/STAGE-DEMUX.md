repo: charon-private
tier: strong
difficulty: 4
work_class: money-path
branch: feat/stage-demux
depends_on:
owns: fleet/benchmark/grader-daemon.py, fleet/benchmark/selftest/test_stage_demux.py
accept: |
  ADVERSARIAL REVIEW REQUIRED (money-path / trust): `stage` is the TRUST axis that decides whether a
  model's score may steer budget + routing. This ticket makes that axis real. A wrong call here ships
  untrusted scores into spend decisions.

  ROOT DEFECT: `stage` is OVERLOADED — it means two different things in two subsystems and nobody
  noticed. VERIFIED 2026-07-16, do NOT re-research:
    - SPOOL PROTOCOL (enqueue-capture.sh:46,123; the daemon) treats `stage` as a PHASE flag:
      provisional = "don't write the row yet", active = "write it now".
    - LEDGER COLUMN 16 (grades.py, budget-derive.py) treats `stage` as a TRUST axis:
      provisional = "collected, but must not steer a live number".
    - `pipeline.py:601` computes stage as a TRUST decision
      (`stage = "provisional" if any_unsaturated else "active"` — calibration debt) and passes it via
      `--stage`. The daemon reads that same field as a PHASE flag and then hardcodes the trust column.

  CONSEQUENCE (confirmed in code + in the ledger):
    - `fleet/benchmark/grader-daemon.py:410` hardcodes the LITERAL `"active"` into column 16 of every
      row it writes: `today, "live", ref, ..., "-", "-", "active",`. Confirmed by reading :405-415.
    - `_handle_capture` (grader-daemon.py:452) NEVER reads `req["stage"]` — confirmed: zero `stage`
      references in that handler. The pipeline's trust decision is SILENTLY DISCARDED.
    - Therefore NO CODE PATH can write a `source=live / stage=provisional` row. Only two outcomes exist:
      row dropped (no verdict), or row written **active**.
    - LEDGER PROOF (fleet/model-scorecard.tsv, re-counted 2026-07-16): **every `source=live` row is
      `stage=active` — 45/45. ZERO provisional rows, ever.** The trust gate has never excluded a single
      row. This is [[charon-meter-inert]] exactly: wired-looking, inert in production.

  DO:
    (a) DEMUX THE TWO MEANINGS. Split the spool's PHASE field from the ledger's STAGE (trust) field —
        two distinct names. Reusing one word for both is the entire bug; renaming one of them is the
        entire fix.
    (b) The daemon must PERSIST THE REQUESTED TRUST STAGE instead of grader-daemon.py:410's hardcode.
        A capture the pipeline marks provisional must land provisional.
    (c) SCOPE DISCIPLINE — do ONLY the demux. Do NOT flip the fail-open defaults (that is
        STAGE-FAILCLOSED's job, and it must sequence with rig PR #99), do NOT touch budget-derive.py's
        source allow-list (BUDGET-SOURCE-RECONCILE), do NOT edit the other ledger writers. This ticket
        makes the trust axis EXPRESSIBLE; the follow-ups make it correct.
    (d) CHECK FOR OVERLAP FIRST: rig PR #99 (TSV-APPEND-UNIFY, MERGED) made auto_append.py delegate to
        model-scorecard.sh and touched the dual appenders. Read what actually landed before you start —
        it moved the ground under this ticket's neighbours. If it already renamed a field, compose with
        it; do not re-litigate.

  FAIL-ON-REVERT (fleet/benchmark/selftest/test_stage_demux.py — REQUIRED, all three):
    (1) THE CORE ASSERTION (impossible today): spool a capture with `--stage provisional` AND a real
        `actual_verdict` -> the appended ledger row lands `stage=provisional` (col 16) and is EXCLUDED
        from grades/budget. Revert the daemon change -> the row lands `active` -> RED. No test in the
        tree asserts the daemon honors a requested stage; this is that test.
    (2) THE OTHER DIRECTION: `--stage active` + real verdict -> row lands `active`. Proves the fix is a
        demux, not an inverted hardcode.
    (3) PHASE STILL WORKS: a capture with NO verdict is still held (not written) regardless of trust
        stage. Proves the phase/trust split did not break the two-phase spool protocol.

  GREEN-IS-NOT-PROOF (explicit — there is a live example of this exact trap in this very subsystem):
  `fleet/tests/test_capture_pipeline.py:160-165` PASSES TODAY and asserts `r[15] == "active"` for a row
  whose note contains FALSE-SUCCESS (a caught model lie) — it ENSHRINES the unconditional hardcode. It
  passes for the WRONG REASON: its phase-1 spool sends `"stage": "provisional"` (:122) but ALSO omits
  `actual_verdict`, so the two correlate BY ACCIDENT and the test proves nothing about stage handling.
  That is why this gap has been invisible. Expect to UPDATE that test's expectation — but justify the
  change in the PR body rather than deleting the assertion. The wider suite is green with a trust axis
  that has never once fired across 45/45 rows, so green is zero evidence. Test (1) is the only bar:
  provisional + real verdict must survive to column 16. Reviewer: confirm test (1) goes RED with the
  :410 hardcode restored, and that no default was flipped (that is STAGE-FAILCLOSED, not this ticket).
scope: |
  Split the OVERLOADED `stage` field: spool PHASE (write-now vs hold) vs ledger column 16 TRUST
  (provisional vs active). grader-daemon.py:410 hardcodes the literal "active" into every live row and
  _handle_capture (:452) never reads req["stage"], so the pipeline's trust decision (pipeline.py:601) is
  silently discarded and NO code path can emit source=live/stage=provisional — ledger proof: 45/45 live
  rows are active, zero provisional ever. Makes BENCH-PROVISIONAL-SCORING (#20)'s accept true and must
  land BEFORE BENCH-OOB-GRADING (#26) rebases onto a trust axis that cannot fire.
  [[charon-meter-inert]] [[benchmark-not-a-valid-ranker]] [[scorecard-live-lane-is-the-ledger]]
  [[document-model-self-report-lies]] [[confirm-dont-trust-documentation]]
ds: |
  ## Dependencies & sequence
  depends_on: (none) — deliberately zero-dep so it can run NOW. It is the FIRST link in the frontier
    chain, not a follower.
  OWNS-COLLISION — MANAGER MUST READ (fleet/benchmark/grader-daemon.py has 3 declared owners):
    - GRADER-SECFIX-RECONCILE (LIVE, unclaimed) owns fleet/benchmark/grader-daemon.py +
      graders/reds_replay.py + selftest/test_grader_daemon.py. It depends_on BENCH-OOB-GRADING, which is
      PARKED — so it is NOT claimable today and cannot race this ticket in practice. It is sequenced
      AFTER this ticket via BENCH-OOB-GRADING (see the edge below), which is also why validate_board
      reports this path as a dep-sequenced hand-off rather than a live collision.
    - BENCH-OOB-GRADING (PARKED) owns `benchmark/grader-daemon.py` (rig-relative path form, so the
      validator's exact-string keying does NOT see it as the same path — the overlap is real regardless).
      This ticket adds `depends_on: STAGE-DEMUX` to that parked ticket to encode the required order.
    - I deliberately do NOT own selftest/test_grader_daemon.py (GRADER-SECFIX-RECONCILE's file) — this
      ticket adds a NEW disjoint test file, selftest/test_stage_demux.py, so the two never collide.
  real-dep: STAGE-DEMUX — (edge declared on BENCH-OOB-GRADING) #26's whole premise is that the OOB
    grader's verdict is what EARNS `active`, but the daemon writes `active` regardless of who graded, so
    #26 would land on a contract that cannot distinguish it. STAGE-DEMUX must land before #26 rebases.
  sequence: STAGE-DEMUX -> BENCH-OOB-GRADING (#26) -> MODEL-PREFLIGHT + GRADER-SECFIX-RECONCILE ->
    FINAL-E2E-REVIEW. Landing this unblocks the frontier chain.
  follow-ons (SEPARATE tickets — deliberately NOT in scope, do not build them here): STAGE-FAILCLOSED
    (flip fail-open defaults; must sequence with rig PR #99), BUDGET-SOURCE-RECONCILE (budget-derive.py:245
    admits bench/bench2, so synthetic S0-S6 scores steer real p95 spend TODAY — independently urgent),
    WRITER-CHOKEPOINT, FALSE-SUCCESS-STAGE. Source:
    fleet/session-notes/2026-07-16-evidence/bench-provisional-deepdive.md §6.
  overlap-check-required: rig PR #99 (TSV-APPEND-UNIFY, MERGED) touched the dual appenders
    (auto_append.py -> model-scorecard.sh delegation). Read what landed before starting; compose, do not
    re-litigate.
  reads-only (no owns claim, no edit): fleet/benchmark/item-bank/pipeline.py:601,897,
    fleet/capability/grades.py:481, fleet/benchmark/budget-derive.py:245-259,
    fleet/tests/test_capture_pipeline.py:160-165 (expectation update expected — justify, don't delete).
  concurrency: RUNS NOW. Owns one script + one NEW test; the only live co-owner of grader-daemon.py is
    blocked behind a parked ticket.
  wave: strong refill 2026-07-16. Frontier may claim down. HIGHEST-LEVERAGE item in this batch — it is
    the head of the blocked frontier chain.
  repo: charon-private (rig).
note: Created 2026-07-16 from fleet/session-notes/2026-07-16-evidence/bench-provisional-deepdive.md
  (implied ticket #1, "money-path, do first"). Zero-dep, READY NOW. ADVERSARIAL REVIEW REQUIRED.
  Must land BEFORE BENCH-OOB-GRADING (#26) rebases — that edge is declared on the parked #26 ticket.
</content>
</invoke>
