# Charon Fleet — Session Handoff — kanan-jarrus

**Date:** 2026-07-19
**Session:** kanan-jarrus

---

## Bootstrap (copy-paste into next session)

```
Read and fully follow /home/stack/charon-private/fleet/SESSION-HANDOFF-kanan-jarrus.md — your entire session is the CATCH-UP-AND-PREVENT mission defined there, and you are done only when its done-contract holds.
```

---

## THE MISSION (this is not a task list)

The next session is dedicated **entirely** to getting fully caught up and to making the
prevention tools actually work. It is a MISSION with a done-contract. Ticket count is not
the measure; the done-contract is.

### Done-contract — ALL of these must hold at session end

1. Zero uncommitted work anywhere — any remaining dirt explicitly recorded as disposable.
2. Every branch landed, covered by an open PR, or explicitly abandoned IN WRITING.
3. No disk-only refs — pin tags pushed, bundled, or mirrored.
4. Every done-marker carries verifiable proof.
5. Board green, zero phantom "done" tickets.
6. Rig CI actually running and enforcing.
7. Reaper safe, rig-aware, on a cadence — **dogfooded end-to-end, not merely unit-tested**.
8. Stranded-work audit fires on a trigger, not run by a session.

### Acceptance test

The session AFTER next must not need a hand-run branch audit. If it does, this mission
failed regardless of how many tickets were closed.

---

## WHY this mission exists (state plainly)

This problem has been re-discovered by hand in at least four sessions. The reason it keeps
coming back is that detection keeps getting **ticketed instead of built**, and the one tool
that does exist is manual and unsafe:

- `STRANDED-WORK-AUDIT` and `LAUNCHER-CRASH-PARTIAL-DETECT` are LIVE tickets on the board
  (`/home/stack/charon-private/fleet/board/STRANDED-WORK-AUDIT.md`,
  `/home/stack/charon-private/fleet/board/LAUNCHER-CRASH-PARTIAL-DETECT.md`) and have
  never been built.
