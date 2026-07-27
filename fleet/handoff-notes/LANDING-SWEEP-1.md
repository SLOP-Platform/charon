# LANDING-SWEEP-1 — triage report for 13 unlanded branches

| # | Branch | Disposition | One-line rationale | Evidence |
|---|---|---|---|---|
| 1 | PREFLIGHT-VERIFY-MERGED-GHCACHE | NEEDS-REVIEW | Original scope (gh-cache.sh adoption) landed via PR#181 (c972396); salvage commit (93f8b02) contains board-hygiene WIP NOT on master, described as "preservation only, not verified." | RAN: `git log master..HEAD` shows 6 commits — 5 are patch-identical to PR#181 on master, salvage commit adds 55-file board reorg. `git show master:fleet/gh-cache.sh` confirms cache adoption already landed. READ: salvage commit message says "needs its own review/PR." |
| 2 | FIXTURE-BYPASS-GATE | LAND-READY | Two new gates (fixture-bypass.sh + gate-integrity.sh) with comprehensive tests. | RAN: fixture-bypass.test.sh = 29 passed, gate-integrity.test.sh = 22 passed. `git show master:fleet/checks/fixture-bypass.sh` = does not exist on master. |
| 3 | RECONCILE-GATE-WIRED | LAND-READY | Built-but-inert meta-gate salvaged + wired into preflight.sh, with 3 accuracy bugs fixed during salvage. P0 priority ticket. | RAN: reconcile-gate-wired.test.sh = 11 passed. READ: review-log documents salvage pass fixing 3 false positives, transitive-closure reachability, and a pre-existing VALID_AREA bug. `git show master:fleet/checks/reconcile-gate-wired.sh` = does not exist. |
| 4 | LITELLM-COST-FIELD-TEST | LAND-READY | Fixes `_cost_from_hidden` to stop conflating 0.0 with absent; adds `total_cost` fallback in `usage.cost`. | RAN: 36 pytest passed (test_gw_bridge2_metering.py). `git show master:src/charon/litellm_plane/metering.py` = does not exist on master. |
| 5 | BANDIT-PREEXISTING-FINDINGS | LAND-READY | Resolves 3 pre-existing MEDIUM bandit findings: B310 scheme guard in charon_cost.py, nosec justifications in two selftest files, chmod 0o700 hardening. | READ: `git show master:fleet/benchmark/lib/charon_cost.py` — no `urlsplit(url).scheme != "https"` guard, no B310 nosec. Selftest fixes also absent from master. |
| 6 | CLAIM-LADDER-HEALTH | LAND-READY | New ladder-health.sh surfacer script — surfaces all claim exclusion reasons across the priority ladder. | RAN: ladder-health.test.sh = 34 passed. `git show master:fleet/ladder-health.sh` = does not exist. |
| 7 | DOGFOOD-SCORECARD-TIMESTAMP-FIX | LAND-READY | Adds PID suffix to scorecard output filenames with collision-guard against same-second overwrites. | RAN: dogfood-to-scorecard.test.sh = 21 passed (includes same-second distinct-output collision-guard test). `git show master:fleet/benchmark/dogfood-to-scorecard.sh` = no PID suffix. |
| 8 | INVENTORY-TABLE | NEEDS-REVIEW | New inventory-table.sh + price-tracked-inventory.tsv added (complete KS29 accessor). But NO dedicated test file found; worktree diff is 567 files, mostly massive board-hygiene deletions — appears to be salvage/hygiene WIP mixed with the ticket work. Completeness of accessor unverified. | RAN: `inventory-table.sh --help` works, `inventory-table.sh list` showed usage correctly. READ: `git diff --stat master..HEAD` (excluding graphify-out) = 567 files, +632/-51140 — dominated by unrelated board/handoff cleanup. `fleet/tests/inventory-table.test.sh` = does not exist. |
| 9 | LOOP-GUARD-INFRA-FAULT-EXEMPT | LAND-READY | Adds infra-fault exemption to loop-guard: zero-commit releases caused by pool exhaustion / RED board / gateway-reset no longer quarantine tickets. P1 priority. | RAN: loop-guard-infra-exempt.test.sh = 36 passed (includes fail-on-revert: infra fault quarantines on 2nd when exemption broken). `git show master:fleet/loop-guard.sh` — no `infra_reason` function, no `--reason` flag. |
| 10 | REAPER-APPLY-WIRING | LAND-READY | Adds OPEN-PR guard to branch-reaper — prevents reaping worktrees with live GitHub PRs. Fail-closed: `gh` unavailable = KEEP. | RAN: branch-reaper.test.sh = 119 passed (includes v5 KEEP-reason-matches-open-PR, v6 open-PR worktree survives --apply). `git show master:fleet/branch-reaper.sh` — no OPEN-PR guard. |
| 11 | REVIEW-RECONCILE-GATE-DESIGN | NEEDS-REVIEW | Adversarial design review of UNIFIED-RECONCILIATION-GATE-DESIGN (PR #178). Verdict: APPROVE-FOR-OPERATOR with 2 NEEDS-REVISION items. No code changes — review document only. | READ: `fleet/state/REVIEW-RECONCILE-GATE-DESIGN.md` = 243 lines of adversarial review with ground-truthed findings against live repo. `git show master:fleet/state/REVIEW-RECONCILE-GATE-DESIGN.md` = does not exist. |
| 12 | ROUTER-LEDGER-DECAY | NEEDS-REVIEW | Working decay module (17 tests pass) with exponential half-life math. BUT: not yet wired into `build_routes_and_pools` — importable but not integrated. Not yet a live ranking input. | RAN: 17 pytest passed (test_ledger_decay.py). READ: review-log states "Not yet wired into build_routes_and_pools — the model-signal ledger is not yet a live ranking input." `git show master:src/charon/routing_policy/ledger_decay.py` = does not exist. |
| 13 | WATCHDOG-RESTART-VERIFY | LAND-READY | Fixes all 4 broken monit restart commands (root-context-safe), adds fail-closed pre-enable verify gate, creates real bench-grader-daemon.service unit. Matches board ticket WATCHDOG-RESTART-CMDS-VERIFY (P0). | RAN: verify-restart-cmds.test.sh = 30 passed (includes FAIL-ON-REVERT: real committed registry passes root-context grammar). `git show master:fleet/watchdog/verify-restart-cmds.sh` = does not exist. |

=== SESSION REPORT v1 ===
TICKET:       LANDING-SWEEP-1
SESSION:      jaina-solo | deepseek-v4-pro
STATUS:       DONE
COMMIT:       none
FILES:        1 changed: fleet/handoff-notes/LANDING-SWEEP-1.md
OWNS-OK:      yes
GATE:         n/a — read-only triage
TESTS:        n/a — read-only triage
RED-PROOF:    n/a — no code change
OBSERVABLE:   MET — all evidence fetchable from worktree git objects; no live system dependency
RAN:          git log/diff for all 13 branches; bash test suites for FIXTURE-BYPASS-GATE (51 tests), RECONCILE-GATE-WIRED (11), CLAIM-LADDER-HEALTH (34), DOGFOOD-TIMESTAMP-FIX (21), LOOP-GUARD-INFRA-EXEMPT (36), REAPER-APPLY-WIRING (119), WATCHDOG-RESTART-VERIFY (30); pytest for LITELLM-COST-FIELD-TEST (36), ROUTER-LEDGER-DECAY (17)
READ:         BANDIT-PREEXISTING-FINDINGS (no test suite — read diff against master), PREFLIGHT-VERIFY-MERGED-GHCACHE (read salvage commit message + verified PR#181 on master), REVIEW-RECONCILE-GATE-DESIGN (review doc only), INVENTORY-TABLE (no test file found)
BRIEF-ERRORS: none
BLOCKED-BY:   none
NEXT:         LAND-READY=9 NEEDS-REVIEW=4 ABANDON=0 UNSAFE=0
=== END REPORT ===
