# Bridge & Names Audit — read-only investigation

Date: 2026-07-06
Scope: (1) session-bridge architecture / locality, (2) Jedi/Droid name pool + Grand Master leak, (3) BB-8 session.

---

## INVESTIGATION 1 — Session-bridge architecture

### Where it lives / how it's wired
- Implementation dir: `/home/stack/.config/opencode/session-bridge/`
  - `server.py` — legacy per-session MCP server (stdio JSON-RPC, self-contained SQLite). Not the active path.
  - `daemon.py` — the **active** single standalone daemon; Unix-socket listener + shared SQLite.
  - `proxy.py` — thin per-session forwarder; each opencode session runs this and forwards JSON-RPC to the daemon over the Unix socket.
- MCP registration: `/home/stack/.config/opencode/opencode.json` lines ~614–627:
  ```
  "mcp": { "session-bridge": {
      "type": "local",
      "command": ["python3", "/home/stack/.config/opencode/session-bridge/proxy.py"],
      "enabled": true,
      "env": { "SESSION_BRIDGE_TTL": "600",
               "BRIDGE_SOCKET": "/home/stack/.charon/bridge.sock" } } }
  ```
  Note `"type": "local"` and the socket env override.

### State storage (all on THIS machine's local filesystem)
- Transport socket: `BRIDGE_SOCKET` = `/home/stack/.charon/bridge.sock`
  - `daemon.py:513` `socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)` → **Unix domain socket**, `os.chmod(SOCK_PATH, 0o600)` (daemon.py:515).
  - Confirmed on disk: `srw------- stack stack /home/stack/.charon/bridge.sock` (an `s`ocket file, owner-only).
- Shared DB: `DB_PATH` = `~/.charon/session-bridge.db` (daemon.py:24, server.py:23). SQLite WAL. On disk with `-wal`/`-shm` sidecars, mode `0600`.
- `daemon.py` default socket if env unset is `/tmp/charon-bridge.sock` (daemon.py:23), but the live config overrides it to `~/.charon/bridge.sock`.

### Running processes (confirmed live)
- `daemon.py` running (PIDs 666424, 668312 — two instances present; possibly one stale/re-exec), plus 3 `proxy.py` forwarders (attached sessions).

### Local-only vs networked — VERDICT: **local-to-this-machine ONLY**
- The only listener is an `AF_UNIX` socket. Grep for `AF_INET`/`socket.bind`/`0.0.0.0`/`SO_REUSEADDR`/`tcp`/`host=` across the bridge dir returns **nothing** — there is no TCP port, no network bind, nothing points at a remote host.
- Access is gated by the local filesystem: only processes on this host that can open `/home/stack/.charon/bridge.sock` (owner `stack`, mode 0600) can talk to the daemon. All persistence is a local SQLite file.

### Can a session on BB-8 (10.0.1.61) register on THIS machine's bridge?
- **No — not with the current design.** A Unix-domain socket is not reachable over the network. A process on a different physical host has no path to `/home/stack/.charon/bridge.sock` unless that exact socket (and the SQLite DB) were exported over a shared filesystem (e.g. NFS) — which is **not** configured anywhere in opencode.json or the fleet rig.
- Mechanism concretely: `proxy.py` (`SOCKET_PATH = env BRIDGE_SOCKET`) does `socket(AF_UNIX).connect(SOCKET_PATH)` (proxy.py:182–185). AF_UNIX resolves a local filesystem path only; there is no host/IP field. So a remote session would fail to connect and fall back to proxy.py's "Bridge daemon not running" error (proxy.py:239–241).
- Consequence: a session on the BB-8 box would register on **its own local bridge** (a separate DB on that host, if it runs one) and would **not** appear on this machine's `board()`. The two boards are fully disjoint. There is currently **no** shared/networked bridge and **no** config pointing either host at the other.

### Reaching / querying BB-8's own bridge
- Nothing in this repo/config references BB-8's host or any remote bridge endpoint. There is **no** IP `10.0.1.61` anywhere in `/home/stack/charon-private`, `/home/stack/code/charon`, or the opencode config (grep = 0 hits). If BB-8 runs its own daemon it would be at that host's local `~/.charon/bridge.sock` — not queryable from here without SSH + a local client on that box. (Did not connect.)

---

## INVESTIGATION 2 — Jedi / Droid name pool

### Key finding: the pool is a CONVENTION, not a hardcoded array
- There is **no** names array/list file in the fleet rig or launcher scripts. `fleet-droid.sh` derives its handle from the tier + PID (`DROID="$TIER-$$"`, fleet-droid.sh:35), not from a Jedi list. `summary.sh`/`handoff.sh`/`BOOTSTRAP.md` only instruct a human/session to "pick an unused Jedi name" from the board.
- The single authoritative definition is the opencode instructions file:
  **`/home/stack/.config/opencode/session-bridge/SESSION.md`, section "Session naming — Star Wars convention" (lines 50–64).**