- `DROID-LIFECYCLE-REAP` (rig #103) WAS built but **cannot merge — it deletes committed work**.
- `/home/stack/charon-private/fleet/branch-reaper.sh` exists but:
  - is invoked ONLY from `/home/stack/charon-private/fleet/land.sh` — no cron, no hook, no CI;
  - reaps ONLY the PRODUCT repo — the rig's 64 worktrees are never touched;
  - its worktree dirty-guard **does not gate**: a dry run reaped 39, kept 0, INCLUDING dirty ones.
- The rig repo has **no `.github/` directory at all** — nothing enforces anything on the rig.

Net effect: each session re-discovers the same backlog and files MORE tickets.
**Filing tickets has been substituting for landing.** Do not repeat that this session.

---

## NEXT / first actions — recommended ORDER, and why

Land the tooling FIRST, then let the tools perform the catch-up. That order dogfoods them.
Cleaning up by hand first would consume the whole session and leave the tools unbuilt again —
which is exactly how the last four sessions ended.

1. **`RIG-CI-GATE`** — nothing enforces anything on the rig today (no `.github/`). Land first.
2. **Fix `branch-reaper.sh`** — make the worktree dirty-guard actually gate, and make the
   tool rig-aware (it must see `/home/stack/charon-private` worktrees, not only the product repo).
3. **Land `DROID-LIFECYCLE-REAP` (rig #103)** using the fail-closed fix already written into
   its PR comment. Do not re-derive the fix; read the comment.
4. **`STRANDED-WORK-AUDIT`** — wire to a cadence/trigger. A session running it by hand does
   NOT satisfy the done-contract.
5. **Then the actual catch-up sweep**, executed BY those tools — this is the dogfood.
6. **`MARKER-PROOF-MECHANIZE`**, then **`INERT-INSTANCE-DETECT`**.

---

## State of record (code-confirmed 2026-07-19)

**Rig** `/home/stack/charon-private` — `Nnyan/charon-private`, `origin/master` = `3714307`
**Product** `/home/stack/code/charon` — `SLOP-Platform/charon`, `origin/master` = `ebaec2e`

### Landed today

Repo-aware `verify_merged`; W0 + W0b destruction guards; `land.sh` owns-scoping; foreman rc
semantics; draft convention; public-clean sweep (68 files); rig #90 / #113 / #115 / #107;
product #174 + #175; 86 done-markers backfilled.

### Closed with reasoning (not silently dropped)

- **product #171** — reverts the #167 metering fix AND deletes its regression test. CI was
  green *because the guard was removed*. Closed.
- **product #170**, **rig #104** — closed with reasoning recorded on the PR.

### Sent back with exact fixes recorded in PR comments

rig #101, #103, #105; product #169, #164, #161, #135, #86. The fixes are IN the PR comments —
read them rather than re-deriving.

---

## OPERATOR DECISION REQUIRED — 3 dirty worktrees (agent refused to guess)

| Worktree | State (confirmed) | Note |
|---|---|---|
| `/home/stack/charon-private-wt/WEB-ROADMAP-GENERATOR` | unresolved merge conflict `DU fleet/provider-exhaustion-ledger.tsv`; git refuses ANY commit | untracked board file `fleet/board/REVIEWER-DOGFOOD-REDS.md` there is therefore still disk-only |
| `/home/stack/code/charon-fleet-DECOMPOSER-ROUTE-THROUGH-SWITCHBOARD` | staged: `tests/test_decompose_planner.py` −85, `src/charon/recommend.py` ±4 | staged TEST DELETION on already-landed work |
| `/home/stack/code/charon-fleet-GATEWAY-NONTOKEN-METERING` | staged: `tests/test_gateway_nontoken.py` deleted (−68), `src/charon/gateway.py` −15/+3 | staged TEST DELETION on already-landed work |

The latter two are the **same shape as product #171** — deleting the guard that proves the
feature. Not committing them loses nothing. Do not commit without an operator decision.

---

## Refs, branches, backlog

- 27 branches were pushed this session. All 5 formerly disk-only pin commits are now
  reachable from a pushed branch.
- **Pin tag REFS remain local only** — a remote pre-receive hook rejects tag pushes. That hook
  is **unexplained and worth investigating**.
- A verified bundle of the pin tags exists. It was written to a *session scratchpad*, which is
  ephemeral, so it has been copied to a durable location:
  **`/home/stack/pin-tags-20260719.bundle`** (`git bundle verify` → "records a complete history").
  Do not rely on any scratchpad copy.
- Unlanded-work backlog: **~27 rig / ~35 product branches**.
- **Four have a CLOSED PR but unlanded content: rig #81, #57, #56, #104.** Decide each
  explicitly. Do NOT assume "closed PR" means "abandoned".

---

## GOTCHAS — avoid re-discovering these (several are DENIED operations)

- `git merge`, `git rebase`, `git reset --hard`, and raw `git push` are **DENIED** to the
  manager. Push only via `/home/stack/charon-private/fleet/land.sh` (feature branch) or
  `/home/stack/charon-private/fleet/land-push.sh` (committed branch/master).
- **`git merge-base` is caught by the `git merge` deny-list.** Find another route.
- **`/home/stack/charon-private/fleet/validate_board.sh` is only board-accurate in the LIVE tree**,
  never in a worktree.
- **Handoff claims must be code-confirmed.** The PREVIOUS handoff was wrong in three places:
  the "8 stuck tickets" were actually 2; SR-1…SR-8 had a different root cause; REPO-DECL-CENTRAL
  was a phantom. **That warning applies to THIS handoff too — verify before acting.**
- **Tool output lies in BOTH directions.** `land.sh` reported success while pushing the WRONG
  commit (`522c147`). `gh pr merge` printed a failure AFTER succeeding. Always verify with
  `git ls-remote` or the API — a success message is not proof.
- **`ps` cannot see subagents.** File mtimes are the only liveness signal. A background agent
  blocked on a permission prompt for hours looks identical to one working.
- **Never write into a worktree an agent owns.**
- **Never say "run the full test suite" in a brief** — it pulls benchmark grader tests that
  invoke live models and block for hours. Name the specific suites, every time.
- **Do not create a board ticket for work already built** — it invites a droid to claim and
  clobber it (this cost commit `32254b3`, recovered).
- **Adversarial review is non-optional for anything that deletes or publishes.** It found real
  defects on 3 of 3 destruction-path changes this session, every one invisible to the author's
  own passing tests.
- **Vacuous assertions appeared 5+ times** — assertion count is not coverage. One suite grew
  6 → 15 assertions while leaving the single new hole uncovered.
- **`pr-audit.md`'s CLEAN verdicts predate current board rules.** Re-simulate before trusting
  them — stale CLEAN verdicts are what blocked rig #107.
- **`.gitignore` is an anchor file.** Rig #107 took it; rig #47 / #93 / #96 / #97 now conflict
  textually and each needs an append-only rebase that keeps BOTH lines.

---

## Still open (carry forward)

- `RIG-CI-GATE` — see `/home/stack/charon-private/fleet/board/RIG-CI-GATE.md`.
- `INERT-INSTANCE-DETECT` — 6 gateway modules are constructed but never invoked, and
  `check_inert_code` reports **green**. Today's green IS the defect.
  See `/home/stack/charon-private/fleet/board/INERT-INSTANCE-DETECT.md`.
- `MARKER-PROOF-MECHANIZE` — `/home/stack/charon-private/fleet/board/MARKER-PROOF-MECHANIZE.md`.
- `land.sh` still does **not** secret-scan.
- `/home/stack/v5/docs/tools/check_push_status.sh` lives OUTSIDE both repos — operator action.

---

## session-bridge

Register on the session-bridge board before claiming any of the work above, and check it for
collisions first — the reaper and CI work touch shared rig files. If you inherit a timed-out
session, pick a NEW Jedi name; do not reuse `kanan-jarrus`.

---

## Files committed by this handoff

| File | Change |
|---|---|
| `fleet/SESSION-HANDOFF-kanan-jarrus.md` | this handoff |
| `fleet/session-notes/2026-07-19-public-clean-sweep-removed.md` | stray session note, committed so nothing is left uncommitted |
