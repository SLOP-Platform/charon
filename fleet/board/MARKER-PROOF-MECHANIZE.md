repo: charon-private
tier: strong
priority: 0 # inherited: blocks a P0 ticket
difficulty: 3
work_class: rig-meta
branch: feat/marker-proof-mechanize
depends_on: DONE-SH-INTEGRITY-FIX, GITHUB-LIMITS-HARDENING, FOREMAN-WIRE, REPO-MAP-CONVERGE, BENCH-OOB-GRADING
real-dep: DONE-SH-INTEGRITY-FIX — shared single-owner of fleet/done.sh, and the DIRECT predecessor:
  it fixes how done.sh MATCHES proof (loose owns-touch false-close, wrong-repo resolution). This
  ticket fixes whether done.sh may write a marker with NO proof at all. Requiring proof before the
  matcher is trustworthy would only harden a matcher that still names the WRONG PR. Land that first,
  then require. Single-writer sequencing — rebase onto it, never co-write.
real-dep: GITHUB-LIMITS-HARDENING — also owns fleet/done.sh (routes its gh calls through
  gh-cache.sh). The write-time proof check calls the same gh seam; running as a concurrent second
  writer of done.sh would re-introduce the direct-gh call sites that ticket is removing.
real-dep: FOREMAN-WIRE — shared single-owner of fleet/preflight.sh. This ticket adds a new gate
  invocation to preflight; co-writing the same file from two branches is the multi-writer defect.