### The pool table (SESSION.md lines 56–59)
- Line 57 header; the rule is "**Any canonical Star Wars Jedi**" (charon) / "**Any canonical Star Wars droid**" (mediastack) — open-ended, with an EXAMPLE list.
- **Charon Jedi example pool — SESSION.md line 58:**
  `yoda`, `obi-wan-kenobi`, `ahsoka-tano`, `cal-kestis`, `revan`, `qui-gon-jinn`, `mace-windu`, `luke-skywalker`, `rey-skywalker`
- Mediastack droid example pool — SESSION.md line 59:
  `bb-8`, `r2-d2`, `c-3po`, `hk-47`, `k-2so`, `chopper`, `bd-1`, `ig-88`, `l3-37`, `gonk`

### GRAND MASTER leak — FLAGGED (must be reserved for manager sessions)
Grand Masters searched: Yoda, Luke Skywalker (Luke), Satele Shan.
- **`yoda`** — PRESENT in the regular Charon example pool. **File `/home/stack/.config/opencode/session-bridge/SESSION.md`, line 58** (first entry). → remove/reserve.
- **`luke-skywalker`** — PRESENT in the regular Charon example pool. **Same file, line 58** (8th entry). → remove/reserve.
- **Satele Shan** — NOT present in the pool (no `satele`/`shan` anywhere in the config or fleet rig). Nothing to remove.

Precise removal target for a later edit: SESSION.md line 58, drop the `yoda` and `luke-skywalker` tokens from the pipe-delimited example list (leave `obi-wan-kenobi`, `ahsoka-tano`, `cal-kestis`, `revan`, `qui-gon-jinn`, `mace-windu`, `rey-skywalker`). Optionally add a "Reserved for manager" note naming Yoda / Luke Skywalker / Satele Shan.

Caveat: because the pool is defined as "**any** canonical Jedi" (open-ended), removing the two example tokens is necessary but not sufficient by itself — a hard reserve would need an explicit "these names are manager-only, never self-assign" line. That is a design decision for the manager, flagged here.

Historical usage note (not the pool def, just evidence Yoda has been used as a regular/handoff session): `SESSION-HANDOFF-yoda.md`, `SESSION-HANDOFF-yoda-prev.md` exist in the fleet dir.

---

## INVESTIGATION 3 — BB-8 session

- "BB-8" is defined **only** as a mediastack (SLOP) **droid session-name example**, in `/home/stack/.config/opencode/session-bridge/SESSION.md` line 59 (`bb-8`, first entry of the droid pool). It is a session label, not a machine definition.
- There is **no** launcher/config anywhere that defines a "BB-8" host, machine, or a bridge pointed at 10.0.1.61. `fleet-droid.sh` and the SLOP/mediastack launchers do not hardcode `bb-8`; sessions self-pick droid names per the SESSION.md convention.
- Which bridge a `bb-8` session registers with: the **same local bridge** as any other session on the host it runs on — via `proxy.py` → local `~/.charon/bridge.sock`, registering with `repo="mediastack"`. There is no separate/remote bridge for it.
- Only other mention: `/home/stack/charon-private/prompts/bridge-harden.md` line 21 — "blocking during a subagent call is the #1 cause of false reaps (killed bb-8 twice)" — i.e. a `bb-8` **session** was false-reaped for missed heartbeats; still not a machine reference.
- Reconciliation with the task's premise ("BB-8 = box at 10.0.1.61"): that mapping is the operator's mental model; it is **not** represented in any repo/fleet/config artifact. As the code stands, a session on that box could not appear on this machine's board (see Investigation 1).

---

## File/line index (for precise later edits)
- Bridge daemon (Unix socket, DB): `/home/stack/.config/opencode/session-bridge/daemon.py` — socket AF_UNIX line 513, chmod 515, SOCK_PATH line 23, DB_PATH line 24.
- Bridge proxy (per-session forwarder): `/home/stack/.config/opencode/session-bridge/proxy.py` — SOCKET_PATH line 18, connect lines 182–185.
- MCP wiring + socket env override: `/home/stack/.config/opencode/opencode.json` lines ~614–627.
- Name pool convention (Jedi + droid) and Grand Master leak: `/home/stack/.config/opencode/session-bridge/SESSION.md` lines 50–64; Grand Masters `yoda` + `luke-skywalker` on **line 58**.
- BB-8 as droid example: SESSION.md line 59; historical false-reap note prompts/bridge-harden.md line 21.
- No occurrence of `10.0.1.61` in any repo/config (grep = 0).
