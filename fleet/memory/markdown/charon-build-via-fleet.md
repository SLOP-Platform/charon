---
description: "Build Charon with the charon-fleet robot-mode rig (ONE command per tab) — NOT bare `claude --bg`. Recurring drift to correct."
metadata: 
name: charon-build-via-fleet
node_type: memory
originSessionId: eaa099fd-f9c2-4e3e-b1af-040f07dd4472
type: feedback
tags: [build-rig, charon, fleet]
last_referenced: 2026-07-13
---
To run build work on Charon (tickets/waves), use the **charon-fleet robot-mode rig** at
`/build-rig/fleet/`. **ONE command per tab:**
`bash /build-rig/fleet/fleet-droid.sh <opus|sonnet|haiku>`. Each tab loops:
self-claim a tier-eligible ticket from the board → run ONE ephemeral `claude` session that
makes its own worktree off master, does the work, opens a **draft PR (base master)**, marks
it submitted → claim the next. Manager (the overseeing session): `board.sh` for status;
after reviewing+merging a PR on GitHub, `done.sh <id>` to unblock dependents. Add work by
dropping `board/<id>.md` (tier/branch/depends_on/owns/prompt) + a prompt in
`/build-rig/prompts/`. Full guide: `/build-rig/fleet/README.md`.

**Why (this is the correction):** the assistant repeatedly DRIFTS back to bare
`claude --bg` with bespoke per-ticket worktree+prompt commands. That is the WRONG method
and caused every WAVE-1 failure — file collisions, main-checkout contamination, a PR
merged to the wrong base (#7), and an editable-install hijack (a droid ran `pip install -e .`
inside its worktree, which we later deleted → broke `charon`). The fleet's atomic flock
claim + per-droid worktree + propose-default + visibility PREVENT exactly those. The
operator PROVED the one-command-per-tab + manager Droid model is right — do not re-litigate
it or revert to `--bg`.

**How to apply:** default to this rig for any Charon build wave. Default landing is
**PROPOSE** (draft PR, operator merges — ADR-0007 D4); never auto-merge. Charon cannot
self-orchestrate yet (the engine — run_parallel/decompose/`charon land`/worker-spawn — is
the unbuilt work, ADR-0007/0008), so this rig IS the build method until that ships. Built
from the audited [[droid-robot-mode-harness]] with two changes: propose-default landing +
ephemeral-per-ticket (no warden/reaper/loop). See [[charon-project-state]].
