# Stage 7-B report — Roci coordinator daemon install

**Scope:** install-only. No SSH tunnel, no cutover of the local bridge
(`~/.charon/bridge.sock`, session `yoda` — untouched throughout). No network
port opened — verified `ss -lx`/`ss -ltn` on Roci at the end: both listeners
are `AF_UNIX` (`u_str LISTEN`), zero new TCP listeners.

## Grounding (read before acting)
- `DURABLE-BRIDGE-DESIGN-v3.md` — Phase 0/1 scope (lease model, NB1 redaction
  allowlist, NB2 persisted seq, per-repo DB/socket isolation). Phase 2 (push
  watcher/renewer) and Phase 3 (status RPC/kill-switch) are NOT part of the
  daemon shipped here — matches what's actually in `daemon.py` today.
- `bridge-phase01-report.md` — confirms Phase 0-1 code (this exact
  `daemon.py`) was built/tested but never deployed; live bridge
  (`~/.charon/bridge.sock`, PIDs 666424/668312, session `yoda`) was verified
  untouched at the end of that session.
- `~/.config/opencode/session-bridge/daemon.py` (source of truth, read in
  full before deploying) — **env contract, confirmed from code, not assumed:**
  - `BRIDGE_SOCKET` (daemon.py:40) — Unix socket path. Default
    `/tmp/charon-bridge.sock` if unset.
  - `BRIDGE_DB` (daemon.py:41) — SQLite DB path, `os.path.expanduser`'d.
    Default `~/.charon/session-bridge.db` if unset.
  - `SESSION_BRIDGE_TTL` (daemon.py:42) — poll-mode lease TTL seconds,
    default 600. Left at default (not set) on Roci.
  - `BRIDGE_REDELIVER_WINDOW_S`, `BRIDGE_NUDGE_TTL_S`, `BRIDGE_MAX_QUEUE_LEN`,
    `BRIDGE_MAX_QUEUE_BYTES` — G1 delivery tunables, all left at defaults
    (not set) on Roci.
  - **Correction to the brief:** `daemon.py` itself does **not** read
    `BRIDGE_REPO`. That env var is read by `proxy.py` (client-side only, for
    cross-host socket resolution against `bridge-hosts.env` — Phase 1
    client-side code, not deployed this stage). The daemon's per-repo
    isolation is achieved entirely by giving each daemon instance its own
    `BRIDGE_SOCKET`/`BRIDGE_DB`; `repo` is a client-supplied field stored per
    session row, used only for `board()` filtering. `BRIDGE_REPO=<repo>` is
    still set in both units (harmless — daemon.py never reads it) per the
    brief's instruction, and documents intent for whoever wires the client
    side in 7-C.
  - **Imports:** stdlib only (`calendar, json, os, secrets, selectors, signal,
    socket, sqlite3, struct, sys, time, typing`) — confirmed by reading the
    import block. No sibling modules (`idempotency.py`, `proxy.py`,
    `server.py`) are imported by `daemon.py`. Only `daemon.py` was copied to
    Roci; `proxy.py` is explicitly client-side (per the brief) and
    `idempotency.py` is unwired Phase-2 scaffold — neither belongs on the
    coordinator.

## Deployed artifacts on Roci (`rocinante`)

| Item | Path |
|---|---|
| Daemon code | `/opt/charon-bridge/daemon.py` (owned `stack:stack`; sha256 `e022db9c...c117a7`, verified byte-identical to local source) |
| Runtime dir (sockets) | `/run/charon-bridge/` — created via systemd `RuntimeDirectory=charon-bridge` (mode 0700, `RuntimeDirectoryPreserve=yes` so it survives daemon restarts, recreated on boot) |
| charon socket | `/run/charon-bridge/charon.sock` — `srw-------` (0600), owner `stack` |
| mediastack socket | `/run/charon-bridge/mediastack.sock` — `srw-------` (0600), owner `stack` |
| DB dir | `/var/lib/charon-bridge/` (owned `stack:stack`, mode 0755 on the dir; DB files themselves `-rw-------` 0600) |
| charon DB | `/var/lib/charon-bridge/charon.db` (+ `-shm`/`-wal`, WAL mode) |
| mediastack DB | `/var/lib/charon-bridge/mediastack.db` (+ `-shm`/`-wal`, WAL mode) |
| Unit (charon) | `/etc/systemd/system/charon-bridge-charon.service` — `enabled`, `active` |
| Unit (mediastack) | `/etc/systemd/system/charon-bridge-mediastack.service` — `enabled`, `active` |

