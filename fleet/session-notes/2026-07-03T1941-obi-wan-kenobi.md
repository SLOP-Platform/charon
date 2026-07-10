# Session notes — obi-wan-kenobi — 2026-07-03T19:41Z

## What was attempted
Build T0 failover packages A-D on `src/charon/proxy.py`, `src/charon/proxy_server.py`,
`src/charon/gateway.py`, `src/charon/config.py`, `src/charon/cli.py`.

## What was actually done (no code changes)
1. Read SESSION-HANDOFF.md — fully parsed. Confirmed: 0 open PRs, 55 done, branch `feat/prod-install`.
2. Ran status.sh — all 55 tickets DONE, no live droids, no open PRs.
3. Ran validate_board.sh — 19 REDs (orphan done markers + bad WCI-FOLLOWON dep).
4. Discovered bridge daemon not running — started it manually (PID 276333).
5. Diagnosed bridge daemon/proxy socket mismatch:
   - Daemon creates socket at `~/.charon/bridge.sock`
   - Proxy defaults to `/tmp/charon-bridge.sock` when BRIDGE_SOCKET env var not set
   - The opencode.json `env.BRIDGE_SOCKET` is NOT being passed to spawned proxy processes
   - Symlink from /tmp to ~ didn't work (Unix sockets don't follow symlinks for connect())
6. After killing/restarting daemon, socket exists but connections return ECONNREFUSED.
   Root cause not yet determined.

## State
- No `src/` files were modified.
- Daemon process running at PID 277633 but socket connections rejected.
- Bridge MCP tools unavailable until daemon fix is deployed.
- Symlink `/tmp/charon-bridge.sock -> /home/stack/.charon/bridge.sock` created (harmless, can delete).

## Key unresolved issue
The bridge daemon socket path mismatch between daemon (`~/.charon/bridge.sock`) and
proxy default (`/tmp/charon-bridge.sock`). The `env` block in `opencode.json` is not
propagating BRIDGE_SOCKET to the MCP child process. Fix options:
- Option A: Patch daemon.py default to match proxy default (`/tmp/charon-bridge.sock`)
- Option B: Fix opencode.json env propagation (may be an opencode bug)
- Option C: Set BRIDGE_SOCKET in the proxy command args: `["python3", "-c", "import os; os.environ['BRIDGE_SOCKET']='/home/stack/.charon/bridge.sock'; exec(open('.../proxy.py').read())"]`

## Next session recommended bootstrap
1. Resolve daemon socket path mismatch (Option A is fastest)
2. Kill stale daemon, restart with correct path, verify `_forward` works
3. Then proceed to build T0 failover packages A-D
