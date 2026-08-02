repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: ci-infra
branch: fix/gate-ownership-failopen-clean
owns: fleet/checks/substrate_first_gate.py, fleet/tests/substrate-gate-ownership-failopen.test.sh, fleet/tests/substrate_first_gate.test.sh
serial_justified: |
  One fail-open in one function (base_board_owns) plus its fail-on-revert suite, plus the board
  repair that the fix would otherwise turn from a silent false RED into a loud true RED for a
  fifth of the board. Splitting ships a gate that REDs everyone until the repair lands.
substrate: |
  PyYAML — ADOPT (already adopted, pinned 6.0.3, EVAL-REGISTRY row exists). This ticket adds no
  dependency and no second parser: the repair is verified with the gate's OWN
  substrate_first_gate.parse_frontmatter, and the gate fix only changes what the gate DOES with a
  TicketError it already raises. yamllint REJECTED on merit (style linter; the question here is
  parseability and error PROPAGATION, not style) — same verdict as BOARD-FRONTMATTER-GATE.
substrate-retest: |
  Not needed — PyYAML's ADOPT verdict is scoped to exactly this job (parsing rig board YAML) and
  this ticket introduces no new use of it beyond the call already at substrate_first_gate.py:104.
note: |
  Root-caused in fleet/state/GATE-DEFECT-OWNERSHIP-DIAG.md (commit f76af94).

  CLASS: FAIL-OPEN ON THE OWNER, FAIL-CLOSED ON THE OWNED. base_board_owns() did
  `except TicketError: continue` — a base-ref board ticket whose frontmatter fails the strict
  PyYAML parse was SILENTLY DROPPED, so its `owns:` paths never entered the ownership set. The
  gate then emitted the assertion "this change touches CODE owned by NO live board ticket",
  which is FALSE. The true statement was "a base-ref ticket owns these files but I could not
  parse it". A gate that drops evidence silently and then reports the absence of evidence as
  proof of absence. It also contradicted the module's own docstring: "A ticket the gate cannot
  parse is a RED, never a silent skip."

  MEASURED BLAST RADIUS on origin/master: 47 unparseable entries under fleet/board/ — 23 LIVE
  tickets (~21% of the board), 23 fleet/board/briefs/ files (empty frontmatter) and
  fleet/board/retired/FRAGILITY-TICKETS.md. Every branch whose only ticket was one of the 23 hit
  the same false RED — a standing push-blocker, and exactly the pressure that manufactures
  `--force` habits. Real victim: fix/shared-namespace-contention (PR #345).

  SECONDARY FAIL-OPEN in the same function: it filtered only "/archive/", so
  fleet/board/retired/ and fleet/board/briefs/ entries still granted LIVE ownership. Scope is now
  the same top-level shape the rest of the rig uses: ^fleet/board/[^/]+\.md$.

  Why no other gate caught it: every other owns-reader (_lib.sh ticket_owns, validate_board.sh
  field(), rig-ci-scope.sh _field, claim.sh, ladder-health.sh, reconcile-*) is a sed/awk LINE
  matcher and is blind to YAML validity. substrate_first_gate.py is the only strict-YAML
  consumer, which is why 23 malformed tickets sat on master with every board gate GREEN.
accept: |
  - base_board_owns() COLLECTS unparseable base tickets instead of dropping them, and
    cmd_pr_has_ticket NAMES them in a loud RED that says the gate could not read the board —
    never that the board is empty.
  - The retired/briefs fail-open is closed: only ^fleet/board/[^/]+\.md$ grants live ownership.
  - ANTI-OVER-BLOCK (the reason the unparseable RED is ordered LAST): an unparseable ticket can
    only ever ADD ownership, never remove it, so it can only change a NEGATIVE verdict. It is
    therefore surfaced as the RED on the negative path and as an INFO disclosure on the positive
    paths. A single malformed ticket must never wedge the whole fleet — nor the very PR that
    repairs the board.
  - `RIG_CI_ROOT=$PWD RIG_CI_BASE=origin/master RIG_CI_HEAD=origin/fix/shared-namespace-contention
    python3 fleet/checks/substrate_first_gate.py pr-has-ticket` prints the TRUE reason (the 23
    unreadable tickets) instead of the false "owned by NO live board ticket", and goes GREEN once
    the repaired board is on the base ref.
  - FAIL-ON-REVERT: fleet/tests/substrate-gate-ownership-failopen.test.sh FAILS when the
    `except TicketError: continue` is restored (asserts the gate REDs loudly NAMING the ticket,
    rather than falsely claiming no owner) and when the retired/ filter is loosened.

## Dependencies & Sequence

- **depends_on: (none).**
- **Branch name:** `fix/gate-ownership-failopen-clean`. The plain name was already published by
  RESCUE-PUSH-TOOL's at-risk sweep at an earlier, superseded shape; a fresh name is the rig rule
  for a re-derived branch rather than a force-push over someone else's rescue.
- **Sequence:** the GATE FIX lands FIRST and ALONE. The 23-ticket board repair is a SEPARATE
  branch (`fix/board-frontmatter-repair-23`) because repairing a ticket puts it in the PR diff,
  which DE-GRANDFATHERS it: `rig-ci-scope.sh:317` only substrate-checks tickets CHANGED in the
  diff, so 23 tickets that have never been in a diff since they were written fail the per-ticket
  content rules the moment they are touched (13 carry no `substrate:` field at all). Those are
  pre-existing content gaps belonging to their own owners — fabricating substrate verdicts for
  them would be exactly the dishonesty this gate exists to prevent. Splitting keeps that decision
  where it belongs and lets the fail-open close today.
- **Landing the fix WITHOUT the repair is safe** (this is why the order could be inverted): with
  the unparseable RED ordered last, no currently-green PR turns red. The only behaviour change
  for the 23 affected branches is that they now get the TRUE reason instead of a false one.
- **owns-collision:** none. No live ticket owned `fleet/checks/substrate_first_gate.py` or
  `fleet/tests/substrate_first_gate.test.sh` (the sibling suite, adopted here because
  `base_board_owns`'s return arity changed and its two monkeypatch lambdas had to follow — a
  2-line fixture change, no assertion touched; it stays 4/4 green).
  `fleet/validate_board.sh` is CONTENDED (rig-ci-scope.sh:11, REPO-MAP-CONVERGE et al) and is
  deliberately NOT touched. The authoring-time half of this class (write-time refusal of
  unparseable frontmatter) is BOARD-FRONTMATTER-GATE's, already in flight — this ticket stays out
  of `fleet/board-lock.sh` entirely. The two are complements: that one stops NEW breakage being
  written, this one stops existing breakage being silently swallowed.
