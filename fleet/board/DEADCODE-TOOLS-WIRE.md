repo: charon
tier: strong
difficulty: 2
work_class: ci-infra
priority: 0
branch: feat/deadcode-tools-wire
depends_on:
owns: tests/test_deadcode_tools.py
substrate: vulture + deadcode — adopt — both executed against 4 real corpora in the DEADCODE-TOOL-REDERIVE matrix (merged d90381d, EVAL-REGISTRY rows landed). Each emits classes NOTHING in our current stack (ruff F401/F841 + tools/check_inert_code.py) produces. This ticket WIRES the adopted tools; it does not re-evaluate them.
serial_justified: |
  vulture and deadcode are the same detection family over the same corpus and share one CI wire
  and one findings-budget mechanism. Splitting them ships two half-wired scanners and two
  competing baselines over an overlapping finding set.
execution: |
  Off-Claude via fleet-droid.sh, own worktree. PRODUCT repo (/home/stack/code/charon).
  Runs in PARALLEL with PYLINT-UNUSED-ARGS (disjoint: that ticket owns W0613 only).
source: |
  DEADCODE-TOOL-REDERIVE (merged d90381d). Operator 2026-08-01: rec #1 approved, then
  "I want the vulture/deadcode/pylint dispatched NOW ... fully wired, tested e2e dogfood."
note: |
  ## MEASURED FINDINGS TO WIRE (from the executed matrix — do NOT re-derive)
  | Class | Tool | Live count (product tree) |
  |---|---|---|
  | unreachable code after return/raise | **vulture** (100% confidence) | 1 — `src/charon/forwarder.py:934` |
  | unused class | vulture / deadcode DC03 | 4 |
  | unused method | vulture / deadcode DC04 | 61 / 64 |
  | unused property | vulture / deadcode DC08 | 3 |
  | unused attribute | vulture / deadcode DC05 | 14 (+3 in ksf) |
  | unused function | vulture / deadcode DC02 | 42 |
  | empty file | **deadcode DC11** | 0 in scope |
  None of these are produced by ruff or `check_inert_code.py` today.

  ## WHAT IS SETTLED — DO NOT REOPEN
  - vulture CANNOT replace `tools/check_inert_code.py`: it is reference-counting, and a
    mutually-referencing dead island (A->B, B->A, neither reachable) is MISSED by it and by
    deadcode, but caught by the reachability BFS. Both stay. This ticket is ADDITIVE.
  - Neither tool covers Bash — that is BASH-INERT-COVERAGE, separate and already in flight.

  ## SCOPE
  1. Add both as dev dependencies and wire them into the product gate/CI so they actually RUN.
  2. **Findings budget that SHRINKS ONLY.** ~125 existing findings is too many to fix in one
     ticket, so record a count and make CI fail when it RISES. A frozen baseline that reports
     green over 125 live findings is the fake-green class [[best-not-defensible]] — the number
     must be a ratchet, not a floor.
  3. Fix the ONE high-value finding outright: vulture's `forwarder.py:934` unreachable-code-after-try.
     It is on the money path; confirm whether it is dead code or a real logic bug and say which.
  4. Overlap: vulture and deadcode largely agree. Do NOT report the same symbol twice — dedupe,
     or run only the tool that covers each class best and record why.
  5. Config lives with the other tool config; no bespoke runner script.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
    a. A newly-introduced unused method/class/attribute makes the check RED. Revert the wire -> RED.
    b. A newly-introduced unreachable-after-return statement makes the check RED (the vulture-unique
       class — prove THIS one specifically, it is the reason vulture is here).
    c. The budget RATCHETS: findings above the recorded count fail; below it, the recorded count
       must be updated downward in the same PR.
    d. **It RUNS in CI** — prove it fires, do not merely add config. A configured-but-unrun linter
       is the inert class this whole programme is about.
    e. ANTI-OVER-BLOCK: `PYTHONPATH=src python3 -m charon.cli gate` stays GREEN overall, and ruff's
       existing F401/F841 behaviour is unchanged.
  Report before/after counts per class, and the verdict on `forwarder.py:934`.

D&S — Deps & Sequence:
  - Depends on: nothing. Product gate went GREEN at e4a70f0, so this is dispatchable now.
  - Parallel-safe with PYLINT-UNUSED-ARGS (owns a different test file, different rule set).
  - Do NOT touch `tools/check_inert_code.py` — it stays, and it is owned elsewhere.
