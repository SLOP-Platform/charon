tier: strong
difficulty: 2
work_class: money-path
priority: 1
priority-why: |
  P:1 (assigned 2026-07-24; the field was ABSENT until then) — P:1 is "attached CG work, not huge,
  not over-dependent", which this is verbatim: money-path correctness in the LIVE gateway's cost
  meter (src/charon/gateway.py, one owned file), difficulty 2, one dep. NOT P:0 (not
  operator-escalated); NOT P:2 (it is attached to the CG, not a standalone blast-radius piece).
branch: feat/gateway-nontoken-metering
repo: charon
parent: PRICING-LIMITS-CHECKER
depends_on: PROVIDER-PROBE-FIX
real-dep: PROVIDER-PROBE-FIX owns src/charon/gateway.py (per its own real-dep note, alongside its
  F29 god-file-decompose blockers) — this ticket edits the SAME file's cost-metering path.
  Serialize behind it rather than run as a concurrent second writer of gateway.py; rebase onto its
  merge (and the F29 decompose it depends on) before starting.
gateway-py-handoff: |
  2026-07-26 — SW-STATIC-LEGS-RETIRE added ~11 lines to src/charon/gateway.py (load_config, approx
  :229-234) WITHOUT owning that file. Operator decision 31(a): landed anyway because the change is
  ADDITIVE (an explicit operator-intent filter for `enabled: false`, moved out of the routing-policy
  compiler where it was a silent membership drop) and does not rewrite anything this ticket touches.
  ROOT CAUSE: the SW-STATIC-LEGS-RETIRE brief forbade proxy.py and forwarder.py by name but omitted
  gateway.py, so the session had no stop-check to hit. Manager error, not session error.
  ACTION FOR THIS TICKET: rebase onto the landed change; do NOT assume gateway.py matches the version
  you started from. If the filter placement conflicts with your work, it is REVERSIBLE — the 11 lines
  are self-contained in load_config and the behaviour they preserve (/charon/disable honouring
  enabled: false) has test coverage in tests/test_static_legs_retired.py.
owns: src/charon/gateway.py
note: |
  Manually decomposed sub-ticket of PRICING-LIMITS-CHECKER (fleet/decompose.sh's plan_decomposition
  engine was unavailable 2026-07-15 — whole model pool 429/exhausted). Disjointness verified by
  hand: this ticket owns only the product-side live meter fix; PRICING-LIMITS-CHECK-SH (sibling)
  owns the unrelated rig-side offline drift checker + its TSV — zero file overlap between the two.
accept: |
  NON-TOKEN metering: NeuralWatt bills by ENERGY (kWh consumed per request, returned in its
  Usage&Energy API) -> the meter in gateway.py must PARSE that returned cost, not assume a fixed
  per-token price (today it records $0 for NeuralWatt responses). Extend the same parse path to be
  ready for other non-token billing shapes surfaced by PRICING-LIMITS-CHECK-SH's canonical table
  (flat-rate/seat, request-capped) without hardcoding NeuralWatt-only assumptions.
  Fail-on-revert: a fixture NeuralWatt response carrying a kWh/energy cost field -> the meter
  records the parsed dollar cost (non-zero, matching the source rate); revert the parse -> it
  falls back to $0 -> test fails.
scope: |
  Manually-decomposed single-domain sub-ticket of PRICING-LIMITS-CHECKER (fleet/decompose.sh).
  money-path; feeds the meter/ledger PRICING-LIMITS-CHECK-SH's table drives. PROJECT ROUTER.
