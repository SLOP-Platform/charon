# Stage 7-C report — SSH tunnel + cross-host config + verify

**Scope:** charon coordinator only (per brief). mediastack tunnel/socket NOT
set up this stage (Roci's `mediastack.sock` exists from 7-B but has no
forward). Local bridge (`~/.charon/bridge.sock`, PIDs 666424/668312, session
`yoda`) confirmed untouched throughout (same PIDs/mtime before and after).
opencode not restarted.

## Tunnel mechanism — fallback wrapper, NOT systemd

`Bash(systemctl *)` is explicitly denied in
`/home/stack/code/charon/.claude/settings.local.json`'s deny-list (with
`service *`, `journalctl *`, etc.) — a deliberate safety guard, not treated
as a bug or worked around. Per the brief's own fallback clause, used a
**documented persistent wrapper** instead:

- `/home/stack/.charon/coordinator-tunnel.sh` — `while true` reconnect loop
  running `ssh -N -L <localsock>:<remotesock> rocinante` with
  `ServerAliveInterval=15 ServerAliveCountMax=3 ExitOnForwardFailure=yes
  StreamLocalBindUnlink=yes BatchMode=yes`; 5s backoff between retries; logs
  to `~/.charon/coordinator-tunnel.log`.
- Launched via `setsid nohup bash coordinator-tunnel.sh &` + `disown` —
  fully detached from this shell (new session, PPID 1-rooted after
  disown), survives this shell exiting. Currently running:
  `bash coordinator-tunnel.sh` PID 857371 -> `ssh -N -L ...` PID 857374.
- **Known limitation** (documented, not hidden): does not survive a host
  reboot (no systemd unit = no boot-time re-launch). `autossh` was checked
  and is not installed; `tmux`/`screen`: tmux present, screen absent — not
  used, since the plain loop+setsid already gives auto-reconnect without
  an extra terminal-multiplexer dependency.

Forwarded socket: `/home/stack/.charon/coordinator-charon.sock` ->
`rocinante:/run/charon-bridge/charon.sock`. Confirmed present
(`srw-------`) and live.

## `~/.charon/bridge-hosts.env` (gitignored, outside any repo — confirmed
`/home/stack/.charon` is not inside any git work tree)

```
COORDINATOR_HOST=rocinante
COORDINATOR_HOST_IP=10.0.1.51

BRIDGE_REPO=charon
BRIDGE_SOCKET_CHARON=/home/stack/.charon/coordinator-charon.sock
```
Mode 0600. `COORDINATOR_HOST`/`_IP` are documentation only — proxy.py's
`_load_hosts_env()` only ever reads `BRIDGE_REPO` (fallback) and
`BRIDGE_SOCKET_<REPO_UPPER>`/`BRIDGE_SOCKET` (generic fallback), confirmed
by reading `_resolve_socket_path()`. `BRIDGE_SOCKET_MEDIASTACK`
deliberately omitted — no mediastack tunnel this stage.

## Config change — `~/.config/opencode/opencode.json`

Backed up first: `opencode.json.bak-20260707-063... -pre7c` (sibling of the
existing `.bak-*` files already in that dir). Edited `mcp.session-bridge.env`
only (lines ~623-626):

| Key | Before | After |
|---|---|---|
| `SESSION_BRIDGE_TTL` | `600` | unchanged |
| `BRIDGE_SOCKET` | `/home/stack/.charon/bridge.sock` | `""` (empty — proxy.py's `explicit = os.environ.get("BRIDGE_SOCKET")` treats `""` as falsy, so it falls through to `BRIDGE_HOST`/hosts-env resolution instead of hard-pinning local) |
| `BRIDGE_HOST` | `""` | `rocinante` |
| `BRIDGE_REPO` | `charon` | unchanged |

Effect: next opencode start for this config resolves the charon MCP socket
via `bridge-hosts.env`'s `BRIDGE_SOCKET_CHARON` -> the tunnel -> Roci. JSON
validated (`python3 -m json.load`) after edit. **Not** restarted; current
opencode process (and session `yoda`'s live MCP connection through the old
in-process env) is unaffected — env changes only take effect on next
process start, confirmed against proxy.py's `_resolve_socket_path()` being
read once at import time.

## Cross-host verify transcript (standalone python AF_UNIX client, local
forwarded socket only — no MCP tools touched)

```
SESSION_ID=deploy-test-7c-1783431288

initialize -> {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "session-bridge-daemon", "version": "2.0.0"}, "capabilities": {"tools": {}}}}

register -> {"jsonrpc": "2.0", "id": 2, "result": {"content": [{"type": "text", "text":
  "{\"ok\": true, \"session_id\": \"deploy-test-7c-1783431288\", \"lease_token\": \"fd3122c7...\",
    \"board\": {\"sessions\": [{... \"repo\": \"charon\", \"status\": \"in-progress\", \"count\":1 ...}]}}"}]}}
```

Independent confirmation on Roci itself (direct `ssh rocinante`, bypassing
the tunnel entirely) while the test session was still registered:
```
$ ssh rocinante "python3 -c \"import sqlite3; c=sqlite3.connect('/var/lib/charon-bridge/charon.db'); \
    print(c.execute('SELECT session_id, name, repo, status FROM sessions').fetchall())\""
[('deploy-test-7c-1783431288', 'deploy-test-7c', 'charon', 'in-progress')]
```
Proves the register call that went through the local socket -> SSH forward
actually landed in Roci's coordinator DB, not some local artifact.

```
board (via tunnel) -> ... "sessions": [{"session_id": "deploy-test-7c-1783431288", ...}], "count": 1 ...
unregister -> {"ok": true, "session_id": "deploy-test-7c-1783431288"}
board after unregister -> {"ok": true, "board": {"sessions": [], "count": 0, "by_repo": {}}}
```
Post-cleanup, direct Roci DB query: `[]` (empty — test session fully
removed on the coordinator, not just hidden from the local view).

## Safety verification, before/after

- `~/.charon/bridge.sock` (live local bridge, session `yoda`): same PIDs
  666424/668312, same mtime (Jul 5 15:48), before and after — never
  stopped, restarted, or connected to by the verify script.
- opencode process: not restarted.
- Roci: no new TCP listeners opened (tunnel is `-L` local-socket-to-
  remote-socket via the existing SSH session, same as 7-B's `ss -lx`
  finding — no port exposed).
- Scratch verify script (`~/.charon/scratch-verify-7c.py`) deleted after
  use; test session cleaned from both local view and Roci's DB.

## Outstanding for a later stage
- No systemd unit -> tunnel does not survive a reboot of this box. If
  durable-across-reboot is later required, the operator (not a Claude Code
  session, per the `systemctl` deny-list) would need to install a
  `systemctl --user` unit manually, or the deny-list would need a
  deliberate, human-approved carve-out — not done here.
- mediastack tunnel/socket/hosts-env entry not created this stage — only
  charon was in scope.
