# CLUSTER TRIAGE — LANE C
## Summary
| Branch | Ticket | Age | Commits | Verdict | One-line what-it-does | PR? |
| feat/inventory-table | INVENTORY-TABLE | 7d | 1 | LAND | KS29 price-tracked inventory TSV + accessor (router identity) | #205 |
| fix/inert-wiring-enforcement-durable | INERT-WIRING-ENFORCEMENT-DURABLE | 7d | 1 | ABANDON | design for durable inert-wire enforcement (branch only added review-log; DESIGN absent from tree) | #193 |
| fix/dogfood-scorecard-timestamp-collision | DOGFOOD-SCORECARD-TIMESTAMP-FIX | 7d | 1 | LAND | PID-suffix + guard on scorecard-append-pathc-*.sh to stop same-sec clobber + test | #221 |
| feat/claim-ladder-health | CLAIM-LADDER-HEALTH | 7d | 1 | LAND | ladder-health.sh surfacer: exact exclusion reason for every top-K claim blocker + tests | #215 |
| fix/bandit-preexisting-findings | BANDIT-PREEXISTING-FINDINGS | 7d | 1 | LAND | clear 3 pre-existing MEDIUM bandit (B310 scheme-gate + nosec/B103 chmod) | #188 |

## Per branch (short)
### feat/inventory-table
- what it does: canonical fleet/state/price-tracked-inventory.tsv (19-col §3c) + fleet/inventory-table.sh (init/read/upsert-row/list-by-status) keyed on (provider, normalized_model_id) via charon.proxy._normalize_model_id.
  evidence: `git -C /home/stack/charon-private-wt/INVENTORY-TABLE diff --name-only master...HEAD` → docs/review-log/INVENTORY-TABLE.md fleet/inventory-table.sh fleet/state/price-tracked-inventory.tsv ; `git -C /home/stack/charon-private ls-files fleet/inventory-table.sh fleet/state/price-tracked-inventory.tsv 2>&1` → "did not match any file(s) known to git" (absent in master); `git -C /home/stack/charon-private merge-base --is-ancestor bcc2a15 master && echo anc || echo not` → "not".
  verdict: LAND
  what's lost if dropped: shared inventory spine for discovery/drift/autoswap; no canonical deduped price-tracked table.

### fix/inert-wiring-enforcement-durable
- what it does: (per commit bbb8421) "design document — root-cause + durable wire-enforcement mechanism"; (per tree) only added review-log.
  evidence: `git -C /home/stack/charon-private-wt/INERT-WIRING-ENFORCEMENT-DURABLE diff --name-only master...HEAD` → docs/review-log/INERT-WIRING-ENFORCEMENT-DURABLE.md ; `git -C /home/stack/charon-private-wt/INERT-WIRING-ENFORCEMENT-DURABLE ls-tree --name-only -r HEAD | grep -E 'INERT-WIRING-ENFORCEMENT-DESIGN|state/INERT'` → (empty) ; `git -C /home/stack/charon-private-wt/INERT-WIRING-ENFORCEMENT-DURABLE cat-file -e HEAD:fleet/state/INERT-WIRING-ENFORCEMENT-DESIGN.md 2>&1 | cat` → "fatal: path exists on disk, but not in 'HEAD'" ; `git -C /home/stack/charon-private ls-files fleet/state/INERT-WIRING-ENFORCEMENT-DESIGN.md fleet/board/INERT-WIRING-ENFORCEMENT-DURABLE.md` → board file present in master, design absent ; `git -C /home/stack/charon-private ls-files docs/review-log/INERT-WIRING-ENFORCEMENT-DURABLE.md` → absent.
  verdict: ABANDON
  what's lost if dropped: the review-log fragment for the operator-escalated design review. Acceptable: the branch's commit never included the DESIGN.md deliverable (absent from tree); board file for ticket already lives in master; review record not protected by this branch.

