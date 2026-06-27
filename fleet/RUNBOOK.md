# Charon fleet — manager RUNBOOK (handoff)

> **ROLE (read first):** The MANAGER session watches + gates ONLY. It NEVER launches
> droids (no `fleet-droid.sh`/`claude --bg` from the manager). The OPERATOR opens droid
> tabs. See memory `manager-never-spawns-droids`. First acts of a fresh session: read
> `MEMORY.md` + `docs/DECISIONS.md`, run `status.sh` + `board.sh`, then resume gating.
>
> **PRE-WAVE GATE (added 2026-06-27 after the capacity.py double-claim + E10 missing-prompt):**
> run `bash validate_board.sh` BEFORE naming any tab to launch. RED = a missing prompt, a
> double-claimed path, a bogus dep, or a colliding branch — fix first. Ownership lives in ONE
> place (`board/<id>.md` `owns:`); prompts must NOT restate a wider file list. Root cause was
> dual, hand-authored, never-cross-checked ownership specs.

## State as of 2026-06-27
- Merged: N1,N2,T7,T8,N4,N5 + ADRs/Decision-Register + **E0** (boundary guard).
- **OPEN but CI-RED (do NOT merge as-is):**
  - **S1 (#22)** — fails `ruff` lint in `tests/test_config.py` (E402 + import sort). Code otherwise fine.
  - **E1 (#23)** — fails E0's boundary scan, but **E1's code is CORRECT** (standard relative imports `from .board`/`from ..ledger`). Root cause = a bug in E0's `check_boundary.py` (doesn't allow relative imports). Fix = ticket **FB1**.

## Recovery (do this first)
1. **FB1** (ready, sonnet) → fixes `check_boundary.py` to allow relative imports. Open 1 sonnet tab. Gate + merge + `done.sh FB1`.
2. **E1** → after FB1 merges, E1 needs the fix on its branch. Cleanest: close PR #23, `release.sh E1`, re-run E1 (1 opus tab) off updated master. (No-waste alt: merge master into `feat/engine-board-claim` to pull FB1, re-run CI, merge.)
3. **S1** → close PR #22, `release.sh S1`, re-run S1 (1 sonnet tab). (No-waste alt: push a `ruff --fix` commit to `feat/sandbox-policy`.)

## Launch sequence (one-line; "open N <tier> tab(s)" = operator action)
Each tab runs `bash /home/stack/charon-private/fleet/fleet-droid.sh <tier>`; the droid
auto-loads the ticket prompt via the board. A ticket unblocks only AFTER the manager
merges + `done.sh` its dependency (propose-default).

| After manager merges | Now eligible | Operator opens | Concurrency |
|----------------------|--------------|----------------|-------------|
| FB1 | E1 (re-run) | 1 opus | 1 |
| E1 | E2 | 1 opus | 1 |
| E2 | **E3**(sonnet) · **E4**(opus) · **E10**(opus) | 1 sonnet + 2 opus | **3 (peak)** |
| E4 | E6 | 1 opus | 1 |
| E6 | E8 | 1 opus | 1 |
| E8 | E9 | 1 opus | 1 |
| E9 | E7 | 1 sonnet | 1 |
| (anytime) | S1 (re-run) | 1 sonnet | parallel |

Peak useful parallelism = **3** (E3+E4+E10 after E2). Elsewhere 1 opus is the ceiling —
the critical path is sequential and dependents unblock only on the manager's merge.

## Two-opus / pre-staging note
`fleet-droid.sh` does NOT idle-wait: if no ticket is eligible for its tier it stands down
(exits) immediately. So a pre-launched 2nd opus tab won't "wait" for E2 — it exits. To get
"ready the instant it ungates," either (a) open the 2nd opus tab the moment E2 merges, or
(b) add a `--wait` poll mode to fleet-droid.sh (on empty claim: sleep+retry instead of
break; idle tab just sleeps, no claude session until it claims). (b) is a small rig tweak —
operator-approved before changing the harness.

## Deferred (NOT ticketed, by decision) — see docs/DECISIONS.md
D005 WorkerBackend port (until a non-ACP worker); D015 verified isolation (promote as the
safety pair for auto-land/Phase-2 per D016).
