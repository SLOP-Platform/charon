# RANK-0 — DO FIRST THING NEXT SESSION (refreshed 2026-07-22)

> Outranks the standard project ladder (ROUTER>BRIDGE>FLEET>SECURITY>BACKLOG) and P0-P4.
> **Process:** work runs in DETACHED off-Claude droids by default (`fleet-droid.sh <tier>`); the
> primary chat only does fast or would-degrade work. [[work-detached-first-token-lean]]
> **Model tier:** right-size per task — do NOT default to frontier. `economy`/`strong` for most;
> `frontier` ONLY for genuine architecture judgement. [[subsession-model-and-token-policy]]

## ✅ DONE this session (2026-07-22) — do NOT redo
- **Prior R0.1** — COVERAGE-META-GATE + SEMGREP + GITLEAKS + BANDIT (adopted as rig CI checks) +
  VULTURE (REJECTED with proof; kept the reachability `check_inert_code.py`). All merged (#140/143/144-147).
- **Prior R0.2** — grader hardening grafted (GRADER-SECFIX-RECONCILE) + live `shell=True` at
  `real.py:54` killed (GRADER-REAL-SHELL-INJECTION-FIX, argv/shell=False + fail-on-revert). Merged (#148/151).
- **Partial R0.3** — 5 merged rig tickets retired to archive (#154). Product code map re-generated (fresh).

## ⚠️ DROID POOL IS PARKED until new-R0.1 lands
The board is **72 open tickets and UNTRUSTWORTHY**: merged rig tickets don't auto-retire, so a droid
re-claimed already-merged BANDIT-ADOPT. Do NOT run a free-claiming `fleet-droid.sh <tier>` pool until
new-R0.1 fixes retire. Until then, PIN droids to named open tickets only.

## R0.0 (LEAD, operator-set 2026-07-22) — WORKLOOP-INTEGRITY-STACK-SPIKE (#156, on master)   [tier: strong]
The DURABLE fix for the whole built-but-not-wired / stale-board / gate-decay class is an ADOPT-FIRST
STACK, not piecemeal hand-rolls. Spike hands-on (evidence: `fleet/state/WORKLOOP-INTEGRITY-RESEARCH.md`
— deep-research, 3 picks verified real via GitHub API):
- **agent-orchestrator ("ao") FIRST** — the glue/feedback loop; make-or-break: does it drive our
  Gitea-primary + GitHub-mirror topology or is it GitHub-coupled? Point it at the local gateway.
- then **Omnigent** (meta-orchestration + policy gates + gateway-native), **Windmill** (durable stage
  automation — n8n REJECTED: no checkpoint/resume), **Archon** (DoD-enforcement harness; composes on ao?).
- PATTERNS to implement-not-install: GitHub merge queue (paid for the private rig; free on the public
  product), trunk-based two-gate DoD, K8s-style **reconciliation loop** (= the durable board-trust/auto-retire fix).
Deliverable = per-tool adopt/reject verdict + EVAL-REGISTRY row + one integrated adoption plan, for
OPERATOR REVIEW before any build. Process: detached off-Claude, right-size tier (not frontier by default).

> R0.1/R0.2 below are now **SUBSUMED by R0.0** (the reconciliation loop IS board-trust; the stack IS the
> inert-wiring enforcement). Kept as the interim-stopgap framing — a manual reconcile sweep keeps the
> board usable until the stack lands. Do NOT hand-roll them if R0.0 adopts a tool.

## R0.1 (subsumed by R0.0 — interim stopgap) — BOARD SELF-TRUST: repo-aware verify-merged / auto-retire   [tier: strong]
Fix the root that lets merged rig tickets stay claimable: `retire-done.sh` / `verify_merged` (`_lib.sh`)
hardcode the PRODUCT repo and never read a ticket's `repo:` field, so `repo: charon-private` tickets
NEVER verify-merge and never retire. Cluster: **VERIFY-MERGED-REPO-AWARE + REPO-FIELD-REQUIRED +
DONE-SH-INTEGRITY-FIX**. Then a one-time reconcile sweep of the ~20+ stale done-but-open tickets.
- **Why ZERO:** (a) actively costing (droids re-do landed work); (b) BLOCKS the detached-pool process
  the operator set as the ongoing default; (c) makes any prioritization of the 72-ticket board
  trustworthy; (d) it is the very decay class the operator escalated.

## R0.2 (new) — INERT-WIRING-ENFORCEMENT-DURABLE (#152, ticket on master)   [tier: strong]
Design-first root-cause of the recurring built-but-not-wired class (operator-escalated: "audits/fixes
that don't work over time"). Deliverable = `fleet/state/INERT-WIRING-ENFORCEMENT-DESIGN.md` (inventory
of every anti-inert gate + its ACTUAL enforcement state; WHY they decay; ONE decay-proof mechanism;
build backlog). Confirmed seeds: the PRODUCT inert gate IS wired+enforceable (public repo → `ci.yml`
runs `charon.cli gate` → `gate_runner.py` → `check_inert_code.py`); the RIG structurally CANNOT require
checks (private + free plan) — call that hole out. Unifies scattered R44/R45/INERT-INSTANCE-DETECT/
WORK-GATE-UNIVERSAL into one ENFORCED system. Operator reviews the design before any build.

## Prioritizing the rest (72 open tickets)
Do new-R0.1 FIRST (makes the board honest), THEN re-prioritize from a trustworthy board. The scattered
anti-decay tickets (R44 dogfood-gate, R45 inert-startup-check, INERT-INSTANCE-DETECT, WORK-GATE-UNIVERSAL)
should FOLD INTO R0.2's unified design, not be built piecemeal.

---
Refreshed 2026-07-22 (this session): landed prior R0.1+R0.2, retired 5 stale tickets, re-mapped the code
graph, and re-based RANK-0 on the operator-escalated decay class. Prior mace-windu evidence docs superseded.
