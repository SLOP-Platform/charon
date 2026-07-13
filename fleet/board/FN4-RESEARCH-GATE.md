tier: economy
difficulty: 3
work_class: ci-infra
branch: feat/fn4-research-gate
repo: charon-private
depends_on:
owns: /home/stack/charon-private/fleet/research.sh
accept: |
  Mechanized research/review/comparison protocol so no session repeats today's misses (missed Graphify =
  no reuse-check; trusted prose = no evidence gate). Composes existing primitives (reuse-check + KS32
  build-vs-adopt + KS29 registry + FN2 bi-temporal decay); mostly WIRING, not new invention.
  Launcher `fleet/research.sh <topic>`:
  - PRE-LAUNCH gate (dedup/staleness): consult the research registry → FRESH = return the prior record (no
    re-research); STALE = launch in UPDATE mode (refresh the record, don't redo from scratch); MISSING = full research.
  - METHODOLOGY injected into every research sub-session (enforced, not left to the prompt/recall):
    (1) REUSE-CHECK FIRST — search our repos / tools / memories / prior-research BEFORE external (catches the
        Graphify-in-house case); (2) EVIDENCE-OVER-PROSE — every feature/ability confirmed against REAL docs/code
        with a cited URL or path:line; unverified marked "unverified"; NO taglines/assumptions; (3) per-item verified cards.
  - POST-OUTPUT completeness gate (KS23 verification-delta shape): REJECT a research record that lacks a
    reuse-check section, contains uncited/prose feature claims, or is missing verified cards — only a passing
    record is written to the registry.
  - REGISTRY (KS29-style): each review recorded {topic, date, sources, verdict, freshness}; staleness via FN2.
  FAIL-ON-REVERT: (a) a research record with a fabricated/uncited feature claim → post-gate RED; revert the check → it
  passes (proving the gate bites). (b) `research.sh` on a fresh-topic returns the cached record WITHOUT launching a
  sub-session; on a stale-topic it launches UPDATE mode.
scope: Rig research discipline. Would have caught BOTH 2026-07-12 misses. Optional add-on (operator floated):
  min-source-count + a required adversarial second pass for high-stakes reviews — include as config flags.
ds: After FN1 (registry can live in the memory store) and reuses KS29/KS32/FN2 primitives. Owns new files
  (`research.sh` + a registry dir) → no owns-collision. Wave B of FOUNDATION.
