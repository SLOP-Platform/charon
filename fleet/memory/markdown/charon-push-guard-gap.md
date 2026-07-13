---
description: Push control — manager pushes ONLY via the gated land-push.sh wrapper, toggled by the AUTONOMOUS lever; `git -C * push*` bypass now denied. Deny-list still structurally porous (interpreter shell-outs).
metadata: 
name: charon-push-guard-gap
node_type: memory
originSessionId: 2683d853-b25a-4778-9fb0-d458d14b54d2
type: project
tags: [charon, guard]
last_referenced: 2026-07-13
---
**Parked 2026-06-26.** `/repo/charon/.claude/settings.local.json` runs in
`bypassPermissions` mode with a **deny-list** that blocks `Bash(git push*)`,
`Bash(git push --force*)`, `Bash(git reset --hard*)`, `Bash(git remote add*)`,
`git rebase*`, `git commit --amend*`. Intent: nothing reaches the public remote and
no destructive history op runs without the operator doing it by hand (`! git push`).

**The gap:** those deny globs are anchored to commands that literally *start with*
`git push` / `git remote add` / `git reset`. The **`git -C <path> …`** form does NOT
match — so during the 2026-06-26 scrub, `git -C <mirror> push --force origin …`
reached the public repo **without the guard firing**. The outcome was authorized
(operator approved beforehand), but the mechanism bypassed an intentional guard.

**Broader than the `-C` form (independent reviewer, 2026-06-26):** the deny-list is
structurally porous, not just missing one glob:
1. `"defaultMode": "bypassPermissions"` → deny-only model; anything not explicitly
   denied runs with no prompt.
2. Allow-listed interpreters — `python *`, `python3 *`, `.venv/bin/* *`, `node *`,
   `npx *`, `make *`, `xargs *` — can each shell out a push, e.g.
   `python3 -c "import os;os.system('git push --force')"`, a Makefile target, or
   `xargs git push`. These bypass EVERY git deny rule.
3. Env-prefixed forms (`GIT_SSH_COMMAND=… git push`) don't start with `git`, so even
   `git * push*` won't match.

**UPDATE 2026-06-27 — push control reworked (the file is NOT Edit-denied anymore; the
agent edited it directly):**
- The manager now pushes ONLY through the sanctioned wrapper
  `build-rig/fleet/land-push.sh <branch> [repo]`, allow-listed as
  `Bash(bash /build-rig/fleet/land-push.sh:*)`.
- `Bash(git -C * push*)` added to the deny-list — the literal `-C` bypass is closed.
- `land-push.sh` self-gates on the **AUTONOMOUS lever** (`state/AUTONOMOUS`, git-ignored):
  OFF (default) = wrapper refuses, prints the operator push command (human checkpoint);
  ON = wrapper pushes (full-autonomous). Toggle: `bash …/fleet/autonomous.sh on|off|status`.
- The allow-rule is read at session start, so the first autonomous push in the session
  that added it may prompt once.

**Still porous (unchanged, by design — the lever is intentional-autonomy control, NOT a
hard boundary against a malicious agent):** `defaultMode: bypassPermissions` is deny-only,
and allow-listed interpreters (`python3 -c "os.system('git push')"`, `make`, `xargs`,
`node`) or env-prefixed `GIT_SSH_COMMAND=… git push` still bypass every git deny glob. A
hard fix would move `defaultMode` off `bypassPermissions`. See [[charon-repo-hygiene-audit]].