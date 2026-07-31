## VERDICT: SHIP-WITH-FIXES

## Blockers (would strand or mislead)

| # | Issue | Evidence (file:line or command output) | Fix |
|---|---|---|---|
| 1 | Bootstrap path is dead — file lives in worktree, not main checkout | L14: `/home/stack/charon-private/fleet/SESSION-HANDOFF-satele-shan.md` — handoff-check: `PATH NOT FOUND` | Change to `/home/stack/charon-private-wt/NS-CONTENTION/fleet/SESSION-HANDOFF-satele-shan.md` OR copy the file into main checkout before session close |
| 2 | STALE provenance marker — handoff-check FAILS, next session won't trust it | L27: `⚠ STALE: 4 commit(s) behind origin/master`. handoff-check: `STALE marker found` | `sync-checkouts.sh` + regenerate provenance block, or note explicitly that the STALE marker is benign (master has since been synced) |
| 3 | "419 commits of drift" on feat/substrate-first-gate-v2 is WRONG (444 actual) | L149: `419 commits`; real: `git rev-list --count master...feat/substrate-first-gate-v2` = `444`. Diff stat (1662+/38-) is correct | `419` → `444` |
| 4 | RECONCILE-GATE-WIRED worktree path does not exist — if the worker tab is gone, next session looks in empty directory | L144: `/home/stack/charon-private-wt/RECONCILE-GATE-WIRED` — directory not found. PR #285 already landed (archived in e0bb409) | Delete this action item or note it's moot: PR landed, ticket archived. The only RECONCILE-* worktrees present are REVIEW-RECONCILE-GATE-DESIGN, RECONCILE-BOARD-PR-DONE, CLAIM-RECONCILE-INERT, RECONCILE-REVIEW-GATE, STALE-CLAIM-RECONCILE |
| 5 | FIXTURE-BYPASS-GATE has no board entry — land.sh will fail | L147: `feat/fixture-bypass-gate` listed as one of 4 remaining LANDs. `ls fleet/board/FIXTURE-BYPASS-GATE.md` → not found | Mint board ticket before landing, or omit from this wave |
| 6 | Main checkout at close was DIVERGED (e0bb409, 7 behind origin) — handoff does not mention this | `git rev-list --count e0bb409..aa22276` = 7. Manager cannot git reset (deny-listed). Handoff never addresses it | Note that the main checkout must be synced by operator, or instruct next session to work from a worktree that IS synced |

## Gaps

| # | Issue | Detail |
|---|---|---|
| 1 | handoff-check failure not documented | Handoff fails with STALE + PATH NOT FOUND. Zero mention of this in the handoff body. Next session has no way to know whether the failures are known/fatal |
| 2 | FLEET-DEMAND-BROKER status is inconsistent | Roadmap L577 says `🔵 next` (in-review), Board L798 says `DONE`, description says "awaiting adversarial review". LAUNCHER-CRASH-PARTIAL-DETECT depends on it (L825) — wrong status blocks downstream |
| 3 | "8 of 12 landed" / "8 landed this session" unverifiable from board | Count of DONE tickets on board doesn't cleanly resolve to 8, and "8 of 12" is vague on which 12. Next session can't confirm progress |
| 4 | "sync-checkouts.sh before closing" required by handoff-check but never mentioned | Manager can't push; no instruction on who runs sync or how |
| 5 | Tab reference `:47361` (L140) is opaque | Next session has no PID/tab mapping — will not know which terminal/shell this referred to |

## False/unverified claims found

| # | Claim | Evidence | Severity |
|---|---|---|---|
| 1 | `419 commits` drift on substrate-first-gate-v2 | Actual: 444 | MEDIUM — diff stat is correct, just the count is wrong |
| 2 | RECONCILE-GATE-WIRED worktree at `.../RECONCILE-GATE-WIRED` | Path does not exist | HIGH — strands the session looking for work that isn't there |
| 3 | "4 commit(s) behind origin/master" (handoff time) | `a2e6671...7b2908b` → 0 ahead, 4 behind from origin perspective — seems correct if origin had 4 unreachable-on-local commits. But `git log --oneline a2e6671..7b2908b` would show ~2 unique. Handoff.sh's count methodology is opaque. | LOW — machine-queried but possibly overcounted |
| 4 | `36 models` / `2,567 served` / `216 of 859` / `5 of 52 params` / `5 of 9 gates` / `15 classes from 30+ incidents` | Unverifiable without live gateway/KSF access. These are audit findings from lane reports — flag as "trust but verify" | MEDIUM — if any number is wrong, downstream decisions on CATALOG-COMPLETENESS etc. are based on bad data |
| 5 | `216 of 859 catalog entries carry any context field` (L204) | Cannot verify. The `discover.py`/`cost_map.json` claim is sourced internally | MEDIUM |

## Smallest set of edits that makes it shippable

1. **Fix bootstrap path** (L14): `/home/stack/charon-private/fleet/SESSION-HANDOFF-satele-shan.md` → `/home/stack/charon-private-wt/NS-CONTENTION/fleet/SESSION-HANDOFF-satele-shan.md`
2. **Add note above bootstrap**: `⚠ handoff-check currently fails on this copy: STALE provenance (rig was behind origin at generation) + PATH NOT FOUND (file lives in ns-contention worktree). Fixes pending operator sync. Proceed with caution.`
3. **Fix 419 → 444** on L149
4. **Delete or moot RECONCILE-GATE-WIRED action item** (L140-144): PR #285 landed (7b2908b), ticket archived in e0bb409. Worktree `RECONCILE-GATE-WIRED` does not exist.
5. **Clarify FLEET-DEMAND-BROKER status**: Pick one — either it's DONE (update roadmap) or in-review (update board). Description says "awaiting adversarial review" which contradicts both.
6. **Note FIXTURE-BYPASS-GATE lacks board entry**: Either mint one or remove from "4 remaining LANDs"