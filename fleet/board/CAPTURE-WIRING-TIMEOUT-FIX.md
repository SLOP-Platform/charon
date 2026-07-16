repo: charon-private
tier: strong
difficulty: 2
work_class: rig-meta
branch: feat/capture-wiring-timeout-fix
owns: fleet/charon-run.sh
depends_on: SALVAGE-STASH-CHARON-RUN
dep-kind: build
real-dep: both own fleet/charon-run.sh. SALVAGE-STASH-CHARON-RUN landed FIRST (rig PR #83, merged
  2026-07-16T01:18Z) — this ticket sequences onto its landed version rather than co-writing the file.
  Declared 2026-07-16: validate_board flagged the pair as a LIVE owns-collision with no dep ordering
  (and as WCI-redundant, identical owns sets). They are NOT duplicates — SALVAGE recovered the
  stashed charon-run timeout work; this ticket fixes capture wiring in the same file. The dep is
  already satisfied (state/done/SALVAGE-STASH-CHARON-RUN exists), so this does not block the claim.
  NOTE: SALVAGE should have been ARCHIVED off the board by retire-done.sh and was not — verify_merged
  (_lib.sh) hardcodes the PRODUCT repo and never reads a ticket's `repo:` field, so a `repo:
  charon-private` ticket can NEVER be merge-verified and never retires, leaving stale done tickets
  colliding with live ones. Ticketed as VERIFY-MERGED-REPO-AWARE; this dep is the local unblock.
dep-kind:
work_class_note: scorecard-integrity — a stray capture row skews real-outcome ranking data.
note: |
  OBSERVED 2026-07-15: fleet/tests/capture-wiring.test.sh RED (1 of 33 cases, confirmed by
  running the test): "timeout kill (rc=124) -> NO capture row (found
  /tmp/.../spool/capture-<model>-<TICKET>.active.<pid>.<ts>.json)". Every OTHER infra/provider
  fault (gateway 502, connection refused/reset, context deadline exceeded, sqlite locked, opaque
  rc=3) correctly produces NO scorecard capture row (infra fault, not model quality — see
  [monitored-preflight-failure-attribution]); a `timeout` wrapper KILL (rc=124) is the ONE
  infra-fault case that still leaves behind a stray ``.active.*.json`` capture-spool row instead
  of being suppressed the same way. charon-run.sh's own comments (SALVAGE-STASH-CHARON-RUN,
  EVAL-LATENCY-GATE) already disambiguate rc=124 into "provider pool exhausted" (infra, no
  capture) vs "model streamed output but ran out of budget" (model-attributable, DOES capture) —
  this ticket's failure is a THIRD sub-case: a bare kill with no signal either way still enqueues
  a PROVISIONAL row that's never finalized.
accept: |
  fleet/tests/capture-wiring.test.sh (already exists, do not rewrite it): a `timeout`-wrapper kill
  (rc=124) with no distinguishing "pool exhausted" or "streamed output" signal in the run log
  produces NO capture-spool row — same treatment as the other infra-fault cases, not a stray
  ``.active.*.json`` left dangling.
  FAIL-ON-REVERT: `bash fleet/tests/capture-wiring.test.sh` currently reports 32 passed/1 failed;
  this ticket is done when it reports 33/33. Revert the fix -> the timeout case goes RED again.
scope: |
  Scorecard-integrity fix in charon-run.sh's capture-enqueue path. Rig-only. A stray row here
  pollutes the real-outcomes ledger ([scorecard-live-lane-is-the-ledger]) with an
  unfinalized/orphaned PROVISIONAL entry.
ds: Now — rig-only, disjoint (charon-run.sh's only other board owner, SALVAGE-STASH-CHARON-RUN,
  is already DONE — no live owns-collision).
