# TIER-BALANCE promotion pass — 2026-07-24

Board commit: `c155a82` on master (`/home/stack/charon-private`), pathspec-limited, 8 files.

## Re-derivation (did NOT trust the quoted list)
Ran `tier_classify.py deltas|drift --board /home/stack/charon-private/fleet/board` from the
branch worktree at `feat/tier-classifier` HEAD `c8c1f13` (newer than the `f1f162c` the ticket
records). Result: 35 deltas over 120 declared tiers; **9 hard-fail REDs**, identical set to the
one recorded on TIER-BALANCE. `drift` rc=3 before the pass.

## Applied — 7 promotions to `frontier` (operator-approved)
| id | change | reason |
|---|---|---|
| BOUNCE-1 | strong → frontier | security surface: real-SUT egress/header exfil canary; SEC_RE ratchet |
| FIX-PROVIDER-KEY-EXFIL | strong → frontier | security surface: provider-key exfil path; SEC_RE ratchet |
| FT-WIRE-QUOTA | strong → frontier | money-path, livefwd=1, d4, measured effort 12.6 |
| GATEWAY-GRADE-ORDER-MVP | strong → frontier | money-path/routing, d5, measured effort 13.6 |
| GW-CUTOVER-LIVE-WIRE | strong → frontier | money-path, livefwd=1, d5, measured effort 13.6 |
| ORDER-A-COST-PRIMARY-LAND | strong → frontier | money-path, livefwd=1, d3, measured effort 10.75 |
| WIRE-GRADING-PRIOR-LIVE | strong → frontier | money-path, livefwd=1, d3, measured effort 10.3 |

Each edit flips the `tier:` line ONLY, byte-identical to the branch's own edit of the same file,
so the merge resolves with no conflict.

## Applied — 2 money-floor promotions (approval EXTENDED mid-pass)
| id | proposed direction | reason given by classifier |
|---|---|---|
| FT-LIMITS-GROQ-RECONCILE | economy → **strong** | money floor, d2, measured effort 7.3 |
| ROUTER-LEDGER-DECAY | economy → **strong** | money floor, d3, measured effort 10.3 |

All 9 re-derived from my own `deltas` run at branch HEAD `c8c1f13`, never from a relayed direction.
Board commits on master: `c155a82` (7 frontier), `f11b183` (2 money-floor), `4e1715f` (land record).

## Gate results (by EXECUTION)
- `bash fleet/validate_board.sh` on master after apply → **rc=0 GREEN**.
  (Non-blocking advisory in output: `parallelizability-gate.sh scan` timed out at 15s — pre-existing,
  not caused by this pass, reported not fixed.)
- Branch classifier `drift` vs live board, all 9 applied → **rc=0, ZERO REDs**.

## LAND ATTEMPTED — REFUSED rc=4 (NOT rc=8, and not about the tier decisions)
`bash fleet/land.sh feat/tier-classifier /home/stack/charon-private-wt/TIER-BALANCE` → **rc=4**,
`land: GATE RED ... refusing to land`. Two REDs, neither of them one of the 9:

    RED tier-drift: FT-CATALOG-SEED  declared=frontier derived=strong   (money floor d2 effort7.45)
    RED tier-drift: PRICE-REFRESHER  declared=strong   derived=frontier (money+ livefwd=0 d3 effort40.3)

**Mechanism finding — the brief's proof design could not have caught this.**
`fleet/land.sh:298-299` builds its gate as `bash $REPO/fleet/validate_board.sh $REPO/fleet` with
`$REPO` = the WORKTREE. The gate grades the **branch's own copy** of `fleet/board/`, not the live
board. So "drift clean against the live board" (which I proved, rc=0) does not predict the land gate.
Anyone re-running JOB 2 as specified will again get a clean proof and again get rc=4.

**Root cause:** `feat/tier-classifier` is **41 commits behind master**, ~85 `fleet/board/*.md`
diverged. FT-CATALOG-SEED and PRICE-REFRESHER are precisely the two the ticket records as "fixed on
master that day"; the branch still holds their pre-fix tiers, so its stale board self-fails 2f.

**The precondition is now satisfiable:** `depends_on: REPO-FIELD-REQUIRED` HAS landed — master's
`fleet/validate_board.sh:100` carries its `repo:` check. The accept: clause "Rebased onto landed
REPO-FIELD-REQUIRED before land" is the actual remaining work and is no longer blocked.

**Not attempted here, deliberately:** a 41-commit rebase across ~85 board files, near-certain to
conflict on the 36 `tier:` lines this branch owns, is a reconcile — not a board write — and the
brief forbade hand-reconciling. Sequence for whoever picks it up:
1. rebase/merge `feat/tier-classifier` onto master in `/home/stack/charon-private-wt/TIER-BALANCE`
2. re-run `tier_classify.py board-retier` (the `owns_data:` sanctioned re-apply path)
3. re-run `land.sh` — all 9 promotions are already on master, so 2f should come up clean

Also outstanding: the MAIN checkout is dirty with another lane's board-archive WIP (4 deleted
`fleet/board/*.md` + 4 untracked `fleet/board/archive/*.md`). It did NOT cause this rc=4, but it is
the documented cause of `land.sh` rc=8 and should be settled before the retry. My commits were all
pathspec-limited, so that lane's WIP was never swept.

## Ticket-done status
- F11 (OQ-2) is DECIDED and IMPLEMENTED on the branch — `deltas` shows the review-class ratchet
  firing ("F11: capability never traded down") on BLAST-TIER-ENFORCEMENT-DESIGN,
  INERT-WIRING-ENFORCEMENT-DURABLE, PRICE-TRACKED-INVENTORY-AUTOSWAP, REVIEW-RECONCILE-GATE-DESIGN,
  SUBAGENT-WORKTREE-SANDBOX, UNIFIED-RECONCILIATION-GATE-DESIGN, WORKLOOP-INTEGRITY-STACK-SPIKE.
- F5 (OQ-1) is answered in MECHANISM by the adopted effort scorer (hard 16.0 band +
  `EFFORT_DIFFICULTY_FLOOR=3`, so breadth alone can no longer promote), but the ticket's own
  `accept:` requires the difficulty-estimation research pass to land and be RECORDED before F5 is
  closed. That has not been recorded here.
- **TIER-BALANCE cannot be marked done**: (a) branch not landed, (b) F5 research answer not written
  back into the ticket.
