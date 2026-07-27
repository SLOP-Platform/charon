# ADR-0015 — Work-Composition Intelligence (reconcile + ordering + advisory layer)

You are writing a **THIN ADR** that *records* an already-reviewed design. Do NOT re-decide
anything; transcribe the settled reshape. Source of truth:
`/home/stack/charon-private/fleet/DSGN-WCI-reshape.md` (this file is on the build rig, NOT in
the product repo — read it for content, never copy the path or rig-internal references into the
ADR).

## What to produce

1. `docs/adr/0015-work-composition-intelligence.md` — a short ADR in the same shape as the
   existing `docs/adr/00NN-*.md` files (Status, Context, Decision, Consequences, References).
   - **Status:** Proposed (or Accepted if `docs/DECISIONS.md` convention prefers it — match the
     neighbouring ADRs).
   - **Position it correctly:** WCI is a composition / ordering / **advisory** LAYER, not a new
     engine. Slot it UNDER ADR-0010 (native substrate) and ADR-0008 / ADR-0011 (intake). It
     reuses existing predicates; it does not introduce a new scheduler rule.
   - **Transcribe the settled record (keep each to a few lines):**
     - The three pillars: (1) static reconcile, (2) within-wave depth pre-sort, (3)
       dependency-minimizing chunking — pillar 3 stays GATED (auto-slice deferred).
     - **R1–R9** resolutions from the reshape (the prior-finding → resolution table) — one line
       each, not the full prose.
     - The **explicit out-of-scope / MVP-exclusion list**: WCI-4 (`merge_after` edge), WCI-5
       (semantic advisory spike), WCI-6 (auto-slice / §5.1 proof) are NOT in the MVP.
     - The **F1 / F2 / F3 reshape-fixes** (F1 = the B1-symmetric label-is-never-a-downgrade
       invariant; transcribe its one-line statement, cite §7).
     - The **HELD WCI-4** decision (operator 2026-06-27: label AND its concurrency payoff ship
       together with §5.1; the `merge_after` schema field is NOT introduced in the MVP).
     - The **PARKED §5.1 / WCI-6** decision (semantic-independence proof contract +
       auto-slice, parked behind §5.1 and the ADR-0008 Phase-2 conflict-rate tripwire).
   - **Hard product constraint (state it explicitly in Consequences):** product WCI is
     **opt-in-orchestrator-only** and **advisory/override for users** — it is NEVER imposed on
     gateway-only / single-task fresh installs. (Charon ships standalone; WCI is an orchestrator
     opt-in, not a default gate.)
2. Append the register row(s) to `docs/DECISIONS.md` (above the marker line, per the file's
   convention) recording: ADR-0015 = WCI reconcile+ordering+advisory layer; MVP = WCI-1 +
   WCI-2; WCI-4/5/6 + §5.1 deferred; opt-in-orchestrator-only constraint.

## Keep it SMALL
## Dependencies & sequence

- **Wave:** 0 (foundation document — no code dependency)
- **depends_on:** none (design/ADR pass; transcribes an already-settled reshape)
- **Concurrency:** safe to run in parallel with any ticket, including WCI-MVP / TIER7B builds
- **Blocks:** WCI (WCI `depends_on: ADR-0015` — WCI must not build against an unsigned design)
- **Type:** design/ADR-pass — produces `docs/adr/0015-work-composition-intelligence.md` + `docs/DECISIONS.md` update only; no `src/` code

## Scope

This ADR records a design that already cleared two adversarial rounds (REWORK → reshape →
focused review → F1/F2/F3 fixes). Do not invent, expand, or contradict it. If the reshape and
an existing Settled `docs/DECISIONS.md` row disagree, STOP and report — do not reconcile silently.

## CONSTRAINTS
Own ONLY the files in your board `owns:` line:
`docs/adr/0015-work-composition-intelligence.md` and `docs/DECISIONS.md` (plus your own
`docs/review-log/ADR-0015.md` fragment). Create/edit nothing else. No code, no engine modules —
this is a documentation-only ticket.

## REPORT BACK — MECHANIZED FORMAT (required)
End your session by emitting EXACTLY this block. Fixed fields, one line each, no diffs or logs.
Validate it before you finish: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Full spec + rationale: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`

```
=== SESSION REPORT v1 ===
TICKET:       <ticket-id>
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha> | none
FILES:        <n> changed: <paths>
OWNS-OK:      yes | NO — <file> is owned by <ticket>
GATE:         PASS | FAIL — <detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> | n/a — <why> | NOT-DONE
OBSERVABLE:   MET | DEFERRED — <what could not be observed and why>
RAN:          <what you proved by EXECUTING>
READ:         <what you concluded by READING only>
BRIEF-ERRORS: none | <what this brief got factually wrong>
BLOCKED-BY:   none | <ticket or condition>
BUDGET:       ok | TRUNCATED — <what you could not finish and why>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