## Unit contents (both, final working version)

First attempt used `ExecStartPre=/usr/bin/install -d ... /run/charon-bridge`
combined with `ProtectSystem=strict` + `ReadWritePaths=/run/charon-bridge` —
**failed** (`226/NAMESPACE`): `ReadWritePaths` requires the path to exist
*before* systemd builds the mount namespace, but `ExecStartPre` runs *inside*
that already-namespaced process — chicken-and-egg. Fixed by switching to
systemd's built-in `RuntimeDirectory=`, which systemd creates pre-namespace
for exactly this case; dropped `/run/charon-bridge` from `ReadWritePaths`
(no longer needed — `RuntimeDirectory` grants it implicitly).

`charon-bridge-charon.service`:
```ini
[Unit]
Description=Charon session-bridge coordinator daemon (repo: charon)
After=network.target

[Service]
Type=simple
User=stack
Group=stack
RuntimeDirectory=charon-bridge
RuntimeDirectoryMode=0700
RuntimeDirectoryPreserve=yes
ExecStart=/usr/bin/python3 /opt/charon-bridge/daemon.py
Environment=BRIDGE_SOCKET=/run/charon-bridge/charon.sock
Environment=BRIDGE_DB=/var/lib/charon-bridge/charon.db
Environment=BRIDGE_REPO=charon
Restart=always
RestartSec=2
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/charon-bridge
UMask=0077

[Install]
WantedBy=multi-user.target
```

`charon-bridge-mediastack.service` — identical except:
```ini
Description=Charon session-bridge coordinator daemon (repo: mediastack)
Environment=BRIDGE_SOCKET=/run/charon-bridge/mediastack.sock
Environment=BRIDGE_DB=/var/lib/charon-bridge/mediastack.db
Environment=BRIDGE_REPO=mediastack
```

Both units share `RuntimeDirectory=charon-bridge` (same name, same
owner/group `stack:stack`) — systemd reference-counts this safely across the
two units; confirmed both sockets coexist in the one directory with correct
independent 0600 perms.

## Verification

```
$ systemctl is-enabled charon-bridge-charon.service charon-bridge-mediastack.service
enabled
enabled
$ systemctl is-active charon-bridge-charon.service charon-bridge-mediastack.service
active
active
$ ls -la /run/charon-bridge/
srw------- 1 stack stack 0 ... charon.sock
srw------- 1 stack stack 0 ... mediastack.sock
$ ss -lx | grep charon
u_str LISTEN 0 16 /run/charon-bridge/charon.sock ...
u_str LISTEN 0 16 /run/charon-bridge/mediastack.sock ...
```
No TCP listeners added (`ss -ltn` count unchanged before/after) — confirms
no network port was opened, sockets are local-only as required.

## Protocol smoke test (real AF_UNIX client, run ON Roci)

Script: `/tmp/smoke_test.py` on Roci (transient scratch file, not left
installed as product infra). For each socket: `initialize` -> `tools/list`
-> `register` (repo-scoped) -> assert `lease_token` present at top level and
absent from the embedded `board` sub-object and from the full response JSON
-> `board()` -> assert `lease_token` absent from the full `board()` response
JSON (both key and the actual token value, substring-checked) and that the
registered session IS visible -> `unregister` -> `board()` again -> assert
session is gone.

### charon.sock transcript (abridged, full JSON echoed during run)
```
=== smoke test: /run/charon-bridge/charon.sock repo=charon session=smoke-charon-1783430884 ===
initialize -> {"protocolVersion": "2024-11-05", "serverInfo": {"name": "session-bridge-daemon", "version": "2.0.0"}, ...}
tools/list -> ['ack', 'board', 'claim', 'nudge', 'register', 'release', 'unregister', 'update']
register -> {"ok": true, "session_id": "smoke-charon-1783430884", "lease_token": "de584deaefa3aab8a7de50615e63b8a1", "board": {...no lease_token key...}}
LEASE PRESENT: lease_token=de584dea... (len=32)
TOKEN REDACTED in register's embedded board: confirmed absent
board -> {"ok": true, "board": {"sessions": [{... full row, no lease_token key ...}], "count": 1, "by_repo": {"charon": 1}}}
TOKEN REDACTED in board(): confirmed absent; session visible on board
unregister -> {"ok": true, "session_id": "smoke-charon-1783430884"}
post-unregister board: session correctly absent
=== ALL CHECKS PASSED for /run/charon-bridge/charon.sock ===
```

