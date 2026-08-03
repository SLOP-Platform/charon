# EVAL-REGISTRY-DERIVE — design and implementation notes

## What was built

### 1. `fleet/checks/eval-registry-reconcile.sh` — the reconciler

A Python3-powered bash script that:
- **Generates** a deterministic `EVAL-INVENTORY.tsv` from committed live sources
  (pyproject.toml, graph.json, gates.json, TOOL-INVENTORY.md).
- **Joins** the inventory against `EVAL-REGISTRY.md`'s per-tool verdict rows.
- **Detects** three drift classes with evidence per finding:
  - **D1 UNEVALUATED ADOPTION** — tool in inventory, NO verdict row
  - **D2 STALE ROW** — verdict ADOPT/shipped, tool ABSENT from inventory
  - **D3 CONTRADICTION** — verdict REJECTED, tool PRESENT in inventory
- **Reports** alignment parseability: every alignment cell must start with one of
  `aligned|drifted|mixed|n-a` (optionally bold-wrapped). An unparseable cell is itself a RED.

Anti-silent design:
- NON-ZERO exit on any drift (1=drift, 2=unreadable input, 3=usage)
- Unreadable registry exits 2 with "FATAL" — never "no drift found"
- NEVER auto-edits EVAL-REGISTRY.md

### 2. `fleet/state/EVAL-INVENTORY.tsv` — derived tool inventory

Generated from:
- `pyproject.toml` — declared dependencies (core + optional)
- `graph.json` — imports actually present in product code
- `gates.json` — registered gate enforcers
- `TOOL-INVENTORY.md` — named tool references in the rig

Determinism: byte-identical on regeneration when sources are unchanged (no timestamp in output).
Verified: `sha256sum` matches across consecutive runs.

### 3. `fleet/tests/eval-registry-reconcile.test.sh` — red-proofs

Hermetic test suite:
- **T1** D1 proof: tool in gates.json with no registry row → RED, then GREEN after adding row
- **T2** D2 proof: ADOPT row with tool absent from inventory → RED, then GREEN after removal
- **T3** D3 proof: REJECT row with tool present in inventory → RED, then GREEN after verdict change
- **T4** Anti-false-positive: clean fixture → zero findings, exit 0
- **T5** Unreadable-input: missing registry → non-zero exit, "FATAL", never "GREEN"

## Baseline drift (2026-08-02)

On the current registry and inventory:
- **Registry rows**: 66
- **Inventory tools**: 64
- **D1 (unevaluated)**: 64 — all internal fleet scripts and gate enforcers, expected
- **D2 (stale)**: 21 — external tools with ADOPT verdicts not captured by our inventory sources
- **D3 (contradiction)**: 0
- **Alignment unparseable**: 0

The high D1/D2 counts are the finding, not a failure. Ratchet from here.

## What was NOT done (out of owns scope)

The following are in the ticket's scope description but require editing files outside
this ticket's `owns:` — these belong to separate tickets:

1. **L1 (creation)**: Extend `fleet/checks/substrate-first-gate.sh` to refuse unparseable alignment.
   File: `fleet/checks/substrate-first-gate.sh` — NOT in owns.

2. **L2 (CI)**: Add `eval-registry-reconcile.test.sh` to `CI_SUITES` in `fleet/checks/rig-ci-scope.sh`.
   File: `fleet/checks/rig-ci-scope.sh` — NOT in owns.

3. **L3 (cadence)**: Register on the cron alongside `stranded-work-cron.sh`.
   File: crontab — NOT in owns.

4. **L4 (escalation)**: Wire D3 contradictions and new D1 via `fleet/pending.sh`.
   File: `fleet/pending.sh` caller integration — NOT in owns.

5. **Alignment normalisation**: The reconciler DETECTS unparseable alignment cells but
   cannot EDIT `EVAL-REGISTRY.md`. File: `fleet/state/EVAL-REGISTRY.md` — NOT in owns.

6. **S2-GROUNDING-MECHANIZED.md items 4 and 5**: The file `fleet/state/S2-GROUNDING-MECHANIZED.md`
   does not exist in this repository. Cannot apply corrections from a non-existent source.

## Verdict

The reconciler, inventory, and red-proofs are built, tested, and working. The four wirings
(L1-L4) and alignment normalisation require follow-up tickets owning the respective files.
