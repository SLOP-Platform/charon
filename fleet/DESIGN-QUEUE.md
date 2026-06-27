# Design Queue — manager-run design/reshape passes

These are **NOT droid build tickets.** They are features that need a design (or reshape) pass
BEFORE they can be turned into buildable board tickets. The manager runs each as the
design → adversarial-review loop (sub-sessions), produces an ADR + a build-ticket breakdown, gets
operator sign-off, THEN creates the board tickets. Kept off the droid board so no droid claims a
design task. Process per item: design sub-session → adversarial peer-review → synthesize → operator
sign-off → create build tickets.

---

## DSGN-WRITEBACK — close-the-loop: report completed work back to the source tracker

**Status:** queued (needs design pass). Sequence AFTER INTAKE1 lands.
**Why design first:** it's a new capability (a write-back/sink path), not yet specced.

**Discussed shape (2026-06-27) — the starting point, validate in the design pass:**
- A GENERAL, opt-in, gated `TicketSink` mirroring the read adapter. SLOP-specific write code stays
  OUT OF TREE (product boundary); the product ships a neutral sink the user configures.
- Do NOT auto-close. On completing a ticket, Charon marks the source item **in-review /
  pending-verify** and writes a **work trail** (PR link, the `accept` exit-0 proof, ledger/land
  record). The OTHER agent (e.g. SLOP robot-mode) or a human does the FINAL close after a
  sanity-check. Two-party handoff — matches Charon's propose-by-default doctrine (D006/D011).
- **Hard dependency:** the external ticket id must survive import — this is being built into
  INTAKE1 (the `id:` field). Write-back targets the source ticket by that id, so it cannot proceed
  until INTAKE1 lands.
- Fresh-user framing: same neutral sink for any user's tracker; no SLOP leak.

**Open questions for the design pass:** how aggressive is "mark in-review" vs leave-a-comment; how
the sink authenticates to an arbitrary tracker; idempotency on re-run; whether the work trail
format is generic or per-tracker.

---

## TIER-RECS — tier model recommendations for `charon setup` (CAPTURED — parked)

**Status:** captured, design approved by operator 2026-06-27 — staged `board/TIER-RECS.md.parked`
(not on the active board). Phased: Phase A (live `/v1/models` list at the selection prompt — cheap
immediate win, may ship first) → Phase B (LLM-judge ranks the live catalog into tiers, grounded +
intersected against the real `/models` list to kill hallucinated/stale ids) → heuristic fallback
(infer tiers from catalog metadata when no model is reachable). Activate after charon-vm bringup /
when setup-UX work is prioritized.

---

## DSGN-WCI — work-composition intelligence (RESHAPE; design + adversarial review already done)

> **TWO LEVELS — do not conflate (2026-06-27):**
> - **RIG-level WCI = MECHANIZED/ENFORCED now.** The work-composition invariants are mechanized in
>   `validate_board.sh` (the WCI enforcer — hard-gates false-blocking-dep + redundancy + owns-collision,
>   advises on semantic intent; see WORKFLOW.md §4b). The manager no longer applies them by hand.
> - **PRODUCT-level WCI (the engine feature below) = PARKED / DEFERRED** by operator decision until
>   Charon is **production-ready** (`board/WCI.md.parked`, `board/WCI-FOLLOWON.md.parked`). Do NOT build
>   now. When built it MUST be opt-in-orchestrator-only + advisory/override (never imposed on
>   gateway-only / single-task fresh installs).

**Status:** DEFERRED until production-ready (operator 2026-06-27). MVP staged as `board/WCI.md.parked`
(depends_on ADR-0015); WCI-4 HELD until §5.1 approved
(operator 2026-06-27); MVP = WCI-1+WCI-2. ADR-0015 pending; build after TIER7B + operator sign-off. The reshape
(`DSGN-WCI-reshape.md`) cleared the focused adversarial review for the MVP = WCI-1 (static
reconciler) + WCI-2 (depth pre-sort); WCI-6 (auto-slice) stays parked. Prior history: a design pass
AND an adversarial review were run this session — the original verdict was **REWORK**, answered by
the reshape. Do not build the original design; build the reshaped MVP only, after sign-off.
This is a CORE feature (see memory `charon-work-composition-intelligence`): three pillars — (1) no
duplicate/redundant/contradictory work, (2) maximize concurrency, (3) dependency-minimizing
chunking — productizing the manager doctrine into the engine.

**The adversarial review's REWORK findings to fix in the reshape (do NOT lose these):**
- **B1 — drop path-slicing as a safety claim.** Disjoint `owns` ≠ semantic independence
  (`assert_disjoint_waves` only checks file paths, not imports/calls). Pillar 3's static slice can
  ship silent breakage. Require a SEMANTIC independence proof before any slice, or keep the existing
  conservative-serialize.
- **B2 — concurrency tiebreak: depth as a PRE-SORT with id as the FINAL tiebreak** (not replacing
  id). Replacing lowest-id breaks the no-deadlock/determinism guarantee (depth isn't injective; the
  board has no acyclicity guard).
- **B3 — move LLM-judges OFF the scheduling/land hot-path.** Make them async/advisory, never gating
  `claimable`; preserve the board's diffable/replayable contract (LLM verdicts are non-deterministic
  and a fail-closed judge call would stall the whole drain).
- **B4 — relocate the on-merge reconciler to the scheduler `_advance` seam** (not `land.py`, a layer
  violation); the O(N²) static pre-filter as described doesn't actually tame the cost.
- **M1 — re-scope honestly:** the STATIC reconciler is ~70% a re-port of existing checks
  (intake.analyze + board.claimable + validate_board.sh). Only the SEMANTIC dedup/contradiction
  judgment is genuinely new.
- **M3 — injection surface:** feeding untrusted ticket text/diffs to an LLM judge re-opens the
  input-as-data boundary (ADR-0011 D3); needs explicit hardening.

**MVP per the (pre-review) design:** WCI-1 (static reconciler) + WCI-2 (concurrency tiebreak) — but
re-scope per M1/B2 above. Semantic/slicing (WCI-4/5/6) are the hard, gated, large parts.

**Live evidence the feature is needed:** even careful MANUAL ticketing this session introduced an
avoidable block (TIER7B `depends_on HARD1` was a merge-order mislabeled as a build dependency) —
exactly what the reconciler/chunker should catch.
