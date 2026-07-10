# Roci coordinator tunnel — self-healing (Stage 7-D follow-up)

**Scope:** make the Stage 7-C SSH tunnel (`~/.charon/coordinator-tunnel.sh`)
recover automatically after a shell restart / laptop sleep / reboot, without
using `systemctl --user` (deny-listed on this box, deliberate guard, not
worked around).

## Why the existing loop wasn't enough

`coordinator-tunnel.sh` is a `while true; ssh -N -L ...; sleep 5; done` loop
that reconnects across *connection drops* fine, but it has no supervisor:
if the shell/session that launched it dies (WSL shell restart, laptop
sleep killing the detached process tree, reboot), the loop itself is gone
and nothing relaunches it. `BRIDGE_HOST=rocinante` in `opencode.json` then
silently fails MCP `session-bridge` calls until a human notices and
manually reruns the launcher.

## What was added

### 1. `~/.charon/ensure-coordinator-tunnel.sh` (new, `chmod 755`)

Idempotent "supervisor-lite." Logic:

1. `is_loop_running()` — `pgrep -f "^bash /home/stack/.charon/coordinator-tunnel.sh$"`
   (stable marker: the loop's exact argv, anchored so it can't self-match
   the ensure script or a pgrep invocation's own command line). If found,
   exit 0 immediately — no-op.
2. `is_socket_live()` — cheap liveness probe: `[ -S "$LOCAL_SOCK" ]` then a
   local `python3` `AF_UNIX` `connect()` with a 1.5s timeout, no data sent,
   immediately closed. Purely local IPC — not a network call, so it never
   hangs even if Roci is unreachable. If the socket is live (something is
   already forwarding, even if it's not the marker process for some
   reason), exit 0 — never stack a second tunnel on a working one.
3. Only if *neither* the loop nor a live socket is found: take a
   non-blocking `flock` on `~/.charon/.ensure-coordinator-tunnel.lock`
   (protects against two shells opened at once both winning the race),
   re-check `is_loop_running()` under the lock, then
   `setsid nohup bash coordinator-tunnel.sh >>coordinator-tunnel.stdout.log 2>&1 & disown`
   — same detach pattern the original Stage 7-C launch used.

Full command cost when healthy: one `pgrep` + one local socket connect,
both sub-second, no remote round-trip.

### 2. `~/.bashrc` block (appended, guarded, marked
`BEGIN/END charon coordinator tunnel auto-heal (roci-tunnel-persistence)`)

```bash
if [[ $- == *i* ]] && [ -x "${HOME}/.charon/ensure-coordinator-tunnel.sh" ]; then
    ( "${HOME}/.charon/ensure-coordinator-tunnel.sh" >/dev/null 2>&1 & disown ) 2>/dev/null
fi
```

Runs only for interactive shells, backgrounded + disowned so it can never
block or slow shell startup, output/errors fully suppressed here (real
logging goes to `~/.charon/coordinator-tunnel.log`).

### 3. `~/.profile` block (appended, same guard markers)

