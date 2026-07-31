# PRIORITY-LADDER — canonical numeric priority axis (single source of truth)

Ticket: `fleet/board/PRIORITY-CONSOLIDATION.md`. Fixes the DRIFTED ranking nomenclatures
that the operator flagged 2026-07-23: RANK-0 / R0.x, the P0-P4 cg-priority ladder, the
project ladder (ROUTER>BRIDGE>FLEET>SECURITY>BACKLOG), and a `priority:` field used
THREE inconsistent ways (HIGH/MEDIUM/P2) — all in the same repo, with no machine
contract. A droid that claims by `priority:` parses it three ways; a droid that claims
alphabetically ignores it entirely. Either way the operator-set ordering is lost.

## The decision — ONE numeric axis

`priority: N` is the **only** machine-read priority field, where `N` is an integer
`0..5` and **LOWER = MORE URGENT**. The operator abbreviates bands as "P:0".."P:5" in
chat; the on-disk field is the integer.

| Band  | Name                              | What it means                                                                                                |
| :---: | --------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| P:0   | top band                          | Operator-escalated / direct CG-active work. The old RANK-0 / R0.0 / R0.1 / R0.2 / R0.3 FOLD IN HERE — no separate super-tier; an "R0.0" is just a human label for a P:0 ticket (see fleet/session-notes/NEXT-SESSION-RANK0.md). |
| P:1   | attached CG work                  | Attached-CG, not huge, not over-dependent.                                                                   |
| P:2   | standalone, biggest blast-radius  | The big standalone pieces (e.g. SUBAGENT-WORKTREE-SANDBOX, REACHABILITY-GATE).                                |
| P:3   | Router standalone                 | The router's own standalone work.                                                                            |
| P:4   | quick wins                        | Fast, isolated, low-risk.                                                                                    |
| P:5   | reserved lowest                   | Reserved lowest explicit band.                                                                               |
| unset | (no `priority:` field)            | Treated as the lowest band (internally 9999) — auto-sequenced by the dependency graph and the rest of the ladder. NOT a priority band in its own right; absence just means "let the graph order it". |

### Why LOWER = more urgent

The composite selection key in `claim.sh` is a left-to-right lexicographic minimum
(priority ASC, blocking DESC, blast DESC, difficulty DESC, id ASC). LOWER on a
lex-minimized first field = picked first, which is the operator-intuitive "do this
first". An ascending integer is also the only ordering that a Python `int(value)`
parse from arbitrary tickets preserves without a convention flip ("`HIGH = 0` or
`HIGH = 5`?" — a setting the operator doesn't have to think about any more).

## What `priority:` is NOT

- **NOT a replacement for `parked:`.** A parked ticket is `parked: true` (or
  prose-parked via `note: ... PARKED ...`) and is **not claimable at all** —
  `claim.sh` already skips it. Parked is orthogonal to priority; you can have a
  P:0 ticket that is parked (operator held) and a P:5 ticket that is the next
  thing a droid should claim.
- **NOT a replacement for `depends_on:`.** The graph still wins: a P:0 ticket
  whose `depends_on:` is on an open ticket is blocked and won't be claimed until
  the dep lands, regardless of its priority. Priority ranks candidates WITHIN
  the already-unblocked set.
- **NOT a replacement for `difficulty:`.** Difficulty is the EFFORT ordinal
  (`1..5`, auto-seeded from tier) and is the SECOND-TO-LAST tie-break in the
  claim ladder — high-difficulty first, so the big one starts early and can run
  in parallel with whatever comes after.

## The full claim selection ladder (in `fleet/claim.sh`)

Among tickets that have already cleared the `claimable` filters (tier ≤ droid's
rank, NOT parked, NOT claimed/submitted/done/loop-guarded, file exists, deps all
done, CLAIM_ONLY honored), pick by, in order:

1. **`priority:` ASC** — `0` first, then `1`, …, `5`, then unset (= 9999).
2. **BLOCKING DESC** — reverse-dep count: how many OPEN board tickets list this
   id in their `depends_on:`. More blocked tickets = do this first, so they
   unblock the chain.
3. **BLAST DESC** — `owns:` surface count. Bigger owned surface = start it
   earlier so the droid can hand off partial work.
4. **DIFFICULTY DESC** — start the high-effort ones first so they overlap
   whatever's next.
5. **id ASC** — deterministic final tie-break (matches the OLD alphabetical-first
   behaviour when the entire ladder above is tied).

The `CLAIM_ONLY` hard-pin (env-var bootstrap, wired by an earlier ticket) skips
this ladder entirely: it pins the droid to one named ticket, case-insensitive.

## Migrating from the old nomenclatures

- **`RANK-0` / `R0.x` (project ladder)** → a `R0.x` is a `priority: 0` ticket.
  The old R0.0 / R0.1 / R0.2 / R0.3 / R0.4 ladder is now just a *human* naming
  convention for the P:0 sub-priorities — the machine sees one band (0) and the
  rest of the ladder (blocking/blast/difficulty/id) breaks P:0 ties. The
  historic R0 work is documented in `fleet/session-notes/NEXT-SESSION-RANK0.md`,
  which now defines the mapping; that doc is no longer the ranking source of
  truth — this one is.
- **`P0`-`P4` (cg-priority-ladder, manager MEMORY)** → a `P:N` is a `priority: N`
  ticket. The cg-priority-ladder lives in the manager's MEMORY (outside this
  repo — `~/.claude` / the manager session), not here. **The manager updates
  that memory** when this ticket lands; this ticket deliberately does NOT edit
  `~/.claude`. (See PR body — manager follow-up.)
- **Project ladder (ROUTER>BRIDGE>FLEET>SECURITY>BACKLOG)** → the ladder is
  the project's *order of business*, not a per-ticket priority. Tickets in each
  lane should pick a `priority:` that reflects WHERE in the overall stack they
  sit; the lanes themselves remain a human framing, not a per-ticket field.
- **`priority: HIGH` / `MEDIUM` / `LOW`** (informal labels on three live tickets
  at ticket-open time) → normalized to integers by this ticket:
  - `REACHABILITY-GATE`: `HIGH` → `2` (standalone, biggest blast-radius band)
  - `REVIEWER-DOGFOOD-REDS`: `MEDIUM` → `3` (router standalone band)
  - `SUBAGENT-WORKTREE-SANDBOX`: `P2` → `2`
  - These were operator-set and informal; the PR body flags them for operator
    sanity-check.
- **`priority: P2`** (the one ticket that used a string-band prefix) → `2`.

## Drift protection

A drift test (`fleet/tests/priority-validator.test.sh`, hermetic) walks every
`fleet/board/*.md` and fails RED if any `priority:` value is not:
- a valid integer 0..5, OR
- absent (the field is OPTIONAL — unset is the "let the graph order it" case).

The test also exercises the claim ladder end-to-end against a synthetic board to
prove the selection order is stable (priority beats alpha; blocking beats blast).
It is in the CI allowlist (`fleet/checks/rig-ci-scope.sh:CI_SUITES`) so a revert
that drops the priority parse or the composite key fails the rig gate, not the
live claim loop.

## Reference

- Selection ladder implementation: `fleet/claim.sh` (claim-loop awk, ticket
  PRIORITY-CONSOLIDATION).
- Drift / fail-on-revert test: `fleet/tests/priority-validator.test.sh`.
- Old RANK-0 framing, retained for context: `fleet/session-notes/NEXT-SESSION-RANK0.md`.
- This ticket's intent: `fleet/board/PRIORITY-CONSOLIDATION.md`.
