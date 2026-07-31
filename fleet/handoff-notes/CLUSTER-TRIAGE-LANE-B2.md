# CLUSTER TRIAGE — LANE B2
## Summary
| Branch | Ticket | Age | Commits | Verdict | One-line what-it-does | PR? |
|---|---|---|---|---|---|---|
| PRICE-TRACKED-INVENTORY-AUTOSWAP | PRICE-TRACKED-INVENTORY-AUTOSWAP | 8d | 1 | ABANDON | 48-line review fragment; the design doc it declares as deliverable was NEVER written | none |
| PREFLIGHT-VERIFY-MERGED-GHCACHE | PREFLIGHT-VERIFY-MERGED-GHCACHE | 8d | 6 | ABANDON | gh-cache N+1 fix (already landed on master as c972396) + catastrophic board-hygiene deletions | none |
| LOOP-GUARD-INFRA-FAULT-EXEMPT | LOOP-GUARD-INFRA-FAULT-EXEMPT | 8d | 1 | LAND | Infra-fault exemption stops loop-guard from quarantining tickets on pool-exhaustion/RED-board stand-downs | none |

## Per branch

### PRICE-TRACKED-INVENTORY-AUTOSWAP (feat/price-tracked-inventory-autoswap, 1 commit)
- **What it does**: Design review fragment proposing a price-tracked provider inventory auto-swap system composed from 4 EXISTING components (catalog_refresh, pricing_limits_checker, cost_rank, provider_presets).
- **Evidence**: `git -C <wt> diff --name-only master...HEAD` → `docs/review-log/PRICE-TRACKED-INVENTORY-AUTOSWAP.md` only (48 insertions). `git -C <wt> ls-tree -r --name-only HEAD fleet/state/PRICE-TRACKED-INVENTORY-AUTOSWAP-DESIGN.md` → **no such path**. The design doc declared as deliverable (`fleet/state/PRICE-TRACKED-INVENTORY-AUTOSWAP-DESIGN.md`) does not exist on the branch, nor on master. Zero code, zero data, zero configuration.
- **Verdict**: **ABANDON**. No implementation exists to lose. The review-log fragment is a 48-line design sketch with no corresponding artifact.
- **What's lost if dropped**: Nothing executable. The review fragment describes 4 existing components and proposes wiring them; the actual design doc was never authored.

### PREFLIGHT-VERIFY-MERGED-GHCACHE (salvage/preflight-verify-merged-ghcache-wip, 6 commits)
- **What it does**: Originally the gh-cache.sh N+1 fix (commit 106618a), later merged with master and extended with WIP board-hygiene reorganization (commit 93f8b02).
- **Evidence — the gh-cache fix is already landed**: `git -C <wt> diff master HEAD -- fleet/gh-cache.sh` → **empty** (identical to master). `git -C <wt> diff master HEAD -- fleet/_lib.sh` → **empty**. Master's `c972396` (`fix(preflight): adopt gh-cache.sh for verify_merged to kill per-marker N+1 (#181)`) carries the same fix with the same message as the branch's `106618a`. Content-equivalent. **OVERTURN PRIOR VERDICT** for the gh-cache core: that part is LANDED-ALREADY, not ABANDON. But the overriding verdict on the branch as a whole remains ABANDON for a different reason — see below.
- **Evidence — the HEAD commit DELETES live infrastructure**: The branch HEAD `93f8b02` (`salvage(WIP): board hygiene reorg found staged-but-uncommitted after PR#181 merge`) actively deletes:
  - `fleet/flow-canary.sh` (578 lines) — the proactive e2e money-path health check (CONFIRMED: `git -C <wt> show HEAD:fleet/flow-canary.sh` → `fatal: path does not exist in HEAD`; `git -C <master> show master:fleet/flow-canary.sh` → EXISTS, live at 1817874)
  - `fleet/tests/flow-canary.test.sh` (398 lines) — its test suite (same deletion confirmed)
  - `fleet/state/WORKLOOP-INTEGRITY-STACK-SPIKE.md` (1118 lines) and `fleet/state/UNIFIED-RECONCILIATION-GATE-DESIGN.md` (415 lines) — design-of-record documents
  - 30+ board ticket files from `fleet/board/` and `fleet/board/archive/`
- **Verdict**: **ABANDON** (confirming the core of the prior review, but for the correct reason). The prior review correctly identified "real deletions would remove live infrastructure" — these ARE real deletions in commit 93f8b02, confirmed by `git diff-tree` on each branch-unique commit. Merging this branch would destroy `flow-canary.sh`, its test suite, design documents, and 30+ board tickets. The valuable test improvements in commit 4033963 (`fleet/tests/gh-cache.test.sh`) could be salvaged as a separate REWORK if the operator wants them, but the branch-as-a-whole is unsafe to merge.
- **What's lost if dropped**: The `gh-cache.test.sh` improvements from commit 4033963 (test coverage for `pr_number_is_merged`) and the board-ticket alignment work in commits `bc4cdb9`/`0fe1774`. These are small, and the gh-cache fix itself is already on master — only the test coverage add is novel. The deletions MUST NOT land.

### LOOP-GUARD-INFRA-FAULT-EXEMPT (fix/loop-guard-infra-fault-exempt, 1 commit)
- **What it does**: Adds `--reason` flag and infra-fault classification to `loop-guard.sh`. Infra faults (pool-exhausted, RED-board, gateway-reset, launcher-refused, etc.) never count toward quarantine threshold — they retry silently. Backward-compatible: no `--reason` still quarantines as before. Fixes the priority-ladder starvation bug where P0/P1 tickets got quarantined during infra outages.
- **Evidence**: `git -C <wt> diff --name-only master...HEAD` → 3 files: `fleet/loop-guard.sh` (+72/-8), `fleet/tests/loop-guard-infra-exempt.test.sh` (new, 134 lines), `docs/review-log/LOOP-GUARD-INFRA-FAULT-EXEMPT.md` (+54). Board file `fleet/board/LOOP-GUARD-INFRA-FAULT-EXEMPT.md` exists on master with P1 bugfix priority. No done-marker exists. No open PR found. The branch commit `a833991` is NOT on master (master's loop-guard is at `6c0ad82`, which lacks the exemption logic).
- **Verdict**: **LAND**. Clean, focused change: 3 files, comprehensive test coverage (5 test categories including fail-on-revert guard), backward-compatible, fixes a demonstrated priority-ladder starvation bug. No conflict risk vs current master — `loop-guard.sh` on master is the same file at the same path with only the pre-exemption logic.
- **What's lost if dropped**: The priority ladder will continue to silently starve during any future pool-exhaustion or RED-board episode. Quarantined P0/P1 tickets are invisible to claim.sh, causing tabs to fall through to economy work with zero signal.

## Recommended landing ORDER for my LAND verdicts
LOOP-GUARD-INFRA-FAULT-EXEMPT — single commit, no dependencies, no conflict risk. Can land immediately.

## Anything I could not determine, and what would settle it
- **PR presence**: `gh` CLI not available on this rig. Could not verify whether open PRs exist for any of the three branches. A `gh pr list --repo Nnyan/charon-private --state open` run by an operator with credentials would settle this.
- **PREFLIGHT gh-cache.test.sh salvage**: The test improvements in commit 4033963 may have already been absorbed into master's test suite since `c972396` landed. Verifying this would require comparing `fleet/tests/gh-cache.test.sh` on the branch vs master — if identical, nothing remains to salvage from this branch at all.
