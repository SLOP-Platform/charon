# WCI-CONSOLIDATION — 2026-07-13

Board/ticket optimization + consolidation pass. Method: code-confirmed only (git log/gh pr
list/actual source at charon origin/master + charon-private origin/master), never trusted
board prose. Done in an isolated worktree (`charon-private-wt/WCI-CONSOLIDATION`, branch
`chore/wci-consolidation`, based on `origin/master`) to avoid colliding with an in-flight
uncommitted session in the main `charon-private` checkout (see COLLISION NOTE at bottom).

## 1. Stale statuses reconciled (7)

All verified via `git log`/`gh pr list --state merged` against the PRODUCT repo
(SLOP-Platform/charon) origin/master, not board prose.

| ticket | was | now | evidence |
|---|---|---|---|
| R46 balance-wire | designed | **done** | PR #95 (`b5d7948`) — `gateway._build_balance_tracker` + `load_config` wire a real `BalanceTracker`; `tests/test_gateway.py::test_load_config_builds_balance_tracker_from_provider_config` is the live FAIL-ON-REVERT. (Note: the ticket's OWN staged branch `feat/r46-balance-wire` / commit `5ed8235` "test(r46): add FAIL-ON-REVERT balance-wire test suite" adds `tests/test_balance_wire.py` and is **NOT** merged — it was written against the pre-#95 world and is now redundant/superseded by #95's coverage. Safe to close without merging; not lost, still on `origin/feat/r46-balance-wire` if ever wanted.) |
| R12 drain-routing | designed | **done** | PR #95 (`b5d7948`) — `forwarder.py` funding-class reorder + `balance.py` drain accounting. |
| R11 drain-then-park | designed | **done** | PR #95 (`b5d7948`) — `forwarder._is_sole_leg` (sole-leg guard), `balance.py` park/unpark + funding-class table, `tests/test_drain_then_park.py` (454 lines, fail-on-revert per funding class). |
| F29 post-gateway-wci-decompose | designed | **done** | 3 slices, all merged: providers-data PR #98 (`5135e2e`), config-package PR #99 (`6460ace`), module-registry PR #100 (`085e74f`, review-log at `docs/review-log/F29-REGISTRY-SLICE.md`). |
| F31 wire-mocklint-enforce | designed | **left open (NOT done)** | **Trap avoided**: `check_test_patterns.py` IS now in `gate_runner.CHECKS` (confirmed at `af4a17c`) — but only as a *side effect* of PR #119 (the unrelated orphaned-gates sweep), not because F31 was executed. F31's actual accept criterion — rule (e) self-mirroring-mock as a **hard ERROR** — is still false: `check_test_patterns.py:17-19` documents it as WARNING-only, and `gate_runner.CHECKS` invokes it without `--strict`. A fresh self-mirroring mock still passes today. Left `designed`; annotated `board/WIRE-MOCKLINT-ENFORCE.md` with the precise remaining scope (DO steps 1/3/4) so it isn't miscounted as done. |
| MODEL-LIFECYCLE | designed | **done** | PR #117 (`69c115d`). |
| LAND-SH-SAFE-SYNC | `next`/`next` (invalid status) | **done** | PR #24 (`40ffdba`) — already merged; the roadmap row had a copy-paste bug (status AND phase both literally `"next"`, not one of the 7 valid values). Fixed. |
| R43 wiring-audit | `next`/`next` (invalid status) | **building / now** | Same copy-paste bug. Real work exists (`fleet/state/WIRING-AUDIT-MATRIX.md` committed at `c041b59`) but its PR **#20 is still DRAFT** — not done. Corrected to a valid status reflecting reality. |

