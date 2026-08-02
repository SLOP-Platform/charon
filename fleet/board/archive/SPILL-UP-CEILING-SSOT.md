repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: ci-infra
branch: fix/spill-up-ceiling-ssot
depends_on:
owns: fleet/state/TIER-CANON.md, fleet/tests/spill-up-ceiling-ssot.test.sh, docs/review-log/SPILL-UP-CEILING-SSOT.md
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
decided_value: |
  OPERATOR-DECIDED 2026-08-02: SPILL_UP_COST_CEILING = strong. Do NOT re-litigate the value;
  implement it. Rationale on record: a cost-driven hop economy -> strong is ALLOWED (that is the
  common case and the one starving the fleet), a hop strong -> frontier is REFUSED and detains
  with a ledger row, and frontier work still STARTS at frontier because tier is a capability
  floor. Frontier spend stays unauthorised while the meter is provably fiction in both directions
  (/data/spend.json reads 1185.44 for August against ~1.34 of measured real spend) and
  monthly_limit_usd is 0.0. Revisit ONLY after SPEND-METRIC-TRUSTWORTHY lands.
  Note this bounds COST-driven hops only — safety escalation out of a wholly HARD-detained band
  is deliberately unbounded and must stay that way (fleet-droid.sh:363-367).
escalation_note: |
  RAISED TO P0 2026-08-02: this is a contributing CAUSE of ZERO-COMMIT-SPIN (queue #1), not an
  independent defect. Measured today: 599 'cost-cap-config-invalid' rows in
  fleet/provider-exhaustion-ledger.tsv, one per claim, on every live tab. With spill-up disabled
  an exhausted cost band has no escape upward, so the claim dies before a session starts and
  loop-guard books it as a model spin.

## Dependencies & Sequence

No inbound deps. Independent of the P0 lanes; disjoint owns.

Pairs with LOOP-GUARD-REASON-WIRE and LIMIT-CLASSIFIER-TPM-WIDEN as the three-part fix for
ZERO-COMMIT-SPIN: this one removes a CAUSE of the zero-commit release, the other two stop an
infra fault from being MISBOOKED as model failure. Disjoint owns — all three can run in parallel
tabs. Land in any order.
