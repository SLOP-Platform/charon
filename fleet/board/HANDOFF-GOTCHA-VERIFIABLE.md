repo: charon-private
tier: strong
difficulty: 2
priority: 1
work_class: rig-meta
branch: fix/handoff-gotcha-verifiable
depends_on:
owns: fleet/handoff.sh, fleet/handoff-check.sh, fleet/tests/handoff-mechanize.test.sh, fleet/SESSION-HANDOFF-adi-gallia.md, fleet/end-session.sh
source: 2026-07-24 session audit of the live handoff (fleet/SESSION-HANDOFF-adi-gallia.md:238) —
  found a FALSE behavioural claim about fleet/land.sh that had propagated by copy through the
  handoff chain and was actively suppressing working tooling.
priority-why: |
  P:1 (attached CG work, not the keystone). This is attached to the live handoff-accuracy CG
  (HANDOFF-GATE-NONBYPASSABLE P:0 / RECONCILE-HANDOFF-FRESHNESS) — same file family, same failure
  class — and the code is already BUILT, so it costs the board one commit. It is NOT P:0 because it
  does not gate the landing queue (RIG-REDS-DISPOSITION does) and no session is blocked on it today;
  it is not P:4 because the defect actively suppressed a working tool for multiple sessions, which is
  more than a quick win.
note: |
  STATE: work is COMPLETE and STAGED in the worktree /home/stack/charon-private-wt/HANDOFF-GOTCHA on
  branch fix/handoff-gotcha-verifiable (5 files, +206/-5). It cannot be committed because the
  work-lease commit hook refuses any worktree branch that maps to no board ticket. This ticket exists
  to unblock that commit; it DESCRIBES what was built, it does not propose new design.
scope: |
  Kill a false claim that had been propagating through session handoffs, and mechanize the CLASS so
  the next one cannot propagate.

  THE FALSE CLAIM (verbatim, from the live handoff): "`land.sh` MERGES an existing PR — it does NOT
  create one. `gh pr create` first." It is FALSE: fleet/land.sh CREATES the PR itself
  (land.sh:395 `gh pr create --fill`), clears draft (land.sh:399 `gh pr ready`) and merges
  (land.sh:404 `gh pr merge`). THE COST: every session that inherited the handoff hand-assembled
  `gh pr create` + `land.sh` and repeatedly asked the operator for a PR-lifecycle tool that ALREADY
  EXISTED. An unverified assertion did not merely misinform — it suppressed working tooling.

  THE GENERATOR FIX (root cause, not the symptom): fleet/handoff.sh:199-210 — the gotchas preamble
  now (a) states the CLAIM-VERIFY rule inline so every generated handoff carries it, and (b)
  auto-emits the ACCURATE land.sh lifecycle bullet with its citations. Fixing the one live copy alone
  would have let the next generated handoff reintroduce the gap.

  THE ONE LIVE COPY: fleet/SESSION-HANDOFF-adi-gallia.md:238 corrected in place and marked
  `CORRECTED 2026-07-24`. Historical handoffs are DELIBERATELY UNTOUCHED — they are a record of what
  a session believed, not a spec; rewriting them would destroy the evidence trail.

  THE CLASS, MECHANIZED: fleet/handoff-check.sh grows a `[claims]` check. Rule — a gotchas bullet
  that NAMES a rig `*.sh` AND asserts behaviour about it MUST cite `<script>.sh:<line>`, where that
  line exists and is non-blank and non-comment. A bare backticked token is deliberately NOT accepted
  as evidence: the false claim quoted `gh pr create`, which DOES appear in land.sh, so token-matching
  would have "verified" the lie. Citing a line forces the author to open the script at that line.