`GATE-REGISTRY-BACKFILL` and `REACHABILITY-GATE` were investigated too (both are, in fact,
code-confirmed **done** — GATE-REGISTRY-BACKFILL's workflow-policy gate + SHA-pin/bare-tag
reconciliation landed in PR #119, `test_gate_registry_execution.py` proves it stays wired) —
but **neither ticket exists in `origin/master`'s `ROADMAP.tsv`/`board/`** yet; both are
uncommitted, local-only additions in the main `charon-private` checkout from a parallel
in-flight session. Deliberately **left untouched** here (see COLLISION NOTE) — flagging so
whoever owns that session's commit marks them done directly, with the same evidence above.

## 2. Wave E re-scope (Fleet F11-F14 "automation brains")

One line: **F11 becomes a composition ticket over already-built pieces (F46 + decompose-sizing),
absorbs F12 (auto-close), and F13/F14 fold away — their concrete scope is already owned by
REACHABILITY-GATE + the gate-registry-execution guard (PR #119) + (once merged) inert-code.**

Detail:
- **F11 work-optimizer** — rewritten. F46 PARALLELIZABILITY-GATE (fleet-rig ticket, merged
  `charon-private` PR #37 `0882882` — launch-time block on an un-justified serial launch of a
  splittable effort) and DECOMPOSE-SIZING-OPTIMIZER (product `feat/decompose-sizing`, commit
  `362d563` — makespan-based N*, **not yet merged to product origin/master**, verified via
  `git log --oneline origin/master | grep 362d563` = no match) are the two real halves of "schedule
  work for max parallelism." F11 is now scoped as the GLUE: read F46's split-or-justify verdict,
  feed N* from decompose-sizing, launch the wave. Not a rebuild. (Also related but a layer up:
  Keystone KS27 `component-work-orchestration` is the portable/generalized KSF version of the same
  idea — F11 is the RIG's concrete instance; KS27 productizes it later. Noted, not folded — different
  repo/layer, deliberately sequenced not merged.)
- **F12 auto-close** — folded into F11 (its auto-close-on-completion step). Also worth noting: the
  bulk of "close landed tickets" is **already live** via F2 `auto-done-on-merge` (done, Wave A). F12's
  only non-overlapping residue (closing STALE/abandoned tickets, not landed ones) is a thin garbage
  collection step, correctly absorbed into F11 rather than kept as its own brain.
- **F13 recurrence-auditor** — folded. "Catch repeat failures automatically" is no longer a
  generic aspiration: the two concrete recurring-defect classes the fleet has actually hit are (a)
  hardcoded cross-boundary paths (bench-grader wall) → owned by REACHABILITY-GATE, and (b)
  registered-but-never-invoked gates (the exact bug class PR #119 fixed 5 instances of) → owned by
  `test_gate_registry_execution.py`. The generalized brain for *future* recurring classes is
  Keystone KS21 (`lens-code-tension`) + KS29 (`component-registry-primitive`, drift-check leg) —
  both already `designed`. No standalone scope remains for F13.
- **F14 detector-lifecycle** — folded. "Keep drift detectors current" — the concrete instance
  (gate-registry entries staying wired) now has a standing fail-loud proof
  (`test_gate_registry_execution.py`, PR #119: a future registered-but-unwired gate fails a test
  immediately). The generalized version is KS29's registry-primitive drift-check leg. No standalone
  scope remains for F14.

All four ROADMAP rows rewritten in place (F12/F13/F14 → `parked`, goal text states the fold +
evidence; F11 stays `queued` with its composed scope). None of F11-F14 had dedicated `board/*.md`
files (roadmap-only placeholders), so `validate_board.sh` is unaffected by this rewrite.

## 3. Broader overlap sweep (beyond the assigned list)

Used `graphify` (charon `graphify-out/graph.json`, freshly regenerated 2026-07-13 14:04 — same
minute as the `af4a17c` merge, i.e. current) to ground the product module map, plus git/gh history
as the source of truth, rather than grepping ticket prose. Findings:

- **R16 GRACEFUL-DEGRADE is now partially unblocked, NOT redundant.** Its board file already names
  R11 as the source of the "auto-recover on refill" primitive. Checked: R11 (merged) built
  `park`/`unpark`/`is_parked`/`force_poll` + the funding-class table, but GRACEFUL-DEGRADE's actual
  3 north-star behaviors (throttle-as-backpressure, alert-on-impact, auto-probe-triggered re-arm)
  have **zero hits** in `router.py`/`failover.py` (`grep -n "throttle\|backpressure\|notify\|alert"`
  → empty). R11 supplied the primitive; GRACEFUL-DEGRADE still has its full original scope on top.
  Not folded — flagged as newly-unblocked instead (see re-sequence below).
- **R10 free-tier-quota-spill** — DRAIN-THEN-PARK's own scope note (now-merged R11) explicitly
  says it "owns the SHARED reactive-park + re-arm mechanism both classes consume," meaning R10's
  remaining scope should SHRINK (it inherits the park/re-arm plumbing for free) rather than build
  its own. Re-scope recommended next session, not done here (no code exists yet to verify against).
- **KS28 consolidate-pattern-guard** already IS the correct fold-ticket for the pattern-scanning
  gate sprawl (leak_guard/no_pipe_mask/KS13/KS19/revert-patterns) — checked its own scope text,
  it's already correctly positioned; no action needed, just confirmed not itself a duplicate.
- **F25 repo-decl-central** vs R43's `rig-repo-routing` (merged PR #13, `9662e3e`) — checked: these
  are DIFFERENT concerns (F25 = central Bash var declaration of the two repo roots for rig scripts;
  PR #13 = the *board/ticket* `repo:` field registry+validator). Not a duplicate — left alone.
- No other clear duplicate/overlapping pair found on this pass within the time budget. The roadmap
  is large (170+ rows); this was a targeted sweep (Wave E + everything the merged R46/R11/R12/F29/
  MODEL-LIFECYCLE PRs touch or reference), not an exhaustive line-by-line re-audit.

## 4. Re-sequence (real dependency + CG-priority ladder)

CG = Charon Gateway (the live money-path). Ladder: **P0** = direct CG-active (gateway/router/
balance money-path) · **P1** = rig gates that protect the money-path · **P2** = KSF/Keystone
capability layer · **P3** = portable-engine/Bridge · **P4** = parked/deferred backlog.

Newly unblocked now that R46/R11/R12/F29 are DONE:
- **P0 — R47 live-api-balance** (neuralwatt adapter + TTL poller): was staged behind R46; R46 is
  merged, so R47 can move from `designed` to actively queued.
- **P0 — R16 GRACEFUL-DEGRADE**: park/re-arm primitive (R11) is live; the remaining throttle/alert/
  probe-triggered-recover behaviors can be built directly on it now.
- **P0 (shrink first) — R10 free-tier-quota-spill**: re-scope to consume R11's shared park/re-arm
  mechanism before estimating/building (see §3).
- **P1 — merge R43's draft PR #20** (cheap, read-only, zero product risk) to formally unblock
  **R44 dogfood-gate** and **R45 inert-startup-check**, both of which explicitly consume R43's
  wired/inert matrix per its own board scope note.
- **P1 — F31 wire-mocklint-enforce**, finish DO steps 1/3/4 (hard-error rule (e)): test-integrity
  gate, money-path-adjacent per its own tier/work_class.
- **P1 — F11 work-optimizer** (re-scoped above): now a clean composition, ready to build.
- **P2 — Keystone KS-wave** (gate library, KS9-KS32): capability layer, correctly lower priority
  than the live money-path items above; no change to their relative order.

## 5. Board health

`fleet/validate_board.sh` — GREEN before and after this pass (0 RED; only pre-existing
WCI-ADVISORY/INFO/WARN lines, unchanged in kind). F11-F14 rewrites don't touch board/*.md files
(roadmap-only rows) so they cannot regress the validator. The 4 retired tickets
(R46-BALANCE-WIRE, DRAIN-THEN-PARK, DRAIN-ROUTING, POST-GATEWAY-WCI-DECOMPOSE) were closed via
`done.sh --merged-sha <sha>` (real verification, not a hand-written marker) and auto-archived by
`retire-done.sh` to `board/archive/`.

## COLLISION NOTE

The main `charon-private` checkout (not this worktree) had uncommitted local changes at session
start on `feat/anti-clobber-session-start`: modified `fleet/benchmark/preflight.sh`,
`fleet/charon-run.sh`, `fleet/provider-exhaustion-ledger.tsv`, `fleet/roadmap-html.sh`,
`fleet/state/ROADMAP.tsv`, plus untracked `fleet/board/GATE-REGISTRY-BACKFILL.md`,
`fleet/board/REACHABILITY-GATE.md`, `fleet/benchmark/bench-grader-setup.sh`,
`fleet/benchmark/preflight-tasks/trap-subset-manifest.tsv`, `fleet/scorecard.v1.json` — evidence of
another in-flight session's WIP. This work was **not touched, not committed, not lost** — this
consolidation pass was done in a fresh worktree branched from `origin/master` specifically to avoid
stepping on it. Whoever owns that session should commit their own state separately; this branch
should rebase/merge cleanly on top since it only touches ROADMAP.tsv rows that session's diff
doesn't (R46/R11/R12/F29/F31/MODEL-LIFECYCLE/LAND-SH-SAFE-SYNC/R43/F11-F14) — worth a diff check
before merging both.
