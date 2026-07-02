# CWD-CONFIG-VERIFY — verify opencode ACP reads config from git repo CWD

## Dependencies & sequence
**depends_on: NONE — Wave 2 (unblocks ORCH-ROUTE if verified).** Research-only; no src/ files.

## Why
The opencode config docs say: "When OpenCode starts up, it first looks for a config file in the current directory, then traverses up to the nearest Git directory." If ACP mode honors this, we could write a per-run `opencode.json` in the worktree and launch `opencode acp` from there — unblocking ORCH-ROUTE.

## STEP 0 — verify (tested 2026-07-01)
Created a temp git repo with `opencode.json` containing a custom provider pointing at a probe proxy. Launched `opencode acp` with cwd set to the repo. Sent ACP protocol messages. **Result: 0 proxy hits — NOT HONORED.** ACP mode ignores project-local `opencode.json` in a git repo.

Same root cause as opencode#34638: ACP mode bypasses the standard config initialization pipeline.

## What to build (blocked)
Once opencode fixes ACP config initialization:
1. In `charon work`, write a temporary `opencode.json` to the worktree with per-run provider config
2. Launch `opencode acp` from the worktree directory
3. The ACP subprocess reads the worktree's `opencode.json` and routes through our proxy

## CONSTRAINTS
Research-only until opencode fixes ACP config. No product src changes possible yet.