### fix/dogfood-scorecard-timestamp-collision
- what it does: append $$ (PID) to OUT="$FLEET/state/scorecard-append-pathc-${TS}.sh" + existence guard + fail-on-revert test forcing same-ts runs.
  evidence: `git -C /home/stack/charon-private-wt/DOGFOOD-SCORECARD-TIMESTAMP-FIX diff --name-only master...HEAD` → docs/review-log/DOGFOOD-SCORECARD-TIMESTAMP-FIX.md fleet/benchmark/dogfood-to-scorecard.sh fleet/tests/dogfood-to-scorecard.test.sh ; `git -C /home/stack/charon-private grep -n 'scorecard-append-pathc-.*\$\|already exists (same-second' fleet/benchmark/dogfood-to-scorecard.sh || echo absent` → absent ; `git -C /home/stack/charon-private show master:fleet/benchmark/dogfood-to-scorecard.sh | sed -n '65,70p'` → OUT="$FLEET/state/scorecard-append-pathc-${TS}.sh" (no PID, no guard).
  verdict: LAND
  what's lost if dropped: silent clobber of generated append scripts on concurrent same-second dogfood runs.

### feat/claim-ladder-health
- what it does: fleet/ladder-health.sh (priority-ladder surfacer emitting CLAIMABLE or exact exclusion across QUARANTINED/CLAIMED/SUBMITTED/DONE/PARKED/BLOCKED/TIER/BOARD_RED/PARALLELIZABILITY-REFUSED) + 268-line test suite covering every exclusion.
  evidence: `git -C /home/stack/charon-private-wt/CLAIM-LADDER-HEALTH diff --name-only master...HEAD` → docs/review-log/CLAIM-LADDER-HEALTH.md fleet/ladder-health.sh fleet/tests/ladder-health.test.sh (597 ins) ; `git -C /home/stack/charon-private ls-files fleet/ladder-health.sh` → "did not match" (absent).
  verdict: LAND
  what's lost if dropped: starved P0s become invisible again; no surfacer for claim exclusion reasons.

### fix/bandit-preexisting-findings
- what it does: close 3 pre-existing MEDIUM findings: charon_cost.py adds `if urlsplit(url).scheme != "https": return None` before urlopen + nosec; session_cost_selftest.py nosec (loopback mock); run_isolation_selftest.py 0o755→0o700.
  evidence: `git -C /home/stack/charon-private-wt/BANDIT-PREEXISTING-FINDINGS diff --name-only master...HEAD` → docs/review-log/BANDIT-PREEXISTING-FINDINGS.md + 3 py files ; `git -C /home/stack/charon-private grep -n 'scheme != "https"\|nosec B310.*loopback\|chmod.*0o700' fleet/benchmark/lib/charon_cost.py fleet/benchmark/selftest/*.py || echo none` → none in master ; `git -C /home/stack/charon-private ls-files fleet/benchmark/lib/charon_cost.py` → present (pre-existing file, but fixes absent).
  verdict: LAND
  what's lost if dropped: tree-scoped bandit stays dirty at MEDIUM+; security ratchet not advanced.

## Recommended landing ORDER for my LAND verdicts (and why)
1. INVENTORY-TABLE — data spine consumed by discovery/drift/autoswap.
2. CLAIM-LADDER-HEALTH — operational visibility for claim starvation.
3. BANDIT-PREEXISTING-FINDINGS — security hygiene (small isolated changes).
4. DOGFOOD-SCORECARD-TIMESTAMP-FIX — narrow reliability fix.

## Anything I could not determine, and what would settle it
None. All grounded via three-dot diffs (`git -C <wt> diff --name-only master...HEAD`), ls-files, grep, ls-tree, cat-file, merge-base --is-ancestor, gh pr list (open #s), and explicit absence of fleet/state/done/* and fleet/board/* (live+archive) for these tickets. No conflicts visible in the diffs.
