# LIFECYCLE-ENFORCEMENT — Review Log

## Ticket
LIFECYCLE-ENFORCEMENT: build the D-003 blocking-gate mechanism — enforcement, not recall.

## Status
Built and red-proofed: edges **E1** and **E3**. Edges **E2 / E4 / E5** NOT built (reasons below).
CI wiring (allowlist + firing layer) is the single deferred item — it needs files outside this
ticket's `owns:`. See "Coverage" and "What the next session must NOT believe".

## What was done

`fleet/checks/lifecycle-enforce.sh` — a stateless, hermetic, offline enforcement gate (bash
wrapper + stdlib-only python core; holds no state, so D-008's "not bash if it holds state" is
honoured). It reads the tree and exits 0/1/2; it never writes, never reaches the network, never
calls gh.

`fleet/tests/lifecycle-enforce.test.sh` — hermetic fail-on-revert suite (mktemp -d + sandbox
lib only, no network, no git, no fleet/state/ dependency), **33/33 passing**.

### Edge 3 — VERDICT-WITHOUT-TICKET (BUILT, the primary edge)
A landed `docs/review-log/*` fragment carrying an **ADOPT/REJECT verdict statement** must
reference a minted board ticket (`fleet/board/<id>.md` or `fleet/board/archive/<id>.md`), by
fragment filename, a `Ticket` line, or a body token naming such a ticket — else RED. This is the
D-007 rule ("a verdict without a minted ticket is NOT done") made a gate.

- Verdict detection is deliberately narrow: only verdict STATEMENTS fire it (`## Verdict` /
  `## Decision` with the value on the same or next line, a heading that IS the verdict, or a
  bold-name-labelled bullet `- **<name>:** ADOPT …`). Prose that merely uses the verbs
  "adopt"/"reject" is not a verdict, and "DO NOT ADOPT" is a negation, not a verdict — both
  tested GREEN.
- Calibrated against the live tree: GREEN (0 RED). The 4 live verdict-carrying fragments
  (FN-MEMORY-RETIRE-ADOPT, FN1-MEMORY-STORE-ADOPT, MISSING-CLASS-DETECTORS, PR-AUTOMATION-EVAL)
  all reference a board/archive ticket by filename.
- Observed RED on a real violating diff (synthetic, in-suite): a fragment carrying an ADOPT
  verdict with no board reference, and a PR-numbered fragment (`99@charon.md`) with
  `## Verdict\nADOPT` and no Ticket line.

### Edge 1 — ASKED-BLOCKS-TICKET (BUILT)
An open `## ASKED` row in `fleet/state/DECISIONS.md` whose `**Blocks:**` / `**BLOCKS:**` field
names a LIVE (non-parked, non-archived) board ticket makes that ticket RED — refuse claim/launch
until the question is answered, naming the row. Reads exactly the field D-003 says "nothing
reads". Parked tickets, archived-only tickets, prose-only Blocks values, rows with no marker, and
CLOSED/ANSWERED rows are all tested GREEN. Dormant on the current ledger (no ASKED row names a
live ticket today) — it enforces the moment a Blocks field names one.

## Coverage — which of the five D-003 edges are built (acceptance d)

| edge | status | why |
|---|---|---|
| E1 ASKED-blocks-ticket | **BUILT** | mechanically checkable from DECISIONS.md + board |
| E2 DECIDED-contradicted | NOT-BUILT | "a diff that contradicts a cited decision" is not mechanically decidable from files; needs semantics. Deferred rather than shipped as a false-green. |
| E3 verdict-without-ticket | **BUILT** | the cheapest, diff-only edge; the D-007 catch |
| E4 DONE-backed-by-evidence | NOT-BUILT | done-markers live in `fleet/state/done/` (gitignored, absent in a fresh checkout / CI); the "evidence it RUNS" half pairs with D-005 mutation testing — live-tree + separate mechanism, deferred |
| E5 out-of-band-notify | NOT-BUILT | needs infrastructure (ntfy / Healthchecks.io) outside these two owned files |

`bash fleet/checks/lifecycle-enforce.sh edges` prints this machine-queryably.

## Red-proof (acceptance b)

Every built-edge clause is covered by a fail-on-revert case; two cases NEUTER the guard on a
scratchpad copy of the gate and assert the copy then passes a violating tree (so a reverted
enforcer is caught even if only its guard's existence is deleted). 33/33 pass; a revert of the E3
or E1 guard demonstrably flips the suite RED.

## Existing-tool check (D-002/D-004)

Forgetful (scored B+2, the highest of any target, for plans/tasks state machines + dependency
gating) was re-opened and re-examined. It is a session's task-state memory product — it cannot
run as a CI merge-gate over `docs/review-log/*` on this repo, which is what acceptance (a)
demands. D-003 already decided this mechanism and this ticket is its decided-but-never-built
implementation. No adoption is being skipped; this is the D-003 mechanism itself.

## What the next session must NOT believe

- The gate is NOT yet wired: acceptance (a) "ENFORCED in CI" and (c) "the suite is in the
  CI_SUITES allowlist" are **DEFERRED**. Both require editing `fleet/checks/rig-ci-scope.sh`
  (CI_SUITES) and a firing layer (`.github/workflows/rig-ci.yml` or preflight), which are outside
  this ticket's `owns:` (the owned files are only the two above) and are contended by
  CI-SUITES-CANARY / PROOF-SUITES-ENFORCE. Until wired, `lifecycle-enforce.sh` will correctly
  show up as **R-G (built-but-inert)** in `fleet/checks/reconcile-gate-wired.sh` and as a G1/G3
  finding in `gate-integrity.sh` — those meta-gates are the mechanism reporting the true wiring
  gap, not a bug in this change.
- Edge 3 detects verdict STATEMENTS; a verdict embedded in free prose is not mechanically
  detected. That is a deliberate precision/safety trade (it keeps the gate green on the live
  tree) and a known coverage limit.
- The gate is stateless and diff-checkable; it is not a substitute for E4's run-evidence or
  E5's alerting, which remain unbuilt.

## NEXT (the single thing the manager should do next)

Wire it: add `fleet/tests/lifecycle-enforce.test.sh` to `CI_SUITES` in `fleet/checks/rig-ci-scope.sh`
and invoke `fleet/checks/lifecycle-enforce.sh` from `.github/workflows/rig-ci.yml` (or preflight)
— a ~2-line change, sequenced against the rig-ci-scope.sh contending tickets.
