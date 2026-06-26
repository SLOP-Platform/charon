# Charon — Decision Register

The **authoritative, concise index of settled decisions.** One row per decision; the
verbose reasoning lives in the cited ADR / REVIEW-LOG entry.

**Protocol (binding):**
1. **Every DTC / adversarial review MUST consult this register FIRST.** If a charge
   contradicts a `Settled` decision, the reviewer **flags it as "contradicts Dxxx" and
   surfaces it** — it does **not** silently re-decide or reconcile around it.
2. **Owner governs reopening.** A `Settled` decision owned by **OP** (operator) may be
   overturned **only with the operator's explicit re-confirmation** — never by a review on
   its own (see D011). An **AI**-owned decision may be revised on evidence; update the row
   and cite the new reasoning.
3. **New decisions append here** as part of the ADR / REVIEW-LOG flow. Superseded rows stay
   (marked `Superseded→Dxxx`) — never delete, so history stays auditable.

Owner: `OP` = operator strategic decision · `AI` = AI/plan call (evidence-revisable).
Status: `Settled` · `Open` (leaning noted) · `Superseded→Dxxx`.

| ID | Decision (one line) | Owner | Status | Source |
|----|---------------------|-------|--------|--------|
| D001 | Charon is **gateway-first**; the orchestrator/work-engine is an opt-in consumer on the shared core. | OP | Settled | ADR-0005 |
| D002 | Charon **owns the work-engine in-tree, sooner** — not external operator-tooling forever. | OP | Settled | ADR-0010, REVIEW-LOG 2026-06-26 |
| D003 | Engine workers are **ACP agents** (warm-poolable), **never `claude -p`**. The `charon-private/fleet/` rig is dev-box *build* tooling only; we port its coordination design, not its worker model. | OP | Settled | ADR-0010 (DTC 2026-06-26) |
| D004 | Split: **coordination substrate** (board/claim/scheduler) = build native; **trust-extending automation** (auto-land, scanner-as-required, intake Phase-2, AIMD) = stays gated. | OP+AI | Settled | ADR-0010, ADR-0007 |
| D005 | `WorkerBackend` port + headless-CLI/remote adapters = **deferred** until a real non-ACP worker exists (premature for an all-ACP product). | AI | Settled | ADR-0010 D2 |
| D006 | Landing is **propose-default** (PR, human merges); **auto-land (D5)** is deferred behind tripwires. | OP+AI | Settled | ADR-0007 D4/D5 |
| D007 | **Scanner matrix = lightweight/right-tools:** gitleaks + ruff-`S` always-on; shellcheck/actionlint change-triggered; semgrep opt-in deep-scan; osv/license off-by-default (stdlib core = no deps). Change-scoped + parallel + cached + **measured-before-required**. | OP | Settled | ADR-0010 D4 |
| D008 | The engine **scheduler drives each unit through the fenced `coordinator.run`** — never a second, unfenced dispatch path. | AI | Settled | ADR-0010 D2 (DTC Lens-2) |
| D009 | `claim` = **thin generalization of the ledger lock** + a monotonic **epoch** fencing token. No second locking subsystem; no heartbeat/remote-lease in v1. | AI | Settled | ADR-0010 D2 (DTC Lens-4) |
| D010 | Worker lifetime = **warm pool default** (reuse subprocess); ephemeral reserved for untrusted/L2+; pick the default by **measurement** (cold-start > ~15% of runtime → ephemeral loses). | OP+AI | Settled | ADR-0007 D7 |
| D011 | **A review/DTC must not silently override an operator (`OP`) decision** — surface it for re-confirmation. AI/plan decisions are evidence-revisable. | OP | Settled | REVIEW-LOG 2026-06-26, memory |
| D012 | The **container is the trust boundary**, not process-isolation or env-munging; the fence escape-scan is best-effort, not a boundary. L2+/untrusted = container-gated. | AI | Settled | ADR-0007 (security), ADR-0009 |
| D013 | Worker **sandbox posture** for any future non-ACP/uncontained worker: leaning **hybrid** (token-pair for trusted own-repo; container required for L2+/untrusted). | OP | Open (leaning hybrid) | DTC 2026-06-26 |
| D014 | **ADR-0008 Phase 1** (human-gated intake→plan) is buildable now (no tripwire); **Phase 2** (autonomous run) stays gated on the measured PR-conflict rate (D10-C). | OP+AI | Settled | ADR-0008, ADR-0010 |

<!-- Append new rows above this line. Keep each to ONE line; cite the ADR/REVIEW-LOG for detail. -->
