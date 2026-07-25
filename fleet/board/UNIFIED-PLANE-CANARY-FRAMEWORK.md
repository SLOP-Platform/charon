repo: charon-private
tier: strong
priority: 5
difficulty: 1
work_class: rig-meta
branch: feat/unified-plane-canary-framework
owns: fleet/state/UNIFIED-PLANE-CANARY-REDIRECT.md
depends_on:
source: RENAMED/SUPERSEDED 2026-07-24 by SG-ISSUE-CONTROL-PLANE (operator-approved reshape). Kept as a
  thin redirect only because a live tab (strong-975076) claimed this id mid-flight.
note: |
  ⚠️ SUPERSEDED — do NOT build design here. This became SG-ISSUE-CONTROL-PLANE (the broader
  DISCOVER->SURFACE->SELF-HEAL control plane). The DESIGN IS ALREADY DONE:
  fleet/state/DESIGN-SG-ISSUE-CONTROL-PLANE.md. If you (a session) hold this claim: STOP re-doing the
  design, RELEASE this claim, and re-claim the real build slice ISSUE-BOARD-SURFACE (P0). Retire this
  redirect once the tab releases it.
accept: |
  - Session holding this: release claim + re-claim ISSUE-BOARD-SURFACE. Then manager retires this stub.
scope: |
  Redirect stub only. No work here.
ds: |
  ## Dependencies & sequence
  Superseded. See SG-ISSUE-CONTROL-PLANE + slices ISSUE-BOARD-SURFACE / KS29-DISCOVERY-LEG / ISSUE-SELF-HEAL-RULES.
