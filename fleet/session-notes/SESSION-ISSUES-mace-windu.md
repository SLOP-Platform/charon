# Session issues + class-level fixes — mace-windu (2026-07-21)

Per §0 CLASS-LEVEL directive: each friction below is named at the class level, with the
mechanized fix and the ticket that owns it. **The unifying class is DECLARED-vs-REALITY DRIFT
(stale metadata outliving the thing it describes)** — it accounts for almost every issue this
session. Detection primitive = KS24 (lens-drift) + KS29 (registry-primitive); branch-subclass
prevention = merge-queue adopt (drift-tooling-audit TOP-5 #1).

| # | Issue hit this session | Class | Fix / owner ticket |
|---|---|---|---|
| 1 | 5 of 6 "stranded/at-risk" branches were already-landed (RIG-CI-GATE + 4); subagent over-counted at-risk 27 vs true 12 | stale-branch drift | Mechanized SUPERSESSION check (patch-id/blob vs master), not ahead-of-master. Owner: STRANDED-WORK-DETECT + VERIFY-MERGED-REPO-AWARE |
| 2 | My §0 land bumped master → in-flight substrate branch went 1-commit stale | serial-land base drift | Merge queue (auto-rebase). Owner: NEW adopt (drift audit #1 — GitHub merge queue) |
| 3 | 20 already-done-but-open tickets + stale done-markers on the board | done-marker drift | Reconcile-merged sweep. Owner: RECONCILE-MERGED-PERF + F2 auto-done-on-merge (GAP: not catching these) |
| 4 | BENCH-OOB parked as frontier-build but was VERIFY-ONLY; `depends_on: STAGE-DEMUX` (archived/landed #115) + build-after #20 (landed #107) both stale | stale-depends_on drift | Auto-clear satisfied deps / stale-dep detection. Owner: KS24 lens-drift applied to board deps |
| 5 | GATEWAY-LITELLM-ADOPT was board-"ready" but (a) not safely one-pass, (b) assign.py refused (money-path Claude-reserved) | board-ready ≠ dispatch-eligible | Decompose/parallelizability gate + surface assign.py refusal in ready-state. Owner: decompose gate (done for this ticket) |
| 6 | Manager land friction: raw `git merge`/`checkout` denied (correct); land-push refuses bare ref when HEAD≠branch; must use `land-push.sh <branch>:master` for non-FF | manager how-to gap | Document in handoff gotchas (below). Not a defect — a knowledge item that cost time |
| 7 | Loaded MANAGER-OPERATING-RULES.md is a growing verbatim file that decays (same class as old MEMORY.md) | growing-loaded-store decay | Migrate mechanizable rules → gates; loaded prose shrinks to §0 + judgment rules. Owner: COVERAGE-META-GATE (ready) + KS30 enforcement-spine |

## Handoff gotchas (manager how-to, so next session doesn't re-fumble)
- To advance rig master, the manager CANNOT raw `git merge`/`checkout` (denied). Use
  `bash fleet/land-push.sh <branch>:master /home/stack/charon-private` (src:dst form). land-push
  refuses a BARE ref when HEAD≠that ref (anti-stale-publish guard) — pass the explicit `src:dst`.
- After each land, origin/master moves; sync local (`git -C <repo> pull --ff-only origin master`)
  or the NEXT in-flight branch you built is already stale (issue #2).
- Subagent counts LIE (issue #1: "27 at-risk" →真 12 → mostly superseded). Always independently
  verify a subagent's numeric/verdict claims before acting (esp. before any prune/land).

## Net
Almost all of the above is ONE class. Recommend the next session's drift workstream = build/activate
KS24+KS29 (the reconciliation primitive) + adopt the merge queue, which collapses issues #1-4 at the
class level rather than re-fixing instances forever.
