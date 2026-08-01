# Charon Fleet — Session Handoff — saba-sebatyne (2026-08-01)

## Bootstrap (copy-paste into the next session)

```
Read /home/stack/charon-private/fleet/state/PRIORITY-TODO.md FIRST, then this file, then flip to fleet mode.
```

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

## Provenance

Session `saba-sebatyne`, 2026-08-01. Product `/home/stack/code/charon`, rig
`/home/stack/charon-private`. Real spend measured **$1.3372** across 50 opencode sessions
(`GET http://127.0.0.1:<port>/api/session`) while the gateway reported `usage.cost_usd = $0.000226`
— the gateway meter is fiction; opencode has ground truth.
