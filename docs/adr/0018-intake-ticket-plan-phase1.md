# ADR-0018 — Intake → ticket-plan front door (ADR-0008 Phase 1, human-gated)

> Renumbered from 0011 (collision with the Switchboard ADR), 2026-07-19.

Status: **Proposed** (2026-06-26). Implements **ADR-0008 Phase 1** (the non-coder
front door) and **ADR-0010 build-seq step 4**. Builds on ADR-0007 (`land.py` units
loader + propose-default gate), ADR-0010 (`engine/board.py` unit schema). Honors
ADR-0005 R3 / ADR-0007 D11 (the gateway path imports nothing from here; this is one
opt-in consumer module, stdlib-only).

## Context
ADR-0007 ships **consumer-supplied units** — you hand-author a units file. That only
serves people who code. ADR-0008 defines the front door that inducts **messy project
input** (a markdown work-item list) → analyzes → emits a **rule-abiding ticket plan**
plus a **top-level product acceptance**. This ADR builds **Phase 1 only**: the output
is a *proposal a human approves/edits*. There is **no autonomous run** (that is Phase 2,
deferred behind ADR-0007 D10-C). `src/charon/intake.py` is the whole increment.

## Decisions

### D1 — Phase 1 is propose-only; intake never executes anything
Intake reads input as **data** and emits a durable artifact. It **never runs** an
acceptance command, never spawns a unit, never lands. Execution stays with the
existing fenced `coordinator.run` + `land.py` gate, downstream, after a human approves
the plan. This makes the whole module injection-inert by construction: there is no
code path from input text to execution.

### D2 — The failure contract is enforced mechanically (ADR-0008 §"failure contract")
1. **File-overlap → serialize, never parallel-share.** Overlap is decided by
   `land.in_scope` (nested-or-equal) — the same matcher the board uses — so intake,
   board, and land agree on "shares a path". For every overlapping unit pair, a
   `depends_on` edge is added (higher id → lower id) so they land in different waves.
   A final invariant check asserts **no two concurrent units share a path**, or it
   raises (defence in depth). Merge is left to the human (flagged), not auto-applied.
2. **Unprovable independence → conservatively serialize + flag.** A unit with **no
   inferable owned paths** cannot be proven file-disjoint, so it is serialized after
   all scoped units and flagged `propose-only` for human scoping. It is never
   parallelized into a wave.
3. **Mis-tiering** is non-fatal (engine failover handles it); intake only tags a tier.
4. **No executable acceptance → propose-only, surfaced for review.** Such an item
   cannot be a runnable unit (the engine/land contract requires a check), so it is
   emitted as a **review item** with reason `missing-acceptance`, *not* in the loadable
   `units` list — keeping the emitted plan loadable by `land.load_units` while still
   capturing the work.
5. **Vague input → "need more detail on X", never a hallucinated unit.** Empty /
   contentless items become an `issue`, not a unit. Empty input yields zero units.
6. **Durable, diffable artifact.** Output is one JSON document (a TICKETS-style plan),
   loadable by `land.load_units`; each unit carries both `owned_paths` (land) and
   `owns` (board) so the one artifact feeds both consumers unchanged.
7. **Injection-safe.** Input is data: fenced code blocks are *not* parsed for
   headings/fields (an injected `## ticket` / `accept:` inside a fence stays data), and
   acceptance strings are stored verbatim, never interpreted.

### D3 — Top-level product acceptance is a first-class output (ADR-0008 §top-level)
Intake captures **"what does the whole thing working look like"** from a designated
acceptance section. This is exactly what `validate.py` (ADR-0007 D12) currently stubs at
unit level. Absence is flagged (the plan is marked not-ready), never invented.

### D4 — Owned-paths inference is deliberately shallow (the ADR-0008 open question)
v1 infers owned paths from **explicit file mentions** (`files:`/`paths:`/`owns:` fields)
and inline code spans that look like paths; prose-only inference is flagged for human
confirmation. **No static analysis** — over-engineering it is out of scope; ambiguity
is surfaced to the human, not guessed.

### D5 — Adapter seam, markdown first
Input format is pluggable via an adapter registry; v1 ships the **markdown work-item**
adapter. Brief / backlog / GH-issue adapters are a reserved seam, not built here.

## Invariants preserved
ADR-0005 R3 / D11: `intake.py` lives outside the gateway path; the boundary test still
asserts the server imports nothing from the engine/consumer modules. Stdlib-only. The
plan is propose-default — a human merges (ADR-0010 D3). No file outside this ticket's
`owns` is touched (`decompose.py`/`land.py`/`validate.py` are read, never edited).

## Adversarial self-review (before code)
- **Does intake widen the attack surface?** No — D1: no input-to-execution path; the
  injection test proves fenced directives stay data.
- **Could it emit a colliding/parallel-sharing plan?** No — D2.1 invariant raises if a
  concurrent pair shares a path; overlap always serializes.
- **Could it hallucinate work from vague/hostile text?** No — D2.5: contentless items
  become issues; only real headings outside fences become units.

Reconciled in `docs/review-log/E4.md` before code (house rule; per-ticket fragment).
