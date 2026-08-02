repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: ci-infra
branch: fix/inert-checks-wire
depends_on:
owns: fleet/state/INERT-CHECKS-WIRE.md, docs/review-log/INERT-CHECKS-WIRE.md
serial_justified: |
  Nine checks, one shared wiring surface (preflight/gate/CI registration). Wiring them in
  parallel means concurrent edits to the same dispatch points, which is the collision this
  ticket exists to remove rather than create.
substrate: N/A
substrate-novel: |
  Nothing adopted or built — the nine checks ALREADY EXIST and are already written. The novel
  slice is exclusively the wiring: making code that exists reachable from a real entrypoint.
accept: |
  MEASURED 2026-08-01 (fleet/state/OWN-TOOLS-CAPABILITY-AUDIT.md): 52 tools audited, 37 carry
  measurable unused capability, and **9 fleet checks are INERT — wired nowhere**. Plus:
   - `gate-integrity.sh scan` live: 39 findings, 3 NEW / 36 baseline.
   - G4 DOCUMENTED-GAP x2 at fleet/land.sh:361-362 — prose states leak-guard.sh and
     push-verify.sh are NOT wired. An acknowledged gap with no gate behind it decays into an
     accepted one; the finding IS the ticket.
   - `graphify affected` (blast-radius reverse traversal): **0 call sites** against 114 for
     `update`. We own the query that answers "what does this change break" and never call it.
   - 1 CLAIMED-BUT-ABSENT guarantee (Faktory exactly-once) is ALREADY CODED AGAINST — code
     depends on a property nothing provides. Treat as the highest-severity row.
  Done contract: for EACH of the 9 inert checks, either wire it to a real entrypoint with a
  fail-on-revert proof that it FIRES, or delete it with the evidence it is redundant. An inert
  check is worse than no check because it reads as protection. Do the same for the 2 G4 gaps
  (close the wiring or delete the stale note) and for `graphify affected` (wire it into the
  blast-radius path or record why not).
  Every "wired" claim must be demonstrated by making the check FAIL on a deliberate violation —
  registration alone is not proof, per the standing rule that a gate must be seen to fail.

## Dependencies & Sequence

P0, no inbound deps, disjoint from PROOF-SUITES-ENFORCE (that one governs which suites RUN;
this one governs which checks are REACHABLE). They may run concurrently in separate tabs.
Sequence inside: the CLAIMED-BUT-ABSENT Faktory guarantee FIRST — code already depends on it —
then the 9 inert checks, then the 2 documented gaps, then graphify affected.
