# GATE-CREATION-STANDARDIZE — per-ticket review fragment

Ticket: GATE-CREATION-STANDARDIZE (charon-private; tier=frontier; difficulty=4; work_class=rig-meta)
Branch: feat/gate-creation-standardize

## What landed

Operator directive (cere-junda handoff): standardize HOW gates are created, driven by the
history of what GREEN gates missed — green-is-not-proof mechanized as a self-updating loop
(ledger -> standard -> meta-gate -> next miss appends the ledger).

- `fleet/state/GATE-GAP-LEDGER.tsv` — append-only, git-tracked ledger of green-gate misses.
  SEEDED with 8 researched historical misses (sources: fleet/session-notes/adversarial-
  delete-static-rank.md, SESSION-HANDOFF-cere-junda.md, docs/review-log/FOREMAN-WIRE.md +
  CONFIG-SSOT-PROPAGATE.md, board/archive/GATE-INTEGRITY-A/B, board/CATALOG-GATE-WIRE,
  validate_board.sh's own header history). Extracted CLASSES, not instances:
  `deploy-context-blind` (DELETE-STATIC-RANK: code green, deploy money-exposure),
  `no-gate-exists` (single-provider stiffness had NO detector),
  `self-report-lie` (FOREMAN-WIRE claimed wiring absent from the diff),
  `built-but-inert` (check_catalog_case_quant registered in no gate),
  `non-deterministic-gate` (inert-gate verdict flipped run-to-run),
  `multi-source-drift` (config-siloing; unreachable source = vacuous pass),
  `fail-quiet-pipe-mask` (validate_board's historic green-on-double-claim),
  `effect-not-verified` (land.sh false-DONE on unmerged PR).
- `fleet/GATE-CREATION-STANDARD.md` — the checklist a NEW gate must satisfy (S1-S10:
  red-proofed, non-vacuous, un-gamed, not-inert/wired, fail-loud, deterministic,
  context-of-validity, artifact-verified, verify-effect, class-coverage), with a
  machine-checked traceability map ledger-class -> standard-item, the mandatory APPEND
  step, and the wiring one-liners for the owners of validate_board.sh / the land path.
- `fleet/checks/gate-creation-standard.sh` — the META-GATE. `check` (hard, exit 1),
  `scan` (advisory, always 0 — validate_board-composable), `append` (validated ledger
  one-liner for the postmortem path). Composes existing lenses (gates.json red_proof
  contract, fleet companion-test convention, the ledger) — no per-instance scripts.
  Explicit FROZEN grandfather baselines (7 pre-standard gates.json ids without red_proof;
  4 fleet checks without companion tests; 1 without a set-line) — anything NEW must arrive
  proofed, and the baselines REDding on removal makes the node-set un-shrinkable.
- `fleet/tests/test_gate_creation_standard.sh` — 31 assertions, all passing. Core cases
  are FAIL-ON-REVERT: neuter any detection branch and the corresponding case exits
  green-when-it-must-be-red, failing the suite. Includes a LIVE read-only run proving the
  seeded state conforms (accept item 4 traceability) and a determinism double-run (S6,
  dogfooded on itself).

## Honest wiring status (S8 — the FOREMAN-WIRE lesson, applied to this very ticket)

`fleet/validate_board.sh` and `fleet/land.sh` are NOT in this ticket's `owns:` and were NOT
edited. The advisory wiring the accept text asks for is therefore NOT claimed here: the
meta-gate's `scan` mode detects and reports its own unwired state (`not-wired` advisory,
test 12c), and GATE-CREATION-STANDARD.md documents the exact one-liners for the files'
owners. No claimed wiring exists that is not in this diff.

Same for `.gitignore` (also not owned): `fleet/state/*` is gitignored, so the ledger was
tracked via `git add -f` — durable once tracked (ignore rules only affect UNTRACKED files;
future appends commit normally). The `.gitignore` owner should still add
`!fleet/state/GATE-GAP-LEDGER.tsv` beside the existing ROADMAP/REDS-CORPUS un-ignores so a
fresh re-add never needs -f.

## Scope self-check

`git diff --name-only master...HEAD` -> exactly: fleet/state/GATE-GAP-LEDGER.tsv,
fleet/GATE-CREATION-STANDARD.md, fleet/checks/gate-creation-standard.sh,
fleet/tests/test_gate_creation_standard.sh, docs/review-log/GATE-CREATION-STANDARDIZE.md
(this fragment — the lone allowed exception). All in `owns:`.

## Test summary

`bash fleet/tests/test_gate_creation_standard.sh` -> 31/31 PASS.
`bash fleet/checks/gate-creation-standard.sh check` (live) -> GREEN.
`bash fleet/validate_board.sh` -> unchanged (board untouched).
