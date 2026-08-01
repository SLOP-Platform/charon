# Charon Fleet — Session Handoff — saba-sebatyne (2026-08-01)

## Bootstrap (copy-paste into the next session)

```
Read /home/stack/charon-private/fleet/state/PRIORITY-TODO.md FIRST, then this file, then flip to fleet mode.
```

---

# ⛔ FIRST SIX ACTIONS (operator-set at close — do these before anything else)

0. **RESCUE** — push the 47 local-only branches (96 commits exist ONLY on this box). Before building anything.
1. `feat/stranded-work-detect-v2` — 1 commit, NO remote. The stranded-work detector is stranded.
2. `feat/session-end-push-gate-v2` — 3 commits, NO remote. Built, never pushed.
3. `HANDOFF-NAME-ALLOCATOR` — archived+DONE and STILL BROKEN. Verify the firing layer.
4. `SESSION-END-GATE-REPAIR` — LIVE, UNCLAIMED. Ticketed, never scheduled.
5. **Adopt a tool to run the loss-gate CONTINUOUSLY in the background** — a close-gate never fires
   when a session dies on a token limit or crashes. Try monit first (already adopted by the rig).
   **LAUNCH THIS IN A TAB FIRST, IN PARALLEL WITH 0** — it is research and blocks nothing.
6. **GATE DEFECT** — `land-push` refuses `fix/shared-namespace-contention` as *"code owned by NO
   live board ticket"*, but the ticket IS on origin/master (`f8266ef`) and owns exactly those 4
   files. Diagnose it; do NOT `--force`. A gate that blocks legitimate work is how `--force` habits
   start.

**Ordering:** RESCUE is 0 because it is the only IRREVERSIBLE item — 96 commits on one disk, and the
gate protects only FUTURE work. Rescue is minutes; the gate is hours. The last two sessions built
the fix first and lost it to the very class it fixes. **0 and 5 start together; 5 finishes last.**

Launch these in TABS. Full detail + the required loss-class coverage: `PRIORITY-TODO.md` §START HERE.

---

# ⛔ READ THIS FIRST

**The carry-forward list is `fleet/state/PRIORITY-TODO.md`, not this file.**
It holds every outstanding item, decision and approval, grouped A–I with status. This handoff is
provenance only.

**Why it is a separate file:** the inbound handoff was **1,286 lines / ~58,000 tokens against a
25,000-token read cap** — unreadable in one pass, and machine-generated state dwarfed the
human-authored part. This one is deliberately short. Do not grow it; grow PRIORITY-TODO.md.

**Do not re-litigate section G of PRIORITY-TODO.md.** Those are settled decisions with measurements
attached (session comms, TUI context reset, model-grading shape, catalog-is-live-data).

---

## The one-paragraph state

Nine droid tabs, three reviewer tabs and one bridge worker were running at session end; in-flight
work was allowed to finish but **no new work was launched**. Master is clean and pushed. The
session's biggest finding: **~20% of installed tool capability is switched on**
(`fleet/state/TOOL-UTILIZATION-AUDIT.md`) — the failure mode is not missing tools, it is default
configuration accepted as a tool's full surface. Four EVAL-REGISTRY rows were reclassified
drifted/mixed under a NEW anti-pattern registered today, **"under-scoped trial"**: an eval that
genuinely runs a candidate but configures the INCUMBENT too narrowly, so the candidate wins a
comparison it should have lost. One of those rows was written by this session, the same day, and is
self-corrected.

---

## Landed on origin/master this session

