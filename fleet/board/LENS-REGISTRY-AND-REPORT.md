repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: rig-meta
branch: feat/lens-registry-and-report
owns: fleet/state/lens-registry.tsv, fleet/lens-report.sh, fleet/tests/lens-report.test.sh
depends_on:
serial_justified: the durable lens store + its SessionStart/handoff surface + the every-N-done report are
  ONE anti-drift mechanism — a registry nobody surfaces, or a report that depends on manual recall, IS the
  "lenses get lost between sessions" gap this closes.
source: |
  operator directive 2026-07-24. Lenses (goal-grouped work threads spanning many tickets) get LOST
  session-to-session — they live in the manager's head + the chat, not durably. And the standing every-5-done
  lens/work report ([lens-work-report-cadence]) is MANUAL, so it gets forgotten — same failure class as the
  unsupervised grader-daemon (manual cadence = it dies). Seed store already written:
  fleet/state/lens-registry.tsv (6 lenses captured this session).
note: |
  Two parts, both mechanized (no manual recall):
  1. LENS REGISTRY — fleet/state/lens-registry.tsv (lens|goal|linked_tickets|status|why) is the durable
     GOAL-LAYER above the ticket board. Surfaced at SessionStart (the startup hook) + emitted by handoff.sh so
     a lens cannot be lost across sessions. Auto-discoverable by REGISTRY-META-CATALOG (matches *-registry.tsv).
  2. MECHANIZED REPORT — fleet/lens-report.sh fires the lens/work report every N (default 5) tickets DONE,
     driven off the done-counter (retire-done/done.sh markers), NOT the manager's recall. ANTI-STALENESS: a lens
     with no update across X sessions escalates (louder), so a stalled goal can't silently rot.
accept: |
  - lens-registry.tsv surfaced automatically at SessionStart (wired into the startup hook, not manual).
  - handoff.sh emits the active lenses into the handoff (a lens carries forward every session).
  - the report fires every 5 DONE tickets, MECHANIZED off the done-counter — proven by a test that closes 5
    tickets and asserts the report emitted (not a recall step).
  - anti-staleness: a lens un-updated across N sessions is flagged/escalated.
  - fail-on-revert: unwire the SessionStart surface -> the "lens visible at boot" test goes RED; break the
    done-counter trigger -> the "report every 5" test goes RED.
  - ADVERSARIAL REVIEW (reviewer != builder).
scope: |
  The durable registry + its SessionStart/handoff surface + the every-N-done report + anti-staleness. Does NOT
  decide lens CONTENT (the manager/operator curates lenses) — it PERSISTS and SURFACES them so they can't be
  lost. Reuses the existing report renderer if one exists (grep first; don't re-implement).
ds: |
  ## Dependencies & sequence
  P0. Pairs with REGISTRY-META-CATALOG (the lens-registry is one catalog entry) and ISSUE-BOARD-SURFACE (both
  are SessionStart surfaces — share the wire, don't duplicate). No hard prereq.
