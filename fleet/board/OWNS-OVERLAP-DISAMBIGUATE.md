repo: charon-private
tier: frontier
priority: 0
difficulty: 5
work_class: rig-meta
branch: fix/owns-overlap-disambiguate
depends_on:
owns: fleet/state/OWNS-OVERLAP-DISAMBIGUATE.md, docs/review-log/OWNS-OVERLAP-DISAMBIGUATE.md
serial_justified: |
  A single global constraint over one namespace. Splitting it means two tabs reassigning
  ownership of overlapping path sets concurrently and producing a board that satisfies neither
  half — the exact contention this ticket exists to remove.
substrate: N/A
substrate-novel: |
  Nothing adopted or built. reconcile-merged.sh, validate_board.sh's owns-collision check and
  the substrate gate's base-ref ownership resolution all EXIST and are correct; they simply
  cannot decide when a path has many claimants. The novel slice is the ownership INVARIANT and
  the tie-break the reconciler can act on. No external tool encodes your board's ownership model.
accept: |
  ROOT CAUSE of the untracked pileup's largest feedback loop. Measured live 2026-08-02 from a
  full `fleet/preflight.sh` run.
  THE LOOP: a merged PR touching a multi-owner file makes reconcile-merged emit
  "AMBIGUOUS — a shared owned file cannot prove WHICH ticket landed — NOT auto-closing".
  So the ticket is never done-marked, stays LIVE on the board, and its stale `owns:` entry makes
  the NEXT merge of that file ambiguous too. It compounds: the more merges, the more live stale
  tickets, the more ambiguity. Retiring 5 already-merged tickets earlier today cleared 12 board
  REDs at a stroke — that is the size of the effect.
  MEASURED OVERLAPS (claimants per path):
    src/charon/forwarder.py            9
    src/charon/gateway.py              6
    pyproject.toml                     6
    fleet/checks/rig-ci-scope.sh       5
    src/charon/proxy.py                4
    src/charon/decompose_planner.py    4
    tools/inert-code-disposition.json  3
    src/charon/decompose_surface.py    2  (+ a long tail at 2-3)
  SECOND CLASS, same run: dozens of "has an UNRESOLVABLE repo: key — cannot prove which repo's
  master a merge would be in" (CONSOLE-PROVIDER-MGMT, DRAIN-ROUTING, MODEL-DISCOVERY,
  TIER-SELECT, WORK-LAND-PR, FB5/FB6/CI1/DEP1/N5 and more). These can never auto-close either.
  Done contract:
  1. Establish the INVARIANT: one live owner per path. Where several tickets legitimately need a
     file, express it as a dependency CHAIN (the fix already used for validate_board.sh:
     REPO-MAP-CONVERGE -> VALIDATE-BOARD-PATH-TRUNCATION -> PROJECT-MEMBERSHIP-GATE), not as
     parallel co-ownership.
  2. Give reconcile-merged a TIE-BREAK it can act on so it reaches a verdict instead of
     abstaining — abstention is what produced this backlog. Fail-closed: an unresolvable case
     must be reported LOUDLY as needing a human, never silently skipped.
  3. Fix the UNRESOLVABLE `repo:` class — every live ticket must carry a resolvable repo key.
  4. Enforce at WRITE time: a new/edited ticket introducing a live overlap without a dependency
     edge must RED in validate_board, so the invariant cannot decay again.
  5. Fail-on-revert on the write-time gate AND a retrospective run showing how many previously
     AMBIGUOUS merges now reach a verdict. That count is the acceptance evidence.

## Dependencies & Sequence

P0. No inbound deps. Ranked with the tool-utilization P0s because it is the same disease seen
from the board side: a mechanism that exists, is correct, and cannot act.
Sequence inside is strict — establish the invariant (1) BEFORE the tie-break (2), or the
tie-break gets written against a namespace that is still ambiguous and encodes the ambiguity.
The write-time gate (4) lands LAST, once the existing overlaps are resolved, or it reds the
board on day one and gets switched off — the failure mode already observed with the shellcheck
advisory ramp and with PROOF-SUITES-ENFORCE.

## CORRECTION 2026-08-02 — the premise is wrong, not just ambiguous

Measured after minting this ticket. Tested every AMBIGUOUS branch against every live ticket's
`branch:` field (drift-tolerant for -v2/-clean/-rebuilt): **NOT ONE of them is declared by any
live ticket.** They are `board/*` hygiene commits (which touch many tickets' files BY NATURE),
cross-cutting chores like `chore/gitignore-state-negations`, and old merges from tickets already
retired or renamed.

So reconcile-merged is not failing to disambiguate — it is asking a question that cannot be
answered. Its premise is "a merged PR touching this ticket's owned file is evidence that ticket
landed". **That premise is FALSE.** A board-hygiene commit editing 12 ticket files is not 12
completed tickets. File overlap is not evidence of completion; a declared `branch:` is.

CONSEQUENCE FOR THE FIX — do this instead of ownership-search:
 1. REQUIRE a branch->ticket declaration. A merged branch no live ticket declares is NOT a
    ticket completion: skip it, do not report it as ambiguous. This alone removes ~all of the
    hundreds of AMBIGUOUS lines and the preflight starvation they cause.
 2. Use file-ownership only as a CROSS-CHECK on the already-identified ticket, never as the
    search key.
 3. Tolerate branch drift (-v2/-clean/-rebuilt), or better: have land-push write the ACTUAL
    pushed branch back to the ticket so the declared value cannot drift from reality. Drift was
    the dominant real cause — 5 genuinely-merged tickets were invisible because they declared
    `branch: X` and merged as `X-v2`.
 4. The owns-overlap itself (forwarder.py 9 claimants, gateway.py 6, pyproject.toml 6) is STILL
    worth fixing for CONTENTION and for the substrate gate's ownership resolution — but it is
    NOT the cause of the reconciliation failure. Do not conflate the two.

EVIDENCE: the real backlog was 5 tickets (GITHUB-LIMITS-HARDENING, SESSION-END-PUSH-GATE,
SYNC-SCHEDULE, REVIEWER-TAB-POOL, SANDBOX-CONTAINMENT), all found by branch-drift matching and
retired in 1adbde8. Zero additional tickets were closable on file-ownership evidence, because
file ownership is not evidence.
