repo: charon
tier: strong
difficulty: 2
work_class: ci-infra
branch: feat/gate-integrity-inert
depends_on:
owns: tools/check_inert_code.py, tools/inert-code-disposition.json, tools/inert_to_graph.py
note: |
  GATE-INTEGRITY sub-A (inert side). Split from the monolithic GATE-INTEGRITY (which the
  parallelizability-gate correctly refused as splittable). Full root-cause spec at
  fleet/state/S1-GATE-INTEGRITY-SPEC.md §2a/§3/§4 — READ IT FIRST. Do NOT edit
  tools/_vendor/ksf_inert_code.py (fix via a monkeypatch of _EXCLUDE_DIRS from
  tools/check_inert_code.py). Disjoint from sub-B (which owns gate_runner.py + check_gate_registry.py).
accept: |
  1. §3 determinism: extend _EXCLUDE_DIRS (via check_inert_code.py monkeypatch of the vendored
     module) to exclude .claude/ + local caches. The reds were LOCAL-tree pollution from ephemeral
     .claude/worktrees/agent-* copies swept into the AST scan — NOT real on a fresh clone.
  2. §2a: strip the stray `# @covers: inert-graph-coupling` line from tools/inert_to_graph.py (it's a
     diagnostic tool, no invariant/exit-code contract) — clears the check_gate_registry orphan-covers red.
  3. §4: apply the inert triage to tools/inert-code-disposition.json — DELETE ActualsLedger/ActualRow;
     keep-pending-wire (NOT delete) ReviewerCircuitBreaker/next_entry/proxy_excluded_keys; classify the rest.

  ## Accept
  - `PYTHONPATH=src python3 tools/check_inert_code.py` run 3x in a tree with .claude/worktrees/ present
    → deterministic, IDENTICAL counts + symbol lists all 3 runs.
  - The inert-code gate passes; no orphan-covers.

  ## Dependencies & sequence
  No depends_on. Disjoint file-ownership from GATE-INTEGRITY-B. Land first (B's full-gate-green
  accept assumes a deterministic inert scan).
