# DSGN-WCI-PROOF — §5.1 semantic-independence proof contract (DESIGN/PROOF pass)

You are running a **DESIGN / PROOF pass**, NOT a droid code build. The output is an
**approved proof *contract*** — a specification, reviewed and operator-signed — exactly the
way `DSGN-WCI-reshape.md` was produced (manager design sub-session → adversarial review →
synthesize → operator sign-off). No `src/charon` code, no engine module, no PR-to-master
build. The artifact is a rig design doc.

## Dependencies & sequence

- **Wave:** 0 (foundation design — no code dependency)
- **depends_on:** none (design/proof pass; independent of any build; reasons about import/symbol/config/test coupling with zero engine code needed)
- **Concurrency:** safe to run in parallel with ADR-0015, WCI-MVP, and any other ticket
- **Blocks:** WCI-FOLLOWON (needs both WCI-MVP landed AND this proof approved)
- **Type:** design/proof-pass — produces a rig-internal design doc only; no `src/` code, no product repo PR

## Scope

Source of truth (read first):
- `/home/stack/charon-private/fleet/DSGN-WCI-reshape.md` §5 (open question 1 — "Semantic-
  independence proof contract is undefined (highest risk)"), §7.1 (the F1 invariant that
  *consumes* this proof), and the WCI-6 / §5.1 park decisions.
- This is the **keystone** the whole Pillar-3 / `merge_after` concurrency story hangs on:
  per F1, "the split is invented by the proof, never by the label." Until this contract is
  specified AND itself adversarially reviewed/approved, Pillar 3 stays edge-relabel +
  serialize-only and WCI-FOLLOWON cannot build.

## What to SPECIFY (the contract)

Define **when two work units are PROVABLY independent** — the precise predicate that lets a
`merge_after`-labeled pair be `CLAIMED` concurrently (F1 condition (i)). It MUST be **strictly
STRONGER than disjoint `owns`** (B1: path-disjointness is necessary-not-sufficient; it proves
nothing about imports, calls, shared runtime state, or config).

Per the reshape, the candidate signals to formalize into a single decidable contract:
1. **Import-graph reachability** between the two sliced sub-units (neither reachable from the
   other through the module import graph).
2. **Shared-symbol analysis** (no write/read of a common mutable symbol / module-global).
3. **Shared-config touch** (no common config key/file both depend on).
4. **Test co-failure signals** (the units do not co-fail / are not coupled through a shared
   test surface).

For each signal specify: what is computed, on what input, what counts as PASS vs FAIL, how
signals COMBINE into the single independence certificate (all-must-hold vs weighted), the
conservative default on ANY uncertainty (serialize — never concurrent), and how the
certificate is recorded so `claimable` can consume it deterministically (no LLM on the gate
path; the certificate is a pure board-state artifact). State explicitly that the certificate
is the ONLY thing that may open F1 condition (i); the `merge_after` *label* is never itself a
certificate.

## Process (manager design loop — like the reshape)
1. Manager design sub-session drafts the proof contract into the design artifact.
2. **Adversarial review** (read-only reviewer instructed to REFUTE the contract — find the
   pair it would wrongly certify as independent), then synthesize.
3. **Operator sign-off.** Output = an APPROVED proof contract.

## Output / ownership
- Write the contract to a rig design doc: `/home/stack/charon-private/fleet/DSGN-WCI-5-1-PROOF.md`
  (or expand `DSGN-WCI-reshape.md` §5.1 in place). **Design artifact ONLY — never product src.**
- The approved contract is a **prerequisite for WCI-FOLLOWON** (the auto-slice / `merge_after`
  concurrency-payoff build). It unblocks nothing until it is reviewed AND operator-approved.

## CONSTRAINTS
- DESIGN/PROOF pass: produce a *contract*, not code. Do not touch `src/charon`, do not open a
  build PR to master. Per DSGN-WCI-reshape §5.1 / §7.1.

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
