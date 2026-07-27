repo: charon-private
tier: strong
difficulty: 2
work_class: rig-meta
priority: 0
branch: fix/pending-label-integrity
depends_on:
owns: fleet/pending.sh, fleet/tests/pending-labels.test.sh, fleet/state/OPERATOR-ACTIONS.md
serial_justified: |
  ONE invariant: "an operator-action label is unique and never reused". The allocator fix and the
  fail-closed delete guard are two halves of the same guarantee — shipping the allocator alone
  leaves the existing duplicate live and still destructive, and shipping the guard alone leaves the
  allocator free to mint new duplicates.
execution: |
  Built by the manager session directly (2-line class fix + hermetic test, cheaper to do than to
  brief out). Both reverts externally specified and red-proofed before landing.
source: |
  Found 2026-07-27 while acting on the operator's request to renumber the pending list. The
  "duplicate #12" was not a cosmetic numbering slip — it was a data-loss bug.
note: |
  ## THE BUG
  `fleet/pending.sh` promises in its own header that a label is "NEVER REUSED — once a label is
  handed out it is retired forever (monotonic high-water mark), so 'answer C' can never mean two
  different things over time."

  That promise rested ENTIRELY on `fleet/state/.operator-actions.hw`, which is **gitignored**
  (`.gitignore:10 fleet/state/*`), while the list it guards, `fleet/state/OPERATOR-ACTIONS.md`, is
  **tracked**. So any fresh checkout, clone, or state wipe lost the counter while KEEPING the live
  items, and allocation restarted at index 0 straight into labels that were still on the board.

  Observed: `#12` was carried by TWO items simultaneously (REAP FOLLOW-UP and SEED-PRIOR-REFRESH).

  ## WHY THAT IS DATA LOSS, NOT COSMETICS
  `cmd_done` deleted with `awk -F'\t' -v t="$up" '$1!=t'` — which removes EVERY row carrying the
  label. `pending.sh done '#12'` would have silently deleted BOTH operator actions. Red-proof
  transcript confirms it: with the guard removed, a 3-row list drops to 1 row on a single `done`.

  ## THE FIX (class, not instance)
  - `hw_effective()` derives the high-water floor as max(HW file, highest label present in the
    TRACKED list). The invariant now survives losing the gitignored counter — the root cause.
  - `cmd_add` additionally refuses to hand out any label currently on the board (belt and braces).
  - `cmd_done` FAILS CLOSED on an ambiguous label: refuses and deletes nothing rather than
    guessing which item the operator meant.
  - Existing data repaired: the later-appended duplicate relabelled `#12` -> `#13`, HW set to 38.

  ## RED-PROOF (both breaks externally specified, both watched RED then GREEN)
  - Revert 1 — restore the original `cmd_add` (bare `cat $HW`, no dedupe loop):
    cases (a) and (b) go RED: "add re-issued a live label: A" / "...: E".
  - Revert 2 — remove the `n -gt 1` guard in `cmd_done`:
    case (c) goes RED: "expected refusal with no deletion; rc=0 rows 3 -> 1".
  - Restored: GREEN (5/5).

  ## FIXTURE NOTE WORTH KEEPING
  The first version of this test was WRONG and passed against the broken code. A fixture holding
  only a HIGH live label (`#12` = index 37) does not reproduce the bug: losing HW restarts at "A",
  so no collision occurs. The live label must sit AT the index the broken allocator is about to
  hand out. This is why the reverts are run rather than assumed — a green test proved nothing until
  it was watched failing.

D&S — Deps & Sequence:
  - Depends on: nothing. `fleet/pending.sh` is unowned by any other live ticket
    (`grep -rn "owns:" fleet/board/*.md | grep pending.sh` -> no hits).
  - Blocks: nothing structurally, but every session surfaces this list at start, so a duplicated
    label is live operator-facing risk until it lands.
  - Sequence: independent of the three P0 tickets in flight (WORKER-LIFECYCLE-FIX,
    SESSION-BRIDGE-CONVERGE, CLAIM-RECONCILE-INERT) — disjoint `owns:`, no shared files.