real-dep: REPO-MAP-CONVERGE — also owns fleet/preflight.sh AND fleet/checks/*.sh, the exact
  surfaces this ticket extends. Its repo-map check establishes the `repo:`-resolution the marker
  gate must reuse to decide WHICH repo a marker's proof sha belongs to; a marker gate that
  resolved the wrong repo would fail valid markers.
real-dep: BENCH-OOB-GRADING — owns `preflight.sh` (unprefixed) in the benchmark tree; declared to
  keep preflight single-writer even where the two owns strings do not textually collide.
owns: fleet/done.sh, fleet/preflight.sh, fleet/checks/marker-proof.sh, fleet/tests/marker-proof.test.sh, .gitignore
serial_justified: The three layers are ONE invariant ("a done-marker without proof cannot exist"),
  not three independent builds. Write-time refusal without the gate leaves the existing backlog
  unverifiable forever; the gate without write-time refusal fires on drift it cannot stop being
  re-created; and either without the audit trail (layer 3) is unreviewable — which is precisely why
  this went unnoticed. Splitting them ships a rule that gives false assurance, the same failure mode
  REPO-FIELD-REQUIRED called out. The fail-on-revert fixtures exercise write-refusal, gate-RED and
  trail-presence as a single invariant.
note: |
  A done-marker (`fleet/state/done/<id>`) is the RECEIPT that a ticket landed — it is what
  unblocks dependents and what retires a ticket from the board. `verify_merged` can check
  `merged:<sha>` or `merged:#<pr>`, but a large share of the ~177 markers present on 2026-07-19
  are BARE TIMESTAMPS with NO proof line and NO board file behind them — unverifiable BY
  CONSTRUCTION, not merely unverified. `done.sh` permits writing a proofless marker and nothing
  downstream ever objects.
  This is the SAME CLASS of defect that let REPO-DECL-CENTRAL be marked done while its code was
  never written [[gates-must-actually-run]] [[document-model-self-report-lies]]. A marker is
  self-reported success; the rig currently trusts it.
  ROOT CAUSE OF THE BLINDNESS: `fleet/state/` is gitignored, so markers have no history and never
  appear in review. The defect was invisible for as long as it existed.
  A backfill pass is running as of 2026-07-19 (`fleet/session-notes/2026-07-19-marker-backfill.md`)
  that adds proof to some existing markers. RE-MEASURE the backlog at build time — this ticket must
  NOT assume a fixed count, and no acceptance criterion may hardcode one.
accept: |
  LAYER 1 — WRITE-TIME (fleet/done.sh). done.sh REFUSES to write a marker unless it carries
  `merged:<sha>` or `merged:#<pr>`. An explicit `--override` remains possible for genuine edge
  cases (work landed outside a PR, historical reconciliation), but it MUST record a human reason
  string INSIDE the marker (e.g. `override-reason: <text>`) and MUST refuse if that reason is
  empty or whitespace. A proofless marker with no recorded reason must be IMPOSSIBLE to create by
  any code path — including the launcher auto-commit path.

  LAYER 2 — GATE (fleet/checks/marker-proof.sh, invoked from fleet/preflight.sh). Scans every
  `fleet/state/done/*` and reports each marker that (a) lacks proof AND lacks an override reason,
  or (b) has no corresponding board file (live, parked or archived). START ADVISORY (rc=0, prints
  the count and the offending ids), and RATCHET TO BLOCKING once the backlog reaches zero.
  REASONING (state it in the implementation too): a gate that goes RED on day one against a
  pre-existing backlog it did not cause blocks every launch and WILL be bypassed or disabled —
  which is how a gate stops actually running [[gates-must-actually-run]]. Advisory-first is
  explicitly NOT permanent: the ratchet must be MECHANICAL, not a follow-up ticket — the check
  flips itself to blocking the first time it observes zero violations and records that it has
  ratcheted, so the clean state cannot silently regress to advisory
  [[security-is-a-ratchet-gate]] [[never-ignore-preexisting-issues]].

  LAYER 3 — STRUCTURAL (.gitignore). Give markers an AUDIT TRAIL. There is direct precedent: ~20
  sibling state files are already exempted from the blanket `fleet/state/*` ignore and tracked.
  ASSESS COST HONESTLY and pick the NARROWEST option that yields a reviewable history — tracking
  the whole of `fleet/state/done/` is the high-noise end (a commit per ticket close, on a path
  every branch touches, i.e. a merge-conflict generator on a directory whose whole point is
  concurrent writes). PREFERRED unless measurement says otherwise: leave the markers themselves
  ignored and track a single derived, append-only ledger (e.g. `fleet/state/DONE-LEDGER.tsv`:
  ticket-id, proof, override-reason, timestamp) written by done.sh at the same moment it writes
  the marker and exempted via `!fleet/state/DONE-LEDGER.tsv`. One file, one line per close,
  linear history, reviewable in a diff — and it makes a marker that disagrees with the ledger
  detectable. Whichever option is chosen, RECORD THE REASONING in the ticket's review-log.
  NOTE the `.gitignore` state-exemption block is CONTENDED: PRs #47/#93/#96/#97/#107 each append
  their own `!fleet/state/...` line at the same anchor. Append, never rewrite the block, and keep
  every sibling exemption already present on master.

  FAIL-ON-REVERT (fleet/tests/marker-proof.test.sh — required, all three must go RED on revert):
  (1) done.sh invoked for a ticket with no discoverable proof and no `--override` -> REFUSES,
  writes NO marker, non-zero rc. `--override` with an empty/whitespace reason -> also REFUSES.
  `--override --reason "<text>"` -> writes the marker WITH the reason string in it. Revert the
  write-time check -> the proofless-write test goes RED.
  (2) a fixture state dir containing one proofless marker and one marker with no board file ->
  marker-proof.sh reports BOTH; with the backlog cleared it reports none AND has flipped to
  blocking (non-zero rc on a subsequently introduced violation). Revert the gate -> RED.
  (3) the chosen layer-3 artifact is actually tracked by git (`git check-ignore` does NOT ignore
  it) and done.sh appends to it on close. Revert the exemption -> RED.
  `bash fleet/validate_board.sh` and the rig gate stay GREEN. Do NOT run the full fleet/tests
  sweep (benchmark grader tests block for hours) — run the named suite.
scope: |
  Rig-only, no product change [[product-vs-build-rig-boundary]]. This is the integrity of the ONE
  mechanism that marks work done and unblocks dependents: an unprovable marker is indistinguishable
  from a fabricated one, and the board's entire dependency graph is downstream of it. Pairs with
  DONE-SH-INTEGRITY-FIX (proof MATCHING) — this ticket is proof EXISTENCE.
ds: |
  ## Dependencies & sequence
  depends_on: DONE-SH-INTEGRITY-FIX, GITHUB-LIMITS-HARDENING (both own fleet/done.sh);
  FOREMAN-WIRE, REPO-MAP-CONVERGE, BENCH-OOB-GRADING (all own preflight.sh). Every dep is a
  SHARED-OWNS single-writer sequencing dep, not a speculative one — see the `real-dep:` lines.
  WAVE: after the done.sh wave (DONE-SH-INTEGRITY-FIX, GITHUB-LIMITS-HARDENING) and the preflight
  wave land. Rebase onto master, never co-write a shared file from a parallel branch.
  CONCURRENCY-SAFETY: sole owner of fleet/checks/marker-proof.sh and
  fleet/tests/marker-proof.test.sh (both new — no other live ticket or open PR claims them, and
  branch feat/marker-proof-mechanize is unused). `.gitignore` is owned by no other live ticket but
  is CONTENDED by five open PRs (#47/#93/#96/#97/#107) at the same anchor — append-only, keep all
  siblings, expect to serialize. Do NOT start while any dep's branch is open on done.sh/preflight.sh.
