# ADR-0008 — Work intake → ticket-plan pipeline (the decomposition front door)

Status: **Accepted** (2026-06-26; Phase 1 shipped). Phase 2 tripwire: ADR-0007
**D10-C** (auto-decompose). Builds on ADR-0007 (work engine; consumer-supplied units),
ADR-0006 (decompose role-DAG). This is a queued skeleton — the failure contract + shape
are fixed now; the build waits for the tripwire.

## Context / why this exists
ADR-0007 ships with **consumer-supplied units** ("bring your own units"). Hand-authoring
units (a TICKETS.md) only works for people who code. To reach **non-coder users** — the
broader audience — Charon needs a front door that **inducts messy project input →
analyzes → emits a rule-abiding ticket plan** the engine can assign. Input is
heterogeneous and human: an LLM-generated bug list (`.md`), a project brief, an ADR
scope, an existing backlog. Output is a **unit list** (file-disjoint, tier-tagged,
collision-free waves) **plus a top-level acceptance for the whole product**.

## Two phases, split by risk
- **Phase 1 — intake → *human-reviewed* ticket plan (lower risk; may precede the D10-C
  tripwire).** Induct input → propose units + waves + tiers + owned-paths + a top-level
  product acceptance → run the mechanical safety checks → present a plan the human
  **approves/edits before anything runs**. The human gates the plan (exactly what the
  operator did by hand for TICKETS.md), so this is safe *without* the conflict-rate data.
  This is the non-coder front door.
- **Phase 2 — autonomous split→run (behind ADR-0007 D10-C).** Trust the plan enough to
  run *without* per-plan human review. Gated on the measured PR-per-unit conflict rate.

## Failure contract (guarantee + fallback per failure mode)
1. **File-overlap** (two units edit one file → collision): *structurally prevented* —
   every unit declares owned-paths; the decomposer detects overlap and resolves by
   **merge** or **serialize into a later wave**; never emits parallel units sharing a
   path. (The `coordinator.py` collision rule, mechanized.)
2. **Hidden inter-unit dependency**: *conservative over-serialization* — when
   independence can't be proven, add a dependency edge (serialize) rather than
   parallelize. A needlessly-serial plan is slow; a falsely-parallel one is broken.
3. **Mis-tiering**: *self-correcting + advisory* — a unit that fails acceptance at its
   tier **escalates** to a higher tier and retries (existing failover); cost bounded by
   SharedBudget. Not fatal.
4. **No executable acceptance check**: the unit is **propose-only** (cannot auto-land);
   flagged for human review. Every unit must carry a check — it is the safety basis.
5. **Vague input / scope explosion**: output is a **proposal a human approves**; bounded
   unit count; too-vague input → *"need more detail on X"*, never hallucinated units.
6. **Non-determinism**: the plan is a durable, **editable/diffable/auditable** artifact
   (a TICKETS.md/ledger entry), not an ephemeral call.
7. **Untrusted input → injection**: input is **data, not instructions**; the
   decomposer's output runs through the engine's propose-default + gated-land;
   decomposition **never auto-executes**; trust-tag the source.

**Non-coder division of labor:** the system runs the mechanical checks (overlap,
acceptance-presence, tier classification, dependency inference) and **surfaces issues in
plain language** — *"tickets 3 and 5 both edit `gateway.py`; merge or run in different
waves?"* — so the user makes the judgment calls with the dangerous ones flagged, not
blind trust.

## Intake must capture a top-level product acceptance
Decomposition is not done when it emits units — it must also capture **"what does the
whole product working look like"** as a checkable top-level acceptance, so the assembled
result can be validated against the original intent (ADR-0007 **D12** end-product
validation). Per-unit green ≠ product works.

## Open questions (resolve when built)
- Input adapters (md list / brief / ADR / GH issues) → a common work-item schema.
- Owned-paths inference (the hardest mechanical check): static analysis vs agent-proposal
  + verification.
- Dependency-inference heuristics + the over-serialization default.
- Review UX for non-coders (plain-language collision/tier/dependency surfacing).
