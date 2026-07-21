# RANK-0 — DO FIRST THING NEXT SESSION (operator-mandated 2026-07-21, mace-windu)

> These outrank the standard project ladder (ROUTER>BRIDGE>FLEET>SECURITY>BACKLOG) and P0-P4.
> The next session does RANK-0 work FIRST, before anything else. The handoff first-actions
> lead with this list. Do not let it drift (that is the whole point of ranking it ZERO).
> Operator confirmed ALL THREE below at ZERO.

## R0.1 — THE single move that kills all three standing concerns (operator's explicit ZERO)
Activate **COVERAGE-META-GATE** (ready; build `fleet/checks/rule-coverage.sh` + `fleet/state/RULE-REGISTRY.tsv`
by porting mediastack `enforcement_coverage.py` — TOOL-FIRST, do NOT rebuild) so every MANAGER-OPERATING-RULES
rule is classified `mechanized(<gate>) | guidance(<why>) | GAP`, **AND land the boarded tool-adapters**:
**SEMGREP-CI-REQUIRED-CHECK** first (unblocks the chain), then **GITLEAKS-ADOPT**, **BANDIT-ADOPT**,
**VULTURE-INVESTIGATE-RETIRE-INERT**.
- Why ZERO: one move resolves all three operator concerns at once —
  (1) shrinks the bloated loaded rules file (mechanizable rules migrate prose→gates),
  (2) enforces rules that were stated-but-unenforced (coverage gate was ticketed-never-built; RULE-REGISTRY files don't exist today),
  (3) does it WITHOUT hand-rolling (gates = thin ADAPTERS over industry tools, per KS31/KS32; custom only for novel classes).
- Bonus: this IS blast-radius blocker #3 (SEMGREP unblocks the SAST chain) and it fixes the
  **gitleaks false-coverage** security gap (config committed, ZERO enforcement today = a rule pretending to be a gate).

## R0.2 — GRADER-SECFIX-RECONCILE (live security defect — ratchet)
Kill the live `shell=True` command-injection on master (`fleet/benchmark/graders/real.py:54`), and per the §0
CLASS rule, class-scan for ALL other `shell=True`/injection sites — fix the class, not the one line.

## R0.3 — Reconcile-merged sweep (clears board drift so the session starts from TRUTH)
Close the **20 already-done-but-open** tickets the blast-radius audit found (RIG-CI-GATE #121,
SESSION-END-PUSH-GATE #130, +18; 6 carry stale done-markers). XS effort. Prevents re-working
already-done items — the single biggest time-sink this session.

## Then (P1, not ZERO)
Build/activate the drift primitive (KS24 lens-drift + KS29 registry-primitive) + adopt a GitHub
merge queue — the class-level fix for the stale-metadata/stranded-branch drift that dominated this session.

---
Evidence (scratchpad, this session): blocker-blast-radius-audit.md, drift-tooling-audit.md,
bench-oob-recon.md, SESSION-ISSUES-mace-windu.md. Consumed by the mace-windu handoff first-actions.
