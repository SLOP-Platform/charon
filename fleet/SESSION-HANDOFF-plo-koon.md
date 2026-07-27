# HANDOFF — plo-koon (2026-07-27) — READ THIS FIRST

## STATE (all clean/pushed as of writing)
rig `55a62f2` · product `f87d4ae` · board GREEN · 4-LOM on **v0.6.1**, all 4 deferred observables PROVEN LIVE.

## RUNNING RIGHT NOW
- `:47205` REVIEW-SUBSTRATE-SUPERSEDED (verdict pending) — prompt `prompts/REVIEW-SUBSTRATE-SUPERSEDED.md`
- `:47908` kill/focus research worker (subagent-owned)
- Check: `bash fleet/fleet-idle.sh` · `ps -eo pid,etime,args | grep '[o]pencode --'`

## THE ONE THING IN FLIGHT
Research agent owes: **focus variant "C"** (spawns a tab WITHOUT stealing focus — operator confirmed it worked, exact command not yet captured), plus SIGTERM-before-SIGKILL ladder, dead-tab `closeOnExit`, tmux comparison. Report: `fleet/handoff-notes/RESEARCH-SESSION-SPAWN-2026-07-27.md`.
**Next action:** wire C into `fleet/spawn-worker.sh`, then countdown-test while operator types.

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

## MODEL OBSERVATIONS
`fleet/handoff-notes/MODEL-OBSERVATIONS-2026-07-26.md` — TEMPORARY, delete when SW-PHASE0-GRADE-READ + DONE-SH(c) land. Key: **red-proof is NOT sufficient when the model picks the break** — both P0 gates passed self-chosen red-proofs and caught nothing. SPECIFY the break externally.
