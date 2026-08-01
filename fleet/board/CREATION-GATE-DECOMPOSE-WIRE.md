repo: charon-private
tier: strong
priority: 2
difficulty: 3
work_class: rig-meta
branch: feat/creation-gate-decompose-wire
owns: fleet/checks/parallelizability-gate.sh, fleet/claim.sh, /home/stack/charon-private/fleet/validate_board.sh, fleet/tests/test_creation_gate_decompose.sh
serial_justified: One cohesive gate-timing fix — the gate script's placeholder-difficulty blind
  spot, its queue-entry wire point, and the board-validation hard-fail are one invariant
  (a splittable ticket must never reach claimable); splitting orphans the contract.
depends_on: PROJECT-MEMBERSHIP-GATE, PRIORITY-CONSOLIDATION, CLAIM-LIVENESS-BINDING
real-dep: CLAIM-LIVENESS-BINDING shares fleet/claim.sh and is P0 with an active need; this P2 sequences after it
real-dep: PROJECT-MEMBERSHIP-GATE owns validate_board.sh (adds project-membership checks); this
  ticket adds a hard-fail path to the SAME file. Rebase onto its merge, don't run concurrently.
dep-kind: build
work_class_note: rig safety/throughput; recurring churn cost (claim→refuse→re-claim→quarantine).
note: |
  OBSERVED 2026-07-15: fleet/checks/parallelizability-gate.sh (F46) is only invoked from
  fleet/fleet-droid.sh at LAUNCH time (fleet-droid.sh:196, inside the per-claim launch step) —
  confirmed by grep, it is NOT called from claim.sh, and validate_board.sh only runs it in
  `scan` mode as a board-wide ADVISORY (validate_board.sh:390-399, "Advisory ONLY here (never
  RED — never fails the board on its own)"). So a splittable/undecomposed ticket (difficulty>=3
  + >1 owned surface, not decomposed, not `serial_justified`) can be CLAIMED (claim.sh has no
  gate) and only fails reactively when fleet-droid.sh tries to launch it — releasing the claim,
  which the next idle same-tier tab immediately re-claims and hits the same refusal: churn ending
  in quarantine. Hit today on BENCH-OOB-GRADING after unpark.

  SECOND BUG (found investigating the above, added by coordinator mid-session): the gate's
  difficulty read (parallelizability-gate.sh:83, `field "$f" difficulty | grep -oE '^[0-9]+'`)
  strips a trailing `# auto-seeded from tier ...` comment but does NOT check for the sentinel —
  it treats a PLACEHOLDER auto-seed difficulty exactly like a refined one. BENCH-OOB-GRADING
  carries `difficulty: 5  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh` (a
  placeholder, not a real estimate) and the gate false-flagged it as splittable, causing the
  claim→refuse→quarantine churn on what is actually a genuinely-serial verification ticket
  (WORK-ROUTING-TO-CHARON-ENGINE carries the identical sentinel — also at risk).
accept: |
  - The parallelizability check is wired into the QUEUE-ENTRY path, not only launch: (a)
    claim.sh refuses to hand out a claim for a splittable/undecomposed/unjustified ticket
    (same PASS/FAIL semantics as the existing `check <id>` mode — reuse it, don't reinvent), and
    (b) validate_board.sh's board-wide scan is promoted from advisory-only to a HARD RED for any
    LIVE (non-parked) ticket that is splittable and neither decomposed nor justified — so an
    undecomposed splittable ticket can never even reach the claimable/live state undetected.
  - The gate does NOT fire on a placeholder/unrefined difficulty: a `difficulty:` value carrying
    an `# auto-seeded from tier` (or equivalently-marked sentinel) comment is treated as UNKNOWN,
    not as its numeric value — the gate does not hard-block on it, instead flagging it
    (`NEEDS-REFINEMENT`, non-blocking) so a human/decompose pass resolves the real estimate first.
  - fail-on-revert tests (fleet/tests/test_creation_gate_decompose.sh):
    (a) a splittable, undecomposed, unjustified ticket -> claim.sh REFUSES the claim (no churn);
        a decomposed (>=2 `parent:` children) or `serial_justified` one -> claim succeeds.
    (b) the same undecomposed-splittable ticket live on the board -> validate_board.sh exits RED;
        remove/decompose/justify it -> GREEN.
    (c) a ticket whose `difficulty:` carries the auto-seeded sentinel comment -> gate does NOT
        FAIL it (flags NEEDS-REFINEMENT instead); revert the sentinel-check -> test goes RED.
  - `bash fleet/validate_board.sh` GREEN (modulo pre-existing unrelated board state).
scope: |
  Closes the reactive claim→refuse→re-claim→quarantine churn loop by moving the check earlier
  (queue-entry, not launch) and fixes a false-positive source (placeholder difficulty). Rig-only,
  no product change. Blast radius: every future claim of a difficulty>=3, multi-surface ticket.
ds: Now — rig-only, high-recurrence churn cost; sequence behind PROJECT-MEMBERSHIP-GATE
  (validate_board.sh same-file).