### mediastack.sock transcript (abridged)
```
=== smoke test: /run/charon-bridge/mediastack.sock repo=mediastack session=smoke-mediastack-1783430888 ===
initialize -> {"protocolVersion": "2024-11-05", "serverInfo": {"name": "session-bridge-daemon", "version": "2.0.0"}, ...}
tools/list -> ['ack', 'board', 'claim', 'nudge', 'register', 'release', 'unregister', 'update']
register -> {"ok": true, "session_id": "smoke-mediastack-1783430888", "lease_token": "ec16039e21586787cbd1abb0652ae11f", "board": {...no lease_token key...}}
LEASE PRESENT: lease_token=ec16039e... (len=32)
TOKEN REDACTED in register's embedded board: confirmed absent
board -> {"ok": true, "board": {"sessions": [{... full row, no lease_token key ...}], "count": 1, "by_repo": {"mediastack": 1}}}
TOKEN REDACTED in board(): confirmed absent; session visible on board
unregister -> {"ok": true, "session_id": "smoke-mediastack-1783430888"}
post-unregister board: session correctly absent
=== ALL CHECKS PASSED for /run/charon-bridge/mediastack.sock ===
```

### Per-repo DB isolation, confirmed post-test
```python
>>> sqlite3.connect("/var/lib/charon-bridge/charon.db").execute(
...     "SELECT session_id, repo FROM sessions").fetchall()
[]
>>> sqlite3.connect("/var/lib/charon-bridge/mediastack.db").execute(
...     "SELECT session_id, repo FROM sessions").fetchall()
[]
```
Both empty (test sessions correctly unregistered), and — more importantly —
two distinct files on disk the whole time: the `charon` daemon's `board()`
never listed the `mediastack` test session or vice versa (each transcript
above shows `count: 1`, only its own session), proving real per-repo
isolation at the daemon-instance level, not just theoretical from separate
env vars.

## For Stage 7-C (tunnel + cutover) — exact values to wire

| | charon | mediastack |
|---|---|---|
| Socket (on Roci) | `/run/charon-bridge/charon.sock` | `/run/charon-bridge/mediastack.sock` |
| DB (on Roci) | `/var/lib/charon-bridge/charon.db` | `/var/lib/charon-bridge/mediastack.db` |
| systemd unit | `charon-bridge-charon.service` | `charon-bridge-mediastack.service` |
| `BRIDGE_REPO` set to | `charon` | `mediastack` |
| Owner/perms | `stack:stack`, socket 0600 | `stack:stack`, socket 0600 |

Both `enabled` (survive reboot) and `active` (`Restart=always`, `RestartSec=2`
— not yet load-tested for the NB3 push-mode renewal gap, since Phase 2 isn't
deployed; poll-mode-only TTL behavior applies, matching what's actually
running). No SSH tunnel exists yet — these sockets are reachable only by a
process running locally on Roci. Stage 7-C's job: forward each socket over
SSH to the relevant client host(s) and only then repoint `proxy.py`
(`BRIDGE_HOST`/`BRIDGE_SOCKET_<REPO>` in `~/.charon/bridge-hosts.env`) — not
done here, not touched here.

## What was explicitly NOT done (per brief)
- No SSH tunnel unit (`charon-bridge-tunnel-*`) — Stage 7-C.
- No cutover of `proxy.py`/`bridge-hosts.env`/`opencode.json` on any client
  host — Stage 7-C.
- Local bridge (`~/.charon/bridge.sock`, session `yoda`) not touched —
  not even read.
- `idempotency.py`, `proxy.py`, `server.py` not copied to Roci — daemon.py
  doesn't import them, and per the brief `proxy.py` is client-side only.
- No network port opened — verified via `ss`.
