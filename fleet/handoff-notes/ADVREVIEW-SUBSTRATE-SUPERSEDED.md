# ADVREVIEW-SUBSTRATE-SUPERSEDED — does `feat/substrate-first-gate-v2` survive master?

**NOTHING-SURVIVES** — master's gate covers everything. The branch is a strict subset of master, lacks the `06b1764` fix entirely, and would regress it.

## Evidence

### What the branch gate IS vs master
- `fleet/checks/substrate_first_gate.py`: branch 793 lines, master 923 lines. The branch is a **strict subset**. Every line in the branch exists in a functionally equivalent or improved form in master. The 16 lines "unique" to the branch are all code master REPLACED (old `cmd_pr_has_ticket`, owns-collision without registry guard, old docstrings). Master has 146 lines the branch lacks — all of `06b1764` plus the registry-backed owns-collision guard.
- `fleet/checks/substrate-first-gate.sh`: **identical** (both 82 lines).
- `fleet/tests/substrate-first-gate.test.sh`: branch 395 lines, master 420 lines. Branch has 0 unique lines. Master added 25 lines (G9/R11 tests for owns-collision + valid registry match).
- `fleet/state/EVAL-REGISTRY.md`: branch 55 lines, master 123 lines. Branch is a strict subset. Master adds ~30 security/egress/guardrail eval rows + HAND-ROLL JUSTIFICATION ANTI-PATTERNS.

### Regression of `06b1764`
The branch's `cmd_pr_has_ticket()` is the **original version** that only checks for `fleet/board/*.md` in the same diff. Landing it would reintroduce uniform CI-RED across the feature-PR queue — the exact bug `06b1764` fixed. The branch lacks: `import fnmatch`, `parse_frontmatter()`, `_base_ref_tip()`, `base_board_owns()`, `_path_owned()`, and the updated `cmd_pr_has_ticket()` logic.

```
$ git show feat/substrate-first-gate-v2:fleet/checks/substrate_first_gate.py | grep -c "base_board_owns\|_base_ref_tip\|_path_owned\|parse_frontmatter\|fnmatch"
0
```

### "Nine adversarial evasions" — already closed on master
Proved by RUNNING three evasions directly against master's gate:
- **S1 (malformed alignment)**: RED — "BOGUS-alignment" correctly rejected
- **S2 (prefix matching)**: RED — "PyYA" does not match "PyYAML"
- **S3 (evidence placeholder)**: RED — "none" rejected as a citation

Proved by RUNNING the full test suite: **49 passed, 0 failed**.

```
$ bash fleet/tests/substrate-first-gate.test.sh
substrate-first-gate.test.sh: 49 passed, 0 failed
```

### Non-gate branch files
The branch has 9 files not on master (GH-SEAM-CHOKEPOINT.md, GRADER-SECFIX-RECONCILE.md, METER-DOC-RECONCILE.md, METER-KWH-USD-FIX.md, REPO-DECL-CENTRAL.md, RIG-CI-GATE.md, WORK-ROUTING-TO-CHARON-ENGINE.md, large-file-guard.test.sh, rig-ci-scope.test.sh). These are board tickets and test files unrelated to the substrate gate. None carry gate logic.

### No merge is safe
The three-dot diff shows these are add/add conflicts: the branch creates files that master also created independently (identical shell script, superset gate, superset tests). Any merge of the branch into master would produce conflicts including the gate file itself (branch's 793-line version vs master's 923-line version), plus the EVAL-REGISTRY conflict (55 vs 123 lines).

## RAN
- Master's gate against three evasion fixture tests (S1, S2, S3) — all caught correctly
- Master's full test suite: 49/49 passed
- Master's scan against live board — correctly flags 7 un-ticketed code files and 3 unparseable tickets
- `git diff --stat master...feat/substrate-first-gate-v2` confirms all gate files are new-on-branch
- `diff` between branch and master gate: branch is a strict subset (0 unique, 146 additions on master)

## READ
- Branch gate (793 lines) vs master gate (923 lines): branch lacks `06b1764` entirely
- Branch test (395 lines) — no unique lines, master adds 25
- Branch EVAL-REGISTRY (55 lines) — no unique rows, master adds ~68
- Branch shell script (82 lines) — identical to master
- `06b1764` commit and diff: the fix is substantial (~130 lines of new parser infrastructure)

## Disposition
Both `feat/substrate-first-gate` and `feat/substrate-first-gate-v2` should be abandoned. The 9 branch-only non-gate files should be evaluated independently if their tickets are still live, but they have no bearing on the substrate gate.

---

=== SESSION REPORT v1 ===
TICKET:       none (ad hoc review)
SESSION:      obi-wan-kenobi | deepseek-v4-pro
STATUS:       DONE
COMMIT:       none
FILES:        0 changed (read-only review, no edits)
OWNS-OK:      n/a — no edits made
GATE:         n/a — review task, no code written
TESTS:        n/a — ran master's gate test suite (49/49) as evidence, not changed
RED-PROOF:    broken=1 green=0 — three evasion fixtures (S1/S2/S3) tested against master's gate, all RED correctly
OBSERVABLE:   MET — gate output, test suite, git diffs all observable locally
RAN:          Master gate against S1/S2/S3 evasion fixtures + full test suite (49/49); three-dot diff master...v2
READ:         Branch gate is strict subset of master; branch lacks 06b1764 entirely (0 hits for base_board_owns/_base_ref_tip/_path_owned/parse_frontmatter/fnmatch); EVAL-REGISTRY is 55 vs 123 lines; test is 395 vs 420 lines
BRIEF-ERRORS: none — the prompt's framing was correct: both branches are superseded by master
BLOCKED-BY:   none
BUDGET:       ok
NEXT:         Abandon feat/substrate-first-gate and feat/substrate-first-gate-v2 branches. Evaluate 9 branch-only non-gate files independently if their tickets are still live.
=== END REPORT ===