| what | detail |
|---|---|
| `LAUNCHER-GATE-SETE-KILL` (PR #356) | a RED gate KILLED the whole pool tab under `set -e`; `GATE_EXIT=$?` was unreachable on failure. Root cause of the measured 24% pipeline rate. 15/15 tests, 13 FAIL on revert |
| `RIG-CI-BASE-DEFAULT-BRANCH` (#357, merged) | board check diffed against the branch's own tip, so 2nd pushes produced FALSE "code owned by NO ticket" REDs. 8/8, 3 FAIL on revert |
| `LEDGER-NO-EVIDENCE-NO-VERDICT` (#358, merged) | rc=1 with an EMPTY tail was charged to the MODEL. A grade is an accusation; no evidence ⇒ no verdict. 12/12, 3 FAIL on revert |
| doctrine **§14** | catalog is LIVE DATA — model names and free status rot; every static list must be API-refreshed at EVERY consumer |
| EVAL-REGISTRY | comms sweep (16 candidates) registered; ruff row added; 4 rows reclassified; `under-scoped trial` anti-pattern registered |
| durable docs | `PRIORITY-TODO.md`, `TOOL-UTILIZATION-AUDIT.md` (git-tracked via `.gitignore` negations) |
| board | RED→GREEN repeatedly; 5 pre-existing unparseable tickets fixed; ~10 tickets minted |

## Built, NOT pushed / NOT merged

- `AUTO-DONE-ON-MERGE-MISS` — committed `9b69739`, branch 83 behind master. **PR #339 should be
  CLOSED, not merged** (it reinvented an inert copy; the real cause was `reconcile-merged.sh` being
  repo-blind to all 196 rig tickets). 19/19, 11 FAIL on revert.
- `BOARD-FRONTMATTER-GATE` — committed, unpushed. 61 assertions, 4-way red-proof.
- `PR-QUEUE-REST-ETAG` — pushed, unmerged. 40/40, 8-way red-proof, zero-quota steady state.
- `BROKER-BARE-TIER-LEGS` — pushed, **deliberately HELD** pending `GRADE-MODEL-PROVIDER-PAIR`.

## Bounced with evidence (comments posted)

**#207** money-path — a strict no-op (10 of 861 models priced; chain already sorted with the same
key; the latency sort discards it) plus a false safety claim. **#346** — would make the reviewer
pool review NOTHING. **#342** — the drift-correction PR reintroduces drift on rows stamped
`aligned`.

## Gotchas (beyond the standing DENIED list)

- `git merge` / `git rebase` are deny-listed; use `reset --hard origin/master` + `cherry-pick`.
- An EVAL-REGISTRY row may NOT land in the same push as the ticket citing it.
- `board-lock` pins a base sha — a plain-`git` commit on master invalidates it; release+reacquire.
- Non-board commits on master need `board-hygiene` or `land:` in the message, or work-lease refuses.
- **`handoff.sh` refused `SESSION=saba-sebatyne`** — the known self-blocking allocator bug
  (operator action #20), hit live at session close. This handoff was written directly.
  `SESSION-END-GATE-REPAIR` was claimed by a tab; verify whether it landed.
- Full friction list with fixes: **PRIORITY-TODO.md §I**.

## Live state pointers (regenerate — do not trust a snapshot)

```
bash fleet/report.sh          # roadmap + totals
bash fleet/pending.sh         # operator actions (#21-23 are new)
bash fleet/preflight.sh       # foreman + claimable depth
ls fleet/state/claims/        # what tabs hold
```

## Provenance (anti-clobber — verify this matches the filename before trusting anything here)

**Session:** saba-sebatyne
**Generated:** 2026-08-01 (written directly — `handoff.sh` refused this session's own name, the
known self-blocking allocator bug, operator action #20 / PRIORITY-TODO §J)
**Rig HEAD at close:** see `git -C /home/stack/charon-private log -1 origin/master`

Session `saba-sebatyne`, 2026-08-01. Product `/home/stack/code/charon`, rig
`/home/stack/charon-private`. Real spend measured **$1.3372** across 50 opencode sessions
(`GET http://127.0.0.1:<port>/api/session`) while the gateway reported `usage.cost_usd = $0.000226`
— the gateway meter is fiction; opencode has ground truth.

## session-bridge (live board at close)

Registered on the bridge as `saba-sebatyne` (repo `charon`, model `claude-opus-5[1m]`).
One stale peer present: `plo-koon`, lease expired 2026-07-27, status `escalated` — a ghost row.

> **Do NOT trust this board.** The bespoke session-bridge was slated for RETIREMENT on 2026-07-26
> in favour of opencode's HTTP control plane, and is still dual-running (3,073 LOC, ~10 sidecars,
> 3 daemons — one stale since Jul 26 — an SSH tunnel, and MCP entries in BOTH client configs).
> It was MEASURED showing **3 rows for 8 live workers — 2 real, 1 ghost** — because registration is
> a model decision, not a fact. Use `fleet/session-ctl.sh` (`/api/session/*`) for real worker state.
> `fleet/session-registry.tsv` is EMPTY except its header, so name→port resolution does not work yet.
> Full detail + the retirement plan: PRIORITY-TODO.md §G.
