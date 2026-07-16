# GATE-CREATION-STANDARD — the standardized checklist a NEW gate MUST satisfy

Doctrine: **green-is-not-proof** [[green-is-not-proof]]. A gate that has never been seen
RED on a real failure proves nothing by being green. This standard is DERIVED from
`fleet/state/GATE-GAP-LEDGER.tsv` — the durable, append-only ledger of every time a GREEN
gate missed a real issue — and it is MECHANIZED by the meta-gate
`fleet/checks/gate-creation-standard.sh` (red-proofed by
`fleet/tests/test_gate_creation_standard.sh`). The ledger feeds the standard; the standard
feeds the meta-gate; the meta-gate blocks the next unproofed gate. Self-updating loop:
every future miss appends a ledger row, and a recurring class earns a checklist item here.

## Scope

Applies to ANY new or changed gate/check:
- a new entry in the product registry `tools/gates.json` (enforced via `gate_runner.py` / `charon.cli gate`),
- a new script under `fleet/checks/`,
- a material behavior change to either.

Anti-accretion: the meta-gate COMPOSES existing lenses (the gates.json registry contract,
the fleet companion-test convention, this ledger). Do NOT mint a per-instance checker
script for each new gate — the new gate's own red-proof test IS its evidence.

## The checklist (a new gate is NOT done until every item holds)

| # | Item | Requirement | Ledger class(es) it answers |
|---|------|-------------|------------------------------|
| S1 | **RED-PROOFED** | The gate has been demonstrated to go RED on a REAL failure (not a synthetic tautology). A committed fail-on-revert test proves it: revert/neuter the detection and the test fails. Product gates: `red_proof` field in `tools/gates.json` names the test file. Fleet checks: a companion test in `fleet/tests/` carrying a `red-proof`/`fail-on-revert` marker. | `self-report-lie`, `fail-quiet-pipe-mask` |
| S2 | **NON-VACUOUS** | The gate CANNOT pass on zero items, an empty scan set, or an UNREACHABLE data source. Absence of evidence is a RED, never a pass. (config-ssot-gate's unreachable-source RED is the reference implementation.) | `multi-source-drift` |
| S3 | **UN-GAMED** | The gate's node-set/baseline cannot silently shrink: removing a registered gate, dropping a scanned surface, or widening an exclude list must itself go RED (baseline floor / grandfather list is explicit and append-forbidden). | (green-is-not-proof corollary; guards every other item) |
| S4 | **NOT-INERT / WIRED** | The gate exercises the WIRED production path: registered where the runner actually looks (gates.json + gate_runner CHECKS; validate_board/preflight for fleet) and invoked by it. A detector that exists but is registered in no gate is a miss, not a gate. | `built-but-inert` |
| S5 | **FAIL-LOUD** | Non-zero exit on failure; `set -uo pipefail`; the verdict flag never lives inside a piped subshell (`| while`); no pipe-mask; the exit code — not the log text — carries the verdict. | `fail-quiet-pipe-mask` |
| S6 | **DETERMINISTIC** | Identical tree ⇒ identical verdict, 3x in a row. Hermetic input set: ephemeral dirs (`.claude/`, local caches, worktree copies) excluded explicitly. | `non-deterministic-gate` |
| S7 | **CONTEXT-OF-VALIDITY** | The gate declares what it does NOT cover (code vs DEPLOY vs live DATA). A code-green gate says nothing about the deploy that follows; money-touching deploys require their own data-preflight gate. | `deploy-context-blind` |
| S8 | **ARTIFACT-VERIFIED** | Acceptance is read from the ARTIFACT (the diff, the file, the wired path), never from the author's self-report/commit message. Verify the claimed wiring exists IN the diff. | `self-report-lie` |
| S9 | **VERIFY-EFFECT** | The gate asserts the EFFECT occurred (post-state: PR merged, file propagated, marker consistent) — not merely that a command exited 0. | `effect-not-verified` |
| S10 | **CLASS-COVERAGE** | Every ledger `root_class` maps to a checklist item here (machine-checked traceability), and every future green-gate miss APPENDS a ledger row. A recurring class with no gate gets one, or an explicit written waiver. | `no-gate-exists` |

## Traceability (ledger root_class → standard item)

Machine-checked by `gate-creation-standard.sh` (each ledger class slug must appear in this
document): `deploy-context-blind` → S7; `no-gate-exists` → S10; `self-report-lie` → S1+S8;
`built-but-inert` → S4; `non-deterministic-gate` → S6; `multi-source-drift` → S2;
`fail-quiet-pipe-mask` → S1+S5; `effect-not-verified` → S9.

## The append step (mandatory)

EVERY time a green gate later fails to detect a real issue:

```
bash fleet/checks/gate-creation-standard.sh append \
  "<gates that were green>" "<issue that shipped>" <root-class-slug> \
  "<gate improvement that would have caught it>" "<status>"
```

The helper stamps the date, validates the row (6 fields, no embedded tabs, class traced in
this standard), and appends to `fleet/state/GATE-GAP-LEDGER.tsv`. If the class is NEW,
first add it to the checklist table above (a new class = a new standard item or an
extension of one), then append. This is part of the land/postmortem path: any postmortem
that begins "the gate was green but…" ends with this one-liner.

## The meta-gate

`fleet/checks/gate-creation-standard.sh`:
- `check` — HARD verdict, exit 1 on any RED: unproofed new gate in gates.json (S1), missing
  red_proof file, baseline gate/check removed (S3), vacuous registry or ledger (S2), fleet
  check without a red-proof companion test (S1), fail-quiet fleet check (S5), malformed or
  untraced ledger rows (S10). Grandfather lists are EXPLICIT and frozen — pre-standard
  gates are named; anything new must arrive proofed.
- `scan` — ADVISORY (always exit 0), same findings prefixed `GATE-STANDARD-ADVISORY`,
  designed for validate_board-style composition; also reports its own wiring status
  honestly (see below).
- `append` — the validated ledger append helper (above).

## Wiring status (honest — per S8, no claimed wiring that isn't in the diff)

**NOT YET WIRED** into `fleet/validate_board.sh` or the land/postmortem path — both files
are owned by other tickets; this ticket does not touch them (per-ticket `owns:` rule). The
meta-gate's `scan` mode detects and REPORTS this state itself (`not-wired` advisory), so
the gap cannot be silently forgotten. Owners of those files: wire with:

- `fleet/validate_board.sh` — mirror the existing F46 parallelizability advisory block:
  run `bash fleet/checks/gate-creation-standard.sh scan` and surface
  `GATE-STANDARD-ADVISORY` lines as `wci`-style advisories (advisory FIRST per the ticket;
  promote `check` to RED after a soak period).
- land/postmortem path (`fleet/land.sh` or the postmortem runbook step): document/emit the
  append one-liner whenever a postmortem attributes an escape to a green gate.
