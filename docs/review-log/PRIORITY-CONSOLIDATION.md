# PRIORITY-CONSOLIDATION review

## Change
Consolidate 4 overlapping ranking nomenclatures (RANK-0 / R0.x, the P0-P4
cg-priority-ladder, the project ladder, and a `priority:` field used 3
inconsistent ways — HIGH/MEDIUM/P2) into ONE numeric machine-read axis
(`priority: N`, integer 0..5, LOWER = more urgent), and make `claim.sh` SELECT
BY PRIORITY instead of alphabetical-first.

## Files changed
- `fleet/claim.sh` — selection ladder: priority ASC > blocking DESC > blast DESC
  > difficulty DESC > id ASC. Replaces the OLD first-match-wins loop. Single
  awk over a precomputed INDEX (preserves the PERF fix from PERF-AUDIT-CLAIM-
  DECOMPOSE). revdep (BLOCKING axis) is precomputed in the INDEX-build awk by
  stashing per-row deps in arrays and tallying in the END block (avoids a
  second pass and the sort-order trap that a naive in-pass count would hit).
- `fleet/state/PRIORITY-LADDER.md` — NEW. Canonical axis + band table.
  Single source of truth for the selection ladder. Whitelisted in
  `.gitignore` to be tracked (sibling to RULE-REGISTRY / ROADMAP / REDS-CORPUS
  in `fleet/state/`).
- `fleet/board/REACHABILITY-GATE.md` — `priority: HIGH` → `2`.
- `fleet/board/REVIEWER-DOGFOOD-REDS.md` — `priority: MEDIUM` → `3`.
- `fleet/board/SUBAGENT-WORKTREE-SANDBOX.md` — `priority: P2` → `2` (and the
  prose updated to reflect the new band).
- `fleet/session-notes/NEXT-SESSION-RANK0.md` — mapping note: RANK-0 = `priority: 0`,
  P-band N = `priority: N`. RANK-0 is no longer a separate super-tier; the
  machine sees one band and the rest of the ladder breaks ties.
- `fleet/tests/priority-validator.test.sh` — NEW. Two surfaces:
  (1) DRIFT — walks every `fleet/board/*.md`, asserts every `priority:` value
  is integer 0..5 or absent. Catches `HIGH` / `MEDIUM` / `P2` / `7` / `-1`
  reverts.
  (2) LADDER — runs the REAL `claim.sh` against a synthetic board and asserts
  every rung of the selection ladder: priority beats alpha, blocking beats
  blast, blast beats difficulty, difficulty beats id, unset = lowest.
  Also: CLAIM_ONLY pin regression (case-insensitive, bypasses the ladder,
  NONE on non-existent id).
- `fleet/checks/rig-ci-scope.sh` — adds `priority-validator.test.sh` to the
  CI allowlist (hermetic; ~2s; no network).
- `.gitignore` — adds `!fleet/state/PRIORITY-LADDER.md` so the new doc is
  tracked (sibling to the other `!fleet/state/<doc>` exemptions).
- `docs/review-log/PRIORITY-CONSOLIDATION.md` — this file.

## Key design decisions
- **LOWER = more urgent.** Convention picked because the composite key is
  a lex-minimized first field and "do this first" is the operator-intuitive
  meaning. Plus, an ascending integer is the only ordering that survives a
  `int(value)` parse from arbitrary tickets without a convention flip.
- **`unset` = +infinity (= 9999).** A ticket without a `priority:` field
  is treated as the lowest band — auto-sequenced by the dependency graph.
  NOT a priority band in its own right; absence just means "let the graph
  order it". (Parked stays orthogonal: a parked ticket is not claimable
  AT ALL, regardless of priority.)
- **Composite key as fixed-width zero-padded joined string.** Lex order on
  the joined string IS the desired total order. DESC axes are inverted via
  `99999999 - n` to keep lex-ascending semantics. 8-digit width is plenty
  (a 2000-file board has well under 10^8 reverse-deps / owns / difficulty).
- **revdep is precomputed in the INDEX-build awk, not the claim awk.** A
  naive per-pass revdep count hits a sort-order trap: the INDEX is sorted
  by file path, but dependents are filed alphabetically AFTER their dep
  most of the time, so a single pass that increments revdep as it walks
  would rate HIGH-BLOCK as blocking=0 even though two open tickets depend
  on it. The stash-and-tally approach in the build awk is O(N) over the
  same N files; no second awk, no extra file I/O. The claim loop just
  reads the precomputed value as INDEX field 10.
- **CLAIM_ONLY pin is preserved verbatim** — same env-var bootstrap, same
  case-insensitive comparison, same short-circuit behaviour. Covered by a
  regression in the new test.

## Test verification
- `bash fleet/tests/priority-validator.test.sh` — GREEN (12 OK, 0 FAIL)
- `bash fleet/tests/parked-semantics.test.sh` — GREEN (unchanged; the
  claim.sh inline parked rule was not touched)
- `bash fleet/tests/parked-claim-e2e.test.sh` — GREEN (unchanged)
- `bash fleet/tests/board-correctness.test.sh` — 7/7 pass (unchanged)
- `bash fleet/tests/claim-loop-guard.test.sh` — 9/9 pass (unchanged)
- `bash fleet/checks/rig-ci-scope.sh syntax` — 0 changed *.sh (no sh
  changes in the diff scope against master)
- `bash fleet/validate_board.sh` — GREEN board structurally valid (no
  new REDs; priority field is absent for ~60 tickets and integer 0..5
  for the 4 that declare it)

## Operator follow-up (PR body, not blocking)
The `cg-priority-ladder` manager MEMORY lives outside this repo (`~/.claude` /
the manager session). The MANAGER updates that memory when this lands; this
ticket deliberately does NOT edit `~/.claude`. The PR body should call this
out so the manager session runs an "axis = priority: 0..5" sweep on its
memory.

## Drift-class risk (revert watch)
The drift test is the canary. If anyone reverts to `priority: HIGH` /
`priority: P2` / `priority: 7` (or the revdep field drop, or the alphabetical-
first loop), `priority-validator.test.sh` fails RED in the CI allowlist. The
test exercises every rung of the selection ladder, so a drop on ANY rung
fails — not just a wholesale revert.
