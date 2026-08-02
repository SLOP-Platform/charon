repo: charon-private
tier: frontier
priority: 0
difficulty: 4
work_class: ci-infra
branch: feat/eval-registry-derive
depends_on:
owns: fleet/checks/eval-registry-reconcile.sh, fleet/tests/eval-registry-reconcile.test.sh, fleet/state/EVAL-REGISTRY-DERIVE.md, fleet/state/EVAL-INVENTORY.tsv
serial_justified: |
  One reconciler over one registry. Splitting derivation from reconciliation would produce a
  generator nothing consumes - the precise failure class this ticket exists to end.
substrate: N/A
substrate-novel: |
  The DERIVATION substrate is already adopted and must be reused, not rebuilt - graphify owns the
  code map (fleet/TOOL-INVENTORY.md sec.1, graphify-out/graph.json, refreshed at every
  SessionStart), and tools/gates.json plus pyproject already declare gates and dependencies. No
  external tool models "reconcile our own tool registry against our own codebase", so the novel
  slice is the JOIN and its three drift predicates. Build no new scanner - if graphify's graph
  already answers "is this tool imported anywhere", consume it.
execution: |
  Off-Claude, SG tab. Build the reconciler and its red-proof. Do NOT rewrite the 67 existing
  verdict rows wholesale - reconcile them and REPORT drift. Mass-editing human reasoning is out of
  scope and would destroy the audit trail.
source: |
  Operator, 2026-08-02, verbatim intent - "EVAL-REGISTRY should get its rows from what we really
  have (code map etc) so as we add/remove tools it gets updated. I want the remaining work on
  EVAL-REGISTRY to be first priority. We need to make sure what we build is not fragile, can go
  stale/silent and is mechanized at all lenses."
