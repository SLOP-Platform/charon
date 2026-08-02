repo: charon-private
tier: strong
priority: 1
difficulty: 3
work_class: ci-infra
branch: fix/spill-up-ceiling-ssot
depends_on:
owns: docs/review-log/SPILL-UP-CEILING-SSOT.md
serial_justified: |
  Single defect, single surface. Nothing to parallelise.
substrate: N/A
substrate-novel: |
  No tool adopted. The mechanism already exists and is misconfigured or mis-wired; the novel
  slice is the correction plus the assertion that keeps it corrected.
accept: |
  MEASURED 2026-08-02: fleet/fleet-droid.sh:259/276/386 reads SPILL_UP_COST_CEILING from the
  cost-band SSOT fleet/state/TIER-CANON.md. That file IS git-tracked (273 lines) but contains NO
  such key — grep -c returns 0. The launcher therefore FAILS CLOSED on every tab:
  'COST-CAP: no usable SPILL_UP_COST_CEILING ... cost-driven spill-up DISABLED (cost band X only)'.
  So a tab can never escalate out of an exhausted cost band. Fix the SSOT (define the key), not
  the launcher. Fail-on-revert: removing the key must re-disable spill-up loudly.

## Dependencies & Sequence

No inbound deps. Independent of the P0 lanes; disjoint owns.
