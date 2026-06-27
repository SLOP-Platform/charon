---
name: fb6-decisions-lint
description: FB6 review note — decision register lint + drift reconciliation
metadata:
  type: review
---

# FB6 — Decision register lint + drift reconciliation

**Date:** 2026-06-27  
**Ticket:** FB6 (`feat/decisions-lint`)  
**Theme:** THEME 9 — docs/decision-register governance has no mechanical backstop

## What was built

### `tools/check_decisions.py` (new)
Stdlib-only linter for `docs/DECISIONS.md` and the ADRs it cross-references.
Four checks:
1. **ID monotonicity** — flags gaps, duplicates, and out-of-order rows.
2. **Status enum** — `Settled | Open | Superseded→Dxxx`; anything else fails.
3. **Source token resolution** — ADR refs must point at real files; section refs
   (e.g. `D2`, `D-ESC-1`) must exist in the file; standalone `DTC <date>` tokens
   (no anchor document) are flagged as dangling; parenthesised annotations (DTC in
   parens after an ADR ref) are stripped before checking, so they don't false-fire.
4. **Register-Settled vs ADR-Proposed** — a `Settled` row citing a `Proposed` ADR
   is flagged.

`--check` mode: exits non-zero, prints count + list (CI-friendly).  
Default mode: human-readable bullet list.

Parser handles markdown `\|` escaped pipes inside cells (the D013 row uses them).

### `tests/test_check_decisions.py` (new, 11 tests)
Proven-red coverage: each defect category makes `lint()` return a non-empty list;
the clean case returns `[]`. Tests use temp directories with synthetic registers
and ADR files — no dependency on live docs.

## Drift reconciled

### ADR-0008/0009/0010: Proposed → Accepted
Engine code shipped under all three ADRs; following ADR-0006 precedent.

### D013: dangling `DTC 2026-06-26` standalone source
Fixed source to `ADR-0009 D-ESC-1, ADR-0010 D5` — the per-rung escalation gate
and the gated-items section that establish the container-required-for-L2+ posture
the sandbox policy encodes.

### D015: wrong order, off-enum Status, dangling source
- Moved from between D013/D014 to after D014 (monotonic order).
- Status `Open (deferred)` → `Open` (enum); "deferred" detail stays in decision text.
- Source `DTC 2026-06-26` → `ADR-0009 D-ESC-5` (the tokens-not-reachable-by-fenced-
  agent section, which is the formal home of the positive-verification direction).

### D007 text vs ADR-0010 D4 contradiction
D007 said "gitleaks + ruff-`S` always-on"; ADR-0010 D4 explicitly classifies ruff
as Tier B (change-scoped, Python diffs only). Source already cited ADR-0010 D4.
Fixed decision text to match its own source: "gitleaks always-on; ruff-`S`
change-scoped (Python diffs)".

### `tools/check_boundary.py` comment (L13-15, L85, L109)
Removed the "no-op while engine/ does not exist" language — the engine modules
(`board.py`, `claim.py`, `scheduler.py`, etc.) now exist and the code actively
enforces the constraint. Behaviour unchanged.

## DTC / adversarial note
No OP-owned decisions were overridden. D007's text was corrected to match its
own cited source (the operator directive in ADR-0010 D4). D013/D015 source fixes
point at real ADR text that was already written; no new design decisions were made.