note: |
  ## WHAT IS FRAGILE TODAY — measured 2026-08-02, all four verified
  1. **Hand-maintained and APPEND-ONLY by policy.** The file's own header says "This file is
     append-only". So a tool REMOVED from the codebase keeps its `ADOPT - shipped` row forever,
     and nothing ever contradicts it. The registry can only ever get more wrong.
  2. **The `alignment` column is FREE PROSE and no longer machine-readable.** A histogram of the
     column across 67 rows returns values like an entire paragraph beginning "mixed - the primary
     reason (stdio-only) is substantive...". A gate cannot key on that. So the one field the
     schema defines as the trust signal is unparseable.
  3. **SIX enforcement points read this file** - fleet/checks/substrate-first-gate.sh,
     fleet/checks/rig-ci-scope.sh, fleet/checks/reconcile-gate-wired.sh, fleet/preflight.sh,
     fleet/board-lock.sh, fleet/session-ctx-preamble.sh. Staleness therefore propagates directly
     into MERGE decisions, not just into documentation.
  4. **A missing row BLOCKS real work.** MEASURED today - a ticket was refused by
     substrate-first-gate with "has NO row in EVAL-REGISTRY.md. The consult-first rule requires
     one." The registry gates work, but nothing gates the REGISTRY.
  5. **It is effectively UNOWNED** - the only ticket owning it (TOOL-COMPOSITION-LAYER) is
     archived.

  ## THE SPLIT — derive what is derivable, never fake-derive a judgement
  A VERDICT is a judgement and cannot be generated. An INVENTORY can. Separate them -
    - **INVENTORY (DERIVED, regenerated, never hand-edited)** -> `fleet/state/EVAL-INVENTORY.tsv`.
      What we ACTUALLY have, from sources that already exist -
        * declared dependencies (`pyproject.toml` in both repos, keystone included)
        * imports actually present in code (graphify `graph.json` - the code map)
        * installed binaries the rig calls (`command -v` over fleet/TOOL-INVENTORY.md's list)
        * registered gates (`tools/gates.json`)
      Each row - tool, where-seen, evidence (file:line or command), first-seen, last-seen.
    - **VERDICTS (authored, unchanged)** -> `fleet/state/EVAL-REGISTRY.md` as today. Keep every
      existing row and its reasoning. This is the audit trail; do not regenerate it.
    - **RECONCILER (mechanized)** -> `fleet/checks/eval-registry-reconcile.sh`, the JOIN.

  ## THE THREE DRIFT CLASSES THE RECONCILER MUST DETECT — each is a real failure
    D1 **UNEVALUATED ADOPTION** - tool present in INVENTORY, NO verdict row. Something was
       adopted without ever being evaluated. This is the silent-adoption hole.
    D2 **STALE ROW** - verdict says ADOPT/shipped, tool ABSENT from inventory. The registry
       asserts we run something we do not. This is the stale-and-silent hole.
    D3 **CONTRADICTION** - verdict says REJECTED, tool PRESENT in inventory. We are running
       something we formally rejected. Highest severity; report it first.
  Report each with its evidence. D3 must never be auto-resolved - it needs a human.

  ## MAKE `alignment` MACHINE-READABLE
  Add a strict first token to the column - exactly one of `aligned|drifted|mixed|n-a` - with any
  prose AFTER a separator. Migrate the existing 67 rows by normalising the FIRST TOKEN ONLY; do
  not rewrite the reasoning. Then a gate can finally key on it. Assert parseability - an
  unparseable alignment cell is itself a RED.

  ## "MECHANIZED AT ALL LENSES" — the operator's words; all four are required
    L1 **CREATION** - the substrate gate already refuses a ticket citing a tool with no row. Keep
       it, and extend it to refuse a row whose alignment is unparseable.
    L2 **CI** - the reconciler runs on every PR and must be in the LITERAL `CI_SUITES` allowlist
       in `fleet/checks/rig-ci-scope.sh`. A suite outside it has NEVER executed in CI.
    L3 **CADENCE** - register on the SAME cron that already runs `stranded-work-cron.sh`. Do not
       build a scheduler. Verify BOTH legs - registered AND executing (heartbeat < 20 min old).
       A registered job that never runs reads as clean; that is the failure mode.
    L4 **ESCALATION** - D3 contradictions and any NEW D1 escalate via `fleet/pending.sh` so they
       reach the operator instead of scrolling past.

  ## ANTI-SILENT, ANTI-FRAGILE — non-negotiable
    - FAIL LOUD and NON-ZERO on drift. No `|| true`, no `|| return 0`.
    - A reconciler that cannot READ its inputs must exit NON-ZERO, never "no drift found".
      "Could not check" and "nothing wrong" must never be the same exit code - that exact
      confusion is documented in this rig twice.
    - NEVER auto-edit `EVAL-REGISTRY.md`. Detect and report; a human or an agent writes verdicts.

  ## ABSORB THE TWO OUTSTANDING CORRECTIONS
  `fleet/state/S2-GROUNDING-MECHANIZED.md` items 4 and 5 carry proposed diffs marked
  "NOT applied" - including the LiteLLM row whose stated reason ("supply-chain compromise") is
  flagged in the registry itself as unsubstantiated. Apply them or state why not. They are part
  of the remaining EVAL-REGISTRY work the operator asked to be finished.
accept: |
  a. `fleet/state/EVAL-INVENTORY.tsv` GENERATED from real sources, with the generating command
     recorded in the file header. Regenerating twice with no code change is byte-identical
     (determinism - a non-deterministic inventory produces phantom drift forever).
  b. `fleet/checks/eval-registry-reconcile.sh` detects D1, D2 and D3 with evidence per finding.
  c. RED-PROOF, one per class - a fixture where a tool is imported with no row -> D1 fires;
     a row claims shipped for an absent tool -> D2 fires; a REJECTED tool is present -> D3 fires.
     Each must be SEEN to fail, then pass when corrected. Registration is not proof.
  d. ANTI-FALSE-POSITIVE - a clean fixture produces ZERO findings and exit 0. A checker that
     always finds something gets muted, and a muted check is a dead check.
  e. UNREADABLE-INPUT PROOF - point it at a missing/corrupt inventory; it exits NON-ZERO with a
     distinct message, and does NOT report "no drift".
  f. `alignment` first-token normalised across all 67 rows, reasoning preserved, plus a
     parseability assertion.
  g. Wired at all four lenses (L1-L4), with the CI_SUITES entry and BOTH cron legs verified.
  h. Baseline recorded - the D1/D2/D3 counts on the CURRENT registry. Expect non-zero; that is
     the finding, not a failure. Ratchet from there.
  i. `bash fleet/validate_board.sh` GREEN.
scope: |
  Inventory generation, the reconciler, its red-proofs, alignment normalisation and the four
  wirings. Does NOT re-litigate any existing verdict and does NOT mass-rewrite reasoning.

## Dependencies & Sequence

- **depends_on: none.** Every input source already exists.
- **FIRST PRIORITY (operator-directed 2026-08-02).** Ranks above the BDD investigation lanes -
  those lanes must APPEND registry rows, and this ticket defines the shape they append into.
- Consumes graphify's code map. `GRAPHIFY-AFFECTED-WIRE` is SUBMITTED and unrelated - this needs
  the EXISTING `graph.json`, not `affected`. Not a blocker.
- Related but distinct - `fleet/checks/stranded-work.sh` finds work missing from GIT;
  `PRIORITY-DROPOUT-AUDIT` finds work missing from the LIST; this finds TOOLS missing from the
  REGISTRY. Same class, three surfaces. Reuse their reporting shape for consistency.
