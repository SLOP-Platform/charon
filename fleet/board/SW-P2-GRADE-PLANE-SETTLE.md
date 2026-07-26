repo: charon
tier: frontier
difficulty: 3
work_class: design-review
priority: 1
branch: design/sw-p2-grade-plane-settle
depends_on:
owns: docs/adr/0017-outcome-graded-gateway.md
serial_justified: |
  Single-file decision ticket. It deliberately owns NO code: the code seams are already owned by two
  existing tickets, and adding a third writer is the redundancy this ticket exists to remove.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session (charon/* gateway model), NOT Claude.
  Graded run — record into fleet/model-scorecard.tsv under work_class `design-review`. Own git worktree.
source: |
  Switchboard-convergence investigation, 2026-07-26 (manager session). Authored as a DECISION ticket
  rather than an implementation ticket after a board scan found the implementation already twice-owned.
note: |
  ## THE VERIFIED GAP
  `src/charon/capability/` (grades.py, scorecard.py) is imported by EXACTLY TWO call sites in the
  product: `src/charon/lifecycle.py:316` and `src/charon/decompose_effort.py:265`. **Neither is the
  forwarder.** The forwarder's `capability_matrix` (built at `gateway.py:549`, consumed at
  `forwarder.py:388-398`) is FEATURE-SUPPORT — tool-calls, vision, reasoning-capable — it is not
  grading. So the live selection path routes with no quality signal at all.

  ## WHY THIS IS NOT AN IMPLEMENTATION TICKET
  Two LIVE board tickets already own that wiring, on TWO DIFFERENT PLANES:
  - `WIRE-GRADING-PRIOR-LIVE` (live, owns `src/charon/gateway.py`) — seeds the CapabilityMatrix from
    `grades_import.seed_matrix()` and connects real outcomes to `reconcile_with_real()`.
  - `GATEWAY-GRADE-ORDER-MVP` (PARKED, owns `capability/product_grades.py` + `routing_policy/grade_order.py`)
    — a grade-ORDERING overlay attached to **litellm.Router**, i.e. the adopted plane that does not serve
    traffic until `GW-CUTOVER-LIVE-WIRE` lands. That cutover ticket is itself PARKED and claimed.
  Writing a third ticket to "wire grades into the forwarder" would be WCI redundancy and would build a
  fourth grade path. The blocker here is not effort, it is that **nobody has decided which plane the
  grade overlay attaches to**, and one of the two candidates is blocked behind a parked cutover while
  the OTHER plane is the one actually serving live traffic today.

  ## THE DECISION TO MAKE (this is the deliverable)
  Determine, from the tree and not from the tickets, which plane serves live traffic at HEAD (state the
  ref), then rule:
  (a) forwarder plane is live and stays live for the foreseeable term -> grade ordering attaches to the
      forwarder; re-scope GATEWAY-GRADE-ORDER-MVP or supersede it, and say who owns forwarder.py for it;
  (b) litellm cutover is imminent -> confirm GATEWAY-GRADE-ORDER-MVP as the single owner, and state what
      unblocks GW-CUTOVER-LIVE-WIRE; or
  (c) both, with an explicit, written statement of which is authoritative and how they cannot diverge.
  Record the ruling in `docs/adr/0017-outcome-graded-gateway.md` — that ADR is the natural home and is
  owned by no other ticket.
accept: |
  DONE-CONTRACT (observable):
  - `docs/adr/0017-outcome-graded-gateway.md` names ONE authoritative attach point for grade-based
    ordering, with the ref it was measured on and the file:line of the live selection path it attaches to.
  - Exactly ONE live board ticket owns grade-into-selection afterwards. The other is superseded, parked,
    or explicitly re-scoped to a non-overlapping slice — stated by ticket ID in the ADR.
  - The ADR states how a capability GRADE differs from the existing feature-support `capability_matrix`
    (forwarder.py:388) so the next reader cannot conflate them again — that conflation is what let this
    gap sit open.
  - It also states the ADR-0011 tie: a grade is an input to "capable" in INV-SW3, not a separate ranking
    stage, or says why not.
  - `PYTHONPATH=src python3 -m charon.cli gate` GREEN (docs-only).
  - REVIEW BY THE OPERATOR before the superseded ticket is closed — an adversarial review must not
    silently overturn an operator-approved ticket (GATEWAY-GRADE-ORDER-MVP was operator-APPROVED
    2026-07-21); re-confirm rather than override.

## Dependencies & sequence

- **Depends on: NOTHING.** Startable immediately. It owns a docs file and touches no code.
- **Blocks:** whichever implementation ticket survives the ruling. Until this is settled, work on either
  candidate risks being thrown away — which is why it is authored FIRST and cheap.
- **Wave:** wave 1, PHASE 2. Fully CONCURRENT with SW-P2-CONTEXT-ADMIT, SW-P2-METER-OBSERVED and all of
  PHASE 1 — docs-only owns, disjoint from every code ticket in the wave.
- **Concurrency safety:** `docs/adr/0017-outcome-graded-gateway.md` is owned by NO other live board
  ticket (verified against the full `owns:` set of `fleet/board/*.md`, 2026-07-26). It is REFERENCED in
  GATEWAY-GRADE-ORDER-MVP's prose but not owned there.
- **Do NOT duplicate:** `WIRE-GRADING-PRIOR-LIVE`, `GATEWAY-GRADE-ORDER-MVP`, `GATEWAY-GRADE-ORDER-MVP`'s
  parent `GATEWAY-LITELLM-ADOPT`, and `SW-ADR0016-SETTLE` (which owns ADR 0011/0016, a different file
  and a different question).
