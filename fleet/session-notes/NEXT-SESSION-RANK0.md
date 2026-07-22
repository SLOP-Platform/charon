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

## R0.2 — grader security ratchet (live defect) — SPLIT into two disjoint tickets 2026-07-22
The class-scan is done: `shell=True` has exactly ONE live rig site — `fleet/benchmark/graders/real.py:54`.
Crucially, **GRADER-SECFIX-RECONCILE does NOT own `real.py`** (it owns grader-daemon.py / reds_replay.py /
test_grader_daemon.py), so the reconcile alone leaves the live hole open. Hence two Priority-1 tickets:

- **R0.2a — GRADER-SECFIX-RECONCILE** (board: `GRADER-SECFIX-RECONCILE.md`; ROADMAP K3): weave the VERIFIED
  security hardening (`feat/bench-oob-grading @ e879957` — F1 _confine, F2 argv/shell=False, F5 false-green
  guard + 3 revert-proof tests) into the canonical grader, reconciling the two divergent lineages. Retire
  `feat/bench-oob-grading` once merged.
- **R0.2b — GRADER-REAL-SHELL-INJECTION-FIX** (board: `GRADER-REAL-SHELL-INJECTION-FIX.md`; ROADMAP K3S) —
  **NEW P1 ticket, operator-mandated 2026-07-22.** Kill the live `shell=True` at `real.py:54` (data-derived
  `check_cmd` with an untrusted `{worktree}` substitution). DISJOINT owns from R0.2a (owns `real.py` + a new
  selftest) so it can land independently; soft-sequenced AFTER R0.2a to reuse the F1/F2 pattern. Carries a
  fail-on-revert canary. Do NOT build concurrently with R0.2a (single-writer on `fleet/benchmark/`).

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