accept: |
  - fleet/handoff.sh: generated gotchas preamble states the rule AND auto-emits the accurate
    land.sh:395/399/404 lifecycle bullet. (Generator-level fix — the reason this cannot recur.)
  - fleet/handoff-check.sh `[claims]`: uncited behavioural claim about a rig *.sh => exit 1;
    correctly cited claim => exit 0. Citations are resolved against the REAL script: a line past EOF,
    a blank line, or a comment line is a BAD CITATION (red). FAIL-CLOSED: missing rig fleet/ dir or
    missing awk => RED, never a silent skip.
  - NON-VACUOUS: a handoff whose gotchas section contains ZERO script-grounded claims exits 1
    `VACUOUS` — the check can never pass by examining nothing.
  - RATCHET, not retro-active rewrite: `CLAIM_EPOCH=2026-07-24`. A handoff dated BEFORE the epoch is
    announced `~ GRANDFATHERED` (announced, never silently skipped); dated ON/AFTER it is ENFORCED;
    a handoff with NO parsable date is RED (fail-closed — an undated handoff must not opt out).
  - FAIL-ON-REVERT (fleet/tests/handoff-mechanize.test.sh, EXTENDED — no new script, so it is already
    executed by fleet/gate.sh's `*.test.sh` glob): the red-proof asserts, by EXECUTION, that
    (1) the false claim => exit 1, (2) the corrected+cited claim => exit 0, (3) past-EOF citation,
    (4) comment-line citation and (5) missing machinery are all RED, and (6) zero claims => VACUOUS
    red. Revert the `[claims]` block in handoff-check.sh => the test goes RED.
  - fleet/end-session.sh: its generated "complete handoff" test fixture gains one cited gotcha bullet
    so the fixture still satisfies the now-non-vacuous [claims] gate (3 lines; see D&S for the
    shared-surface sequencing with SESSION-END-PUSH-GATE).
  - bash fleet/validate_board.sh stays GREEN.
known-open: |
  REPORTED, NOT FIXED (sub-finding of this work — do not silently drop it): handoff-mechanize's b2/c1
  cases fail on origin/master TOO, i.e. pre-existing and NOT caused by this change. Root cause: the
  `[sections]` gotchas needle `GOTCHA|avoid|DENIED` also matches text OUTSIDE the gotchas section, so
  a handoff with its gotchas section STRIPPED still satisfies the section check and the deletion goes
  undetected. Needs its own ticket (section-scoped detection); recorded here so the finding survives
  this branch landing.
ds: |
  ## Dependencies & sequence
  depends_on: NONE. Wave-1, claimable immediately; the code is already built and staged.

  CONCURRENCY SAFETY / owns:
  - fleet/handoff.sh, fleet/handoff-check.sh, fleet/tests/handoff-mechanize.test.sh and
    fleet/SESSION-HANDOFF-adi-gallia.md have NO other live owner on the board (verified 2026-07-24
    against every `owns:` line). Adjacent handoff tickets touch DIFFERENT files and are parallel-safe:
    HANDOFF-GATE-NONBYPASSABLE owns fleet/land.sh + fleet/checks/rig-ci-scope.sh (it makes
    handoff-check.sh RUN; this ticket changes what handoff-check.sh CHECKS — disjoint, composable in
    either order); RECONCILE-HANDOFF-FRESHNESS owns fleet/checks/reconcile-handoff-freshness.sh;
    HANDOFF-ROOT-ARCHIVE owns HANDOFF.md. No dep needed in either direction.
  - fleet/end-session.sh IS contended: SESSION-END-PUSH-GATE (live, queued) owns it. Sequencing is by
    MERGE ORDER, resolved on the OTHER ticket: SESSION-END-PUSH-GATE now `depends_on:
    HANDOFF-GOTCHA-VERIFIABLE`, because this branch is BUILT and one commit from landing while
    SESSION-END-PUSH-GATE is not started, and the two edits are in different functions (a 3-line test
    fixture here vs. the close-refusal logic there) so they COMPOSE rather than clobber. Putting the
    dep on the built ticket instead would block finished work behind unstarted work.
  - fleet/SESSION-HANDOFF-adi-gallia.md is the single LIVE handoff; historical handoffs are untouched
    by design, so no other session's file is in the blast radius.
