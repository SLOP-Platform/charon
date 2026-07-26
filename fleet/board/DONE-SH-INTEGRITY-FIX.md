repo: charon-private
tier: strong
priority: 2
difficulty: 2
work_class: rig-meta
branch: feat/done-sh-integrity-fix
owns: fleet/done.sh
depends_on: GITHUB-LIMITS-HARDENING, VERIFY-MERGED-REPO-AWARE
real-dep: VERIFY-MERGED-REPO-AWARE — shared single-owner of fleet/done.sh. That branch is ALREADY
  BUILT and pending landing (it rewrites done.sh's merge-verification path to be repo-aware); this
  ticket also edits done.sh. Single-writer sequencing — rebase onto it, never co-write.
  Added 2026-07-18 (board correction).
real-dep: GITHUB-LIMITS-HARDENING owns fleet/done.sh (batches its gh calls via gh-cache.sh).
  Rebase onto its merge; don't run as a concurrent second writer of the same file.
dep-kind: build
work_class_note: rig data-integrity — a false-close silently hides unmerged/unlanded work.
note: |
  OBSERVED 2026-07-15, two independent bugs in fleet/done.sh:
  (a) FALSE-CLOSE via loose owns-touch: ``merged_pr_touching_owns`` (done.sh, fallback path (c))
  accepts ANY merged PR — on ANY branch — that happens to have touched one of the ticket's
  ``owns:`` files, with no check that the PR is actually THIS ticket's work. DEDUP-ACTUALS-DELETE
  was wrongly marked done via this path while its own PR (#160) was still open, because an
  unrelated merged PR had touched one of its owns-listed files. The proof recorded
  (``merged:#<pr>``) names the WRONG PR.
  (b) repo-default bug: when a RIG ticket's board file has an EMPTY ``repo:`` field (not set to
  ``charon-private``), ``ticket_repo`` reads as empty, ``[ -n "$ticket_repo" ]`` is false, and
  ``REPO_SLUG`` silently stays at its top-of-script default (``SLOP-Platform/charon``, the
  PRODUCT repo) — so done.sh checks the PRODUCT repo's merged-PR history for a RIG ticket whose
  actual fix lives in the RIG repo. HANDOFF-PIPEFAIL was refused close on this path even though
  its fix was merged to charon-private master, because done.sh looked in the wrong repo.

  (c) ADDED 2026-07-26 (operator decision 8a, manager session kit-fisto) — CONSTANT GRADE SIGNAL.
  `fleet/done.sh:175` hardcodes `MERGE/pass/score=100` on every close. The scorecard therefore holds
  63 MERGE vs 1 BLOCK and the render shows 100% merge in 24 of 25 cells: the ledger records an
  OUTCOME that is not measured. Same integrity class as (a) and (b) — done.sh writing a value it did
  not verify — which is why this folds here rather than into a new ticket that would become a fifth
  concurrent writer of done.sh.
  Consequence: model ranking cannot discriminate. `SW-PHASE0-GRADE-READ` fixes the READ side (the
  >=3-strong-control filter that drops every row); without (c) that read returns a ranking computed
  over a constant, which is worse than no ranking because it looks authoritative.
  Scope for (c): derive pass/fail and score from the ticket's ACTUAL outcome (gate result / review
  verdict / whether the PR merged), and record BLOCK when it did not. Do not invent a scoring model —
  record what happened. Related: [[benchmark-not-a-valid-ranker]], [[scorecard-live-lane-is-the-ledger]].
accept: |
  (a) ``merged_pr_touching_owns`` (fallback (c)) is tightened to only match a merged PR whose
  HEAD BRANCH matches the ticket's recorded ``branch:`` prefix/pattern, OR whose PR title/body
  references the ticket id — never an arbitrary unrelated PR that happened to touch a shared
  file. If no branch/id-linked merged PR is found, done.sh REFUSES (same as today's "no proof"
  path) rather than accepting a loose file-touch match.
  (b) an EMPTY (or unset) ``repo:`` field on a ticket whose board file lives under
  ``fleet/board/`` (i.e., a rig ticket by location) resolves to ``charon-private`` by DEFAULT,
  not silently falling through to the product ``SLOP-Platform/charon`` default. (If the field is
  genuinely ambiguous, done.sh should warn loudly rather than guess wrong.)
  FAIL-ON-REVERT (fleet/tests, extend or add alongside done.sh's existing test coverage):
  (a) a fixture: ticket X's owns file touched by an unrelated merged PR on a DIFFERENT branch
  with no id/branch link -> done.sh REFUSES to close X (no false-close). A merged PR that DOES
  match X's branch/id -> closes normally. Revert the tightening -> the false-close test goes RED.
  (b) a fixture rig ticket with empty ``repo:`` -> done.sh resolves REPO_SLUG to the rig repo
  (charon-private), not the product default. Revert the default -> test goes RED.
  NON-VACUOUS: a fixture run that examined ZERO candidate PRs must REFUSE, never close — a matcher
  that proves nothing must not read as proof.
  RUNNER-REACHABLE: the red-proof must be EXECUTED by a real runner (fleet/gate.sh's
  ``fleet/tests/*.test.sh`` glob or rig-ci-scope.sh CI_SUITES) — a proof no runner runs is not
  evidence, and a ``test_*.sh`` name is matched by NEITHER runner.
  ``charon.cli gate`` / rig gate stays GREEN.
scope: |
  Data-integrity fix on the ONE mechanism that marks board work done and unblocks dependents. A
  false-close (a) silently hides real unmerged work from the board; a wrong-repo check (b) blocks
  a REAL close. Rig-only, no product change. Sequence behind GITHUB-LIMITS-HARDENING (same file).
ds: |
  ## Dependencies & sequence
  RESTORED 2026-07-24. A bundling pass had ABSORBED this ticket into MARKER-PROOF-MECHANIZE as its
  "LAYER 0". That was reverted: bundling means GROUP AT ONE PRIORITY IN ONE WAVE, not fuse two
  tickets into one serial branch. The pair is grouped in ROADMAP.tsv (project FLEET, wave
  `done-marker-integrity`, both `priority: 2`) and stays TWO tickets so two agents can work it.
  [[decomposed-by-design-not-reactive]] [[optimize-execution-wallclock-tokens]]
  depends_on: GITHUB-LIMITS-HARDENING and VERIFY-MERGED-REPO-AWARE — both REAL, both shared
  single-owners of fleet/done.sh; see the real-dep: lines. Rebase onto their merges; never co-write
  the file from a parallel branch.
  DOWNSTREAM: MARKER-PROOF-MECHANIZE `depends_on:` THIS ticket — it also owns fleet/done.sh, and
  requiring proof before the matcher is trustworthy would only harden a matcher that still names the
  WRONG PR. That edge is a genuine sequencing constraint, which is exactly why it is expressed as an
  EDGE and not as a merge of the two tickets.
  WAVE: rig-only; high-value now (prevents future false-closes / false-refusals like the two hit
  2026-07-15). CONCURRENCY-SAFETY: sole live owner of fleet/done.sh once its two deps land.
