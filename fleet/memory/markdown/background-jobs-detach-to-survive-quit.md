---
description: Claude-in-session background tasks DIE on /quit; only setsid/nohup-detached jobs or separate tabs survive
metadata: 
name: background-jobs-detach-to-survive-quit
node_type: memory
originSessionId: a95dc541-223e-4053-8197-6848f0322d6b
type: reference
tags: [memory]
last_referenced: 2026-07-13
---
Whether a background job outlives a Claude Code `/quit` depends ENTIRELY on how it was launched:

- **Dies on /quit:** Claude's own `run_in_background` Bash tasks and sub-agents — they are children of the `claude` process; quitting sends SIGHUP to the process group and kills them. A prior session wrongly told the operator these survive; they do not.
- **Survives /quit:** a job **detached** from the session process group — `setsid`/`nohup … & disown`, or launched from a **separate terminal tab**. It reparents to `/init` and keeps running.

Confirmed 2026-07-10: the staged-fold `opencode run` survived because it was detached (PPID = `/init`, 157902).

**Fleet drain jobs MUST be launched detached** so they survive session end. Pattern used this session:
`setsid bash -c 'opencode run --model charon/kimi-k2.6-nw "$(cat BRIEF)" > LOG 2>&1' </dev/null >/dev/null 2>&1 &`
Verify with `ps -o ppid= -p <pid>` → should be the `/init` pid, not the `claude` pid. Log to a durable path (e.g. `build-rig/fleet/state/*.log`), NOT the session scratchpad, so the next session can read it. Relates to [[charon-headless-review-loop]] and [[all-work-in-subsessions]].
