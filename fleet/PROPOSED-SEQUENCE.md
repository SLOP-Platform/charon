# Proposed Sequence — future-work backlog (concurrency-aware lanes)

> **WCI lives at two levels (2026-06-27):** the **RIG-level** WCI is **mechanized/enforced** now in
> `validate_board.sh` (WORKFLOW.md §4b) — not in this backlog. The **PRODUCT-level** WCI engine
> feature (Lane A: ADR-0015 → WCI-MVP → WCI-FOLLOWON) is **PARKED / DEFERRED until Charon is
> production-ready** per operator decision; it is shown below for lane context only and is NOT
> claimable now.

**Status:** DRAFT for operator sign-off. Nothing here is claimable — every item below is staged
as `board/<ID>.md.parked` (off the active board). This plan applies the WCI principle to our OWN
backlog: a `depends_on` is kept ONLY where it is a REAL build/correctness prereq, never for mere
ordering. Disjoint owns ⇒ no build-dependency (the exact TIER7B↔HARD1 / TIER7B↔WCI mislabel the
WCI reconciler is meant to catch).

Two INDEPENDENT lanes run in parallel. Gate types are labelled:
**[BUILD-DEP]** = real build/correctness prerequisite · **[SIGN-OFF]** = design approval gate ·
**[MERGE-ORDER]** = land-order only (never blocks the build).

---

## Lane A — infra (WCI composition layer)

```
TIER7B  [in-progress]
   ∥
ADR-0015 [DRAFTABLE NOW]  ──[SIGN-OFF: operator reshape sign-off]──►  WCI-MVP
                                                                        │  (builds ∥ TIER7B —
                                                                        │   owns are DISJOINT)
                                                                        ▼
                                                          WCI-FOLLOWON  [PARKED until §5.1]
```

- **TIER7B** — in-progress / operator-deferred Phase-B routing. Owns `router/api/adapters.acp/
  failover.py`. Not part of this drafting task; shown for lane context.
- **ADR-0015** — *draftable NOW*, concurrently with the TIER7B build. It is a DOC capturing the
  already-reviewed reshape; it needs no TIER7B code. Its only gate is **[SIGN-OFF]** operator
  approval of `DSGN-WCI-reshape.md`. Must LAND before WCI-MVP.
- **WCI-MVP** — gated on **[BUILD-DEP] ADR-0015** (don't build against an unsigned design).
  **Dropped its old `depends_on: TIER7B`** — owns are disjoint (`engine/{reconcile,scheduler,
  board}.py` vs `router/api/acp/failover.py`), so WCI-MVP builds **concurrently with TIER7B**
  once ADR-0015 is signed.
- **WCI-FOLLOWON** (WCI-4 + §5.1 + WCI-6) — **[BUILD-DEP] WCI** (extends the MVP layer) **plus
  [SIGN-OFF] §5.1 approval**. HELD per operator 2026-06-27.

## Lane B — dogfood / north-star (independent of Lane A)

```
PREFLIGHT [NOW]  ──►  DOGFOOD [NOW, after INTAKE1]  ──[informs]──►  DSGN-WRITEBACK
```

- **PREFLIGHT** — operator runs `charon setup` once. No upstream gate. De-risks DOGFOOD.
- **DOGFOOD** — gated on **[BUILD-DEP] INTAKE1 landed** (needs `charon intake import` +
  external-id). **NOT gated on TIER7B/WCI** (mock + acp run today). Own lane, starts as soon as
  INTAKE1 is on master. Exporter is OUT-OF-TREE (boundary, below).
- **DSGN-WRITEBACK** — gated on **the first DOGFOOD run** (its findings inform the design) +
  **[BUILD-DEP] INTAKE1** (transitive, via DOGFOOD). Closes the loop after dogfood.

---

## Per-item table

| ID | TYPE | depends_on (board) | Gate (kind) | Parked file | Review needed? |
|---|---|---|---|---|---|
| **ADR-0015** | design/ADR-pass | *(none)* | operator reshape sign-off **[SIGN-OFF]**; draft now | `board/ADR-0015.md.parked` | **NO** (light — transcribes an already-twice-reviewed design) |
| **WCI-MVP** (`WCI`) | droid-build | `ADR-0015` | ADR-0015 signed+landed **[BUILD-DEP]**; ∥ TIER7B | `board/WCI.md.parked` | **NO new design review** — MVP already cleared focused adversarial review; standard adversarial droid-PR gate at merge |
| **WCI-FOLLOWON** | droid-build (gated) | `WCI` | WCI-MVP landed **[BUILD-DEP]** + §5.1 approved **[SIGN-OFF]** | `board/WCI-FOLLOWON.md.parked` | **YES** — §5.1 proof contract must be specified + adversarially reviewed before it builds (F1 safety proof already exists) |
| **PREFLIGHT** | operator/out-of-tree | *(none)* | none upstream; run now | `board/PREFLIGHT.md.parked` | **NO** — manual operator step, no code |
| **DOGFOOD** | operator/out-of-tree | *(none)* | INTAKE1 landed **[BUILD-DEP]** | `board/DOGFOOD.md.parked` | **YES** — out-of-tree boundary (no SLOP/tracking.db leak into `src/charon`); blast-radius review |
| **DSGN-WRITEBACK** | design/ADR-pass | *(none)* | first DOGFOOD run **[informs]** + INTAKE1 **[BUILD-DEP]** | `board/DSGN-WRITEBACK.md.parked` | **YES** — design soundness of a new write-back/sink path + the out-of-tree boundary |

*(board depends_on is empty for operator/out-of-tree + design items because they have no
done-marker board ticket upstream; the real gate is stated in each note and above.)*

---

## Peak concurrency

Up to **THREE concurrent lanes of activity**:
1. **TIER7B build** (Lane A) ∥
2. **WCI-MVP build** (Lane A, once ADR-0015 is signed — owns disjoint from TIER7B) ∥
3. **DOGFOOD** (Lane B, operator-driven, once INTAKE1 lands)

Plus ADR-0015 *drafting* and PREFLIGHT can both happen even earlier, in parallel with TIER7B and
INTAKE1. The two lanes never share owns and never block each other.

## Out-of-tree boundary (loud)

DOGFOOD's SLOP exporter and DSGN-WRITEBACK's sink-writer **must stay OUT of `src/charon`**. The
product touches the SLOP world ONLY through the GENERAL `charon intake import` adapter (read) and
a future NEUTRAL `TicketSink` (write). Zero `tracking.db` / `query.py` / SLOP coupling in the
product. A stranger's `pipx install` never sees the home rig. (memory `product-vs-build-rig-boundary`.)
