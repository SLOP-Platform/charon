# SUBAGENT-WORKTREE-SANDBOX — review-log fragment

## What was produced
- `fleet/state/SUBAGENT-WORKTREE-SANDBOX-DESIGN.md` (NEW) — design doc evaluating four sandbox mechanisms for confining subagent/droid filesystem writes to their assigned worktree.

## Key decisions
- **ADOPT bubblewrap/bwrap** as the primary confinement mechanism: bind-mount the worktree rw, everything else ro via unprivileged user+mount namespaces. Maintained, flatpak-audited, no setuid.
- **REJECT landlock** — compiled into kernel but securityfs NOT mounted on WSL2 (no ABI exposed). Not portable enough; more novel glue than bwrap.
- **REJECT firejail** — suid-root binary with CVE history; full-suite capability is overkill for a single bind-mount primitive.
- **REJECT PreToolUse hook as primary** — ~5% escape (Bash builtins/heredoc bypass PreToolUse); Claude-only; model can disable hooks. Adopt as defense-in-depth complement only.
- **Coordinate with LEG-SANDBOX-HARDEN** — bwrap could optionally refactor the sibling's direct-unshare approach for consistency, but is NOT blocked (sibling already ships).

## Evaluation evidence
- User namespaces verified working on host (`unshare --user --map-root-user --mount true`, exit 0)
- bwrap available as `apt install bubblewrap` but COULD NOT BE INSTALLED (no sudo on this WSL2 host)
- landlock `CONFIG_SECURITY_LANDLOCK=y` in kernel config but `/sys/kernel/security/landlock/` nonexistent at runtime (securityfs not mounted)
- firejail available via apt but could not be installed; well-understood from docs

## Spawned follow-up
- BUILD ticket `SUBAGENT-WORKTREE-BUILD` specified inline in the design doc with full frontmatter, accept criteria (including fail-on-revert canary), and owns list.
