# HANDOFF — plo-koon (2026-07-27) — READ THIS FIRST

## STATE (all clean/pushed as of writing)
rig **`d391f46`** · product `f87d4ae` · board GREEN · 4-LOM on **v0.6.1**, all 4 deferred observables PROVEN LIVE.
(If this SHA is stale, trust `git -C /home/stack/charon-private log --oneline -1`, not this file.)

## RUNNING RIGHT NOW
- `:47205` REVIEW-SUBSTRATE-SUPERSEDED — **DONE, verdict NOTHING-SURVIVES** (report written). Tab idle, closeable.
- `:47908` research worker — **GONE** (research completed).
- ⚠️ Two dead tabs need manual Ctrl+D: `FOCUSTEST-A`, `FOCUSTEST-C` (window 1, idx 2-3).
- Check: `bash fleet/fleet-idle.sh` · `ps -eo pid,etime,args | grep '[o]pencode --'`

## IN FLIGHT — NOTHING. Both research strands COMPLETE and WIRED.
Full report: `fleet/handoff-notes/RESEARCH-SESSION-SPAWN-2026-07-27.md` (1023 lines).
- **Focus fix WIRED** into `spawn-worker.sh`: `wt -w 1 new-tab ... ';' focus-tab -t "${CHARON_WT_HOME_TAB:-0}"`. The `';'` MUST be a quoted standalone arg. ~40-90ms residual, holds across a 4-spawn fan-out. Fails only if the operator types in a DIFFERENT wt window.
- **`fleet/stop-worker.sh <PORT>` NEW**: verified ladder port->PID->`kill -INT`->`-TERM`->`-KILL`. INT/TERM exit 0 in <1s, port refuses, **WT tab auto-closes**. SIGKILL exits 9 and LEAVES TAB LITTER — fallback only. Verifies pid-gone AND http-000.
- **There is NO HTTP stop.** `/tui/execute-command` is inert even with real dot-form ids (`app.exit`, `session.interrupt`). Question CLOSED — do not re-investigate.
- **Hard kill is SAFE**: store is SQLite+WAL, reads cleanly after mid-turn kill; siblings unaffected; only the in-flight turn is lost.
- **tmux-in-one-WT-tab verified structurally better** (`new-window -d` = ZERO focus change, `capture-pane` = free progress probe, no tab litter) but costs tab ergonomics. Recorded as the fallback if focus-C ever regresses.

**NEXT ACTION:** operator wants a countdown-then-launch test of the focus fix WHILE THEY TYPE. Ask first (see rules).

## OPERATOR RULES SET TODAY (hard)
- **ASK BEFORE LAUNCHING ANY TAB.** No spawning while they type.
- Concise reports: subs / issues / NUMBERED decisions / status. Then WAIT.
- Give full copy-pasteable commands; say which HOST (Tardis vs 4-LOM).
- "unpark X" = TRIAGE first, surface, WAIT. Never unpark-then-fix.
- Keep `fleet/pending.sh` list current; print at session start / on add / on clear.

## WHAT WAS BUILT TODAY (all landed)
`spawn-worker.sh` (named+coloured WT tabs, readiness gate, /tui inject, verify) · `session-ctl.sh` (list/steer/stop/reply/watch/resolve/launch/board) · `land-ticket.sh` · `fleet-idle.sh` · `verify-hot-rotation.sh` · SESSION REPORT v1 + `check-session-report.sh` (16 fields incl. BUDGET) · 3 gates (DOGFOOD, INV-SW2, INERT-STARTUP-CHECK) all externally red-proofed.

## HARD-WON FACTS — DO NOT RE-DERIVE
1. **Two-dot diff LIES.** `git diff master..<b>` shows master's later adds as branch deletions. Caused 2 WRONG destructive verdicts. Use `master...<b>` (three dots); for "already landed": `P=$(git diff --name-only master...<b>); git diff --stat master <b> -- $P` (empty=landed). Commit-count NEVER proves landed (squash).
2. **`/tui/*` returns `true` UNCONDITIONALLY** — means "published", not "received". `/api/health` goes healthy BEFORE the TUI attaches; injecting in that window is silently dropped. Gate on health && established>0.
3. **`session-ctl launch` on a TUI worker creates ORPHAN sessions** in the global store. Use `/tui/append-prompt` + `/tui/submit-prompt` on the worker's port.
4. **`/api/session/active` is NOT a liveness signal** — returns `{}` even for working sessions.
5. **`-w 0` follows GUI focus, NOT the manager's window.** `-w 1` / `-w <name>` works. `$WT_SESSION` is a pane guid.
6. **`deepseek-v4-flash` has an upstream 48-request session cap** — silently truncates, still reports DONE. Do NOT use for derivation-heavy work.
7. **Free tiers pass a 1-shot probe then collapse under session load**: `minimax-m3-free`, `gemini-3.1-pro`. Sustained: `deepseek-v4-pro`, `minimax-m3-together`.
8. **opencode default model is `gpt-5.4` = DEAD pool.** Always pass `--model`.
9. **Bridge already detects stalls** (`stalled`, `stall_seconds`, auto-nudges) — nothing consumes it. Do NOT build a 2nd liveness notion (see DROID-LIFECYCLE-REAP).
10. Manager CANNOT `git merge` (deny-listed) — operator merges; manager pushes via `land-push.sh`. Board files need `board-lock.sh commit`. Merge commits need `BOARD_LOCK_BYPASS=1` (git forbids partial commit during merge).

## OPEN DECISIONS / WORK
- Substrate branches (`feat/substrate-first-gate`, `-v2`) UNLANDABLE — master already has the gate (`03ba2b1`+`06b1764`). Awaiting :47205 verdict on what survives.
- `salvage/preflight-verify-merged-ghcache-wip` = **ABANDON** (deletions REAL, would remove live infra).
- BACKLOG-A: 2 REWORK, 1 UNSAFE, 1 LAND-WITH-CAVEAT. BACKLOG-B: 4 LAND — not yet landed.
- P0 open: GRADE-PROVENANCE-DIVERGENCE, MONIT-INSTALL-ENABLE (unblocked), CLIENT-MODEL-LIST-CONVERGE, BRANCH-SPRAWL-ROOT-CAUSE, SEED-PRIOR-REFRESH (gated on WIRE-GRADING-PRIOR-LIVE).
- Bridge Phase 2 (migrate 5 remaining consumers, then delete 3073 LOC) not started.

## ⚠️ TWO HAZARDS FOUND (unactioned)
1. Workers spawn a `scoop install opencode@1.18.5` child that **SURVIVES a process-group kill**. `stop-worker.sh` kills the listener pid only — the stray may persist. Check `pgrep -f scoop` after stops.
2. **`~/.local/share/opencode/opencode.db` is 6.5 GB.** Unmanaged growth, no rotation. Nobody has looked at why. Worth a ticket.

## SUBSTRATE BRANCHES — RESOLVED
`ADVREVIEW-SUBSTRATE-SUPERSEDED.md`: **NOTHING-SURVIVES.** Master's landed gate (`03ba2b1`+`06b1764`) covers everything. **Both `feat/substrate-first-gate` and `-v2` can be ABANDONED** — ~4000 lines of merge risk deleted. Do NOT attempt that merge (13 conflicts, 3 add/add).

## MODEL OBSERVATIONS
`fleet/handoff-notes/MODEL-OBSERVATIONS-2026-07-26.md` — TEMPORARY, delete when SW-PHASE0-GRADE-READ + DONE-SH(c) land. Key: **red-proof is NOT sufficient when the model picks the break** — both P0 gates passed self-chosen red-proofs and caught nothing. SPECIFY the break externally.
