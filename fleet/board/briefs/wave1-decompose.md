# GATEWAY-ROUTING-DECOMPOSE (Wave 1) — deepseek-v4-pro — cwd: a worktree of /home/stack/code/charon
GOAL: extract the routing/provider-selection logic out of the god-file src/charon/gateway.py into a NEW
PACKAGE **src/charon/routing_policy/** — this MUST be a package, not a single file (red-team fix #1),
or downstream Wave-2 work cannot parallelize.

Produce these files (skeleton + interface stubs land FIRST so Wave-2 can pipeline against them):
- routing_policy/__init__.py        — exports the policy registry + abstract base
- routing_policy/base.py            — abstract Policy base class (the interface Wave-2 authors implement)
- routing_policy/matrix.py          — the (model x work_class) -> grade capability MATRIX schema
                                       (dataclass/TypedDict; the schema EXPLORE-PROMOTE + CAPABILITY-ENGINE consume)
- routing_policy/cost_rank.py       — stub (COST-RANK-AUTO lands here in Wave 2)
- routing_policy/drain.py           — stub (DRAIN-ROUTING)
- routing_policy/pools.py           — stub (POOLS-SIMPLIFICATION)
- routing_policy/spill.py           — stub (FREE-TIER-QUOTA-SPILL)
gateway.py keeps behavior IDENTICAL but DELEGATES its routing decision into routing_policy (pure refactor,
no behavior change). Do NOT implement the policies' logic — just move existing logic + define the seams.

OWNS (only these): src/charon/gateway.py, src/charon/routing_policy/ (new), tests/test_routing_policy.py
FAIL-ON-REVERT TEST: assert routing_policy is a package with the sub-modules above AND that gateway routing
delegates to it (test goes RED if the package is collapsed back into gateway.py).
NOTE: proxy.py/balance.py do NOT import gateway.py (coupling checked) — safe to run parallel to METER.

## CHARON-RUN CONTRACT (required)
End your run by writing a REVIEW PACKET (to REVIEW-PACKET.md in the worktree AND print it) containing:
- files + line ranges changed; root cause / approach
- the FAIL-ON-REVERT test: name + exact run command (must go RED if the change is reverted)
- self-run FULL GATE result: `PYTHONPATH=src python3 -m charon.cli gate` (paste pass/fail tail)
- residual risk + blast radius
- the commit SHA
LAST STEP (required): commit all changes on this branch and report the SHA.
Do NOT push or merge.