Debian's stock `~/.bashrc` has a top-of-file guard —
`case $- in *i*) ;; *) return;; esac` — that returns *before* reaching any
appended block for **non-interactive login shells** (e.g. `bash -lc '...'`,
which is exactly the form the brief's own test command uses). So a block
appended only to `.bashrc` would silently never fire for that case.
`~/.profile` has no such guard and is read for *any* login shell whether
interactive or not (confirmed: it already unconditionally sources
`~/.bashrc`), so the same guarded call was added there too, unconditional
on interactivity (login shell context is already the restriction):

```bash
if [ -x "${HOME}/.charon/ensure-coordinator-tunnel.sh" ]; then
    ( "${HOME}/.charon/ensure-coordinator-tunnel.sh" >/dev/null 2>&1 & disown ) 2>/dev/null
fi
```

Net effect: an interactive login shell fires both blocks (harmless — the
ensure script is idempotent, second call is a same-microsecond no-op); a
non-interactive login shell (`bash -lc ...`) fires only the `.profile`
one; a non-login non-interactive `bash script.sh` fires neither (correct —
we don't want random script invocations touching the tunnel).

**Not touched:** the pre-existing stale `CHARON_GATEWAY_TOKEN` export
elsewhere in the profile — separate known red, out of scope here, left
exactly as found.

## Test transcript

### (a) Tunnel already healthy — confirm no duplicate spawn

Direct call:
```
$ /home/stack/.charon/ensure-coordinator-tunnel.sh
loop pid before: 857371   ssh pid before: 857374
loop pid after:  857371   ssh pid after:  857374   (same PIDs, unchanged)
```

Via the actual shell-startup path (`bash -lc 'true'`, exercising the new
`.profile` block):
```
loop pid before: 857371   ssh pid before: 857374
bash -lc 'true'
loop pid after:  857371   ssh pid after:  857374
loop pid count after: 1   ssh pid count after: 1
```
No duplicate loop or ssh process either way.

### (b) Kill the tunnel, confirm auto-recovery on next shell

```
$ kill 857371 857374          # loop + ssh child
(no loop process)
(no ssh process)
$ time bash -lc 'true'
real  0m0.006s                # startup not slowed — recovery is backgrounded
$ # poll:
t+1s: loop_pid=[] ssh_pid=[]
t+2s: loop_pid=[859953] ssh_pid=[859956]   # recovered
```
Log confirms the ensure script detected and relaunched it:
```
[2026-07-07T06:42:05-07:00] ensure-coordinator-tunnel.sh: loop not running, socket dead -> relaunching
[2026-07-07T06:42:05-07:00] coordinator-tunnel.sh starting; local=/home/stack/.charon/coordinator-charon.sock remote=rocinante:/run/charon-bridge/charon.sock
[2026-07-07T06:42:05-07:00] launching ssh forward
```
Recovery landed within ~2 seconds of the triggering shell, well under
"a few seconds."

### (c) Standalone AF_UNIX client through the restored socket

Ran a scratch Python JSON-RPC client (deleted after use, same pattern as
the Stage 7-C verify) against the freshly-restored
`~/.charon/coordinator-charon.sock`:

```
initialize -> ok (session-bridge-daemon 2.0.0)
register   -> {"ok": true, "session_id": "tunnel-restore-test-1783431737", ...}
board      -> {"ok": true, "board": {"sessions": [{"session_id": "tunnel-restore-test-...", "repo": "charon", ...}], "count": 1}}
unregister -> {"ok": true, "session_id": "tunnel-restore-test-1783431737"}
```
Independent confirmation via direct `ssh rocinante` query against Roci's
own DB after unregister:
```
$ ssh rocinante "python3 -c \"... SELECT session_id... WHERE session_id LIKE 'tunnel-restore-test%' ...\""
[]
```
Empty — proves the round trip actually reached Roci's coordinator and the
test session was fully cleaned up there, not just locally.

### Final idempotency re-check + safety checks

- Re-ran `ensure-coordinator-tunnel.sh` once more against the now-healthy
  (recovered) tunnel: PIDs unchanged (859953 / 859956), loop count 1, ssh
  count 1 — still no duplicate.
- `~/.charon/bridge.sock` (unrelated local bridge daemon, session `yoda`):
  same mtime (`Jul 5 15:48`) before and after this entire exercise —
  confirmed untouched.
- Scratch verify script deleted after use.
- Left running healthy at end: loop PID 859953 -> ssh PID 859956, socket
  `~/.charon/coordinator-charon.sock` live.

## Files touched

- `/home/stack/.charon/ensure-coordinator-tunnel.sh` (new, 755)
- `/home/stack/.bashrc` (appended guarded block, marked
  `BEGIN/END charon coordinator tunnel auto-heal (roci-tunnel-persistence)`)
- `/home/stack/.profile` (appended guarded block, same markers)
- Neither `coordinator-tunnel.sh` itself, `opencode.json`, nor
  `bridge-hosts.env` from Stage 7-C were modified.

## Residual limitation (documented, not fixed — out of reach from inside a shell)

WSL2 itself does not auto-start on Windows boot by default, and even where
it does (`wsl --install` distros with boot-task registration), a shell
inside it isn't guaranteed to launch automatically. So the tunnel comes
back up on the **first shell opened after WSL starts** (interactive
terminal, or any `bash -l` invocation e.g. from opencode/VS Code Remote),
not at the instant the Windows host boots or wakes from sleep. This is
acceptable per the brief: the gap is bounded by "until the user next opens
a WSL shell," not indefinite, and closing it fully would require either a
Windows Scheduled Task / WSL boot-task hook (outside this box's Linux
`.claude` deny-list scope entirely — a Windows-side change) or the
`systemctl --user` unit this task was explicitly told not to pursue.
