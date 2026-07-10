# session-bridge `model` field — build + deploy report

**Scope:** add an optional `model` field to session-bridge sessions (closes
the #14/#15 gap — lets availability/board tooling differentiate live
sessions by which model they run). Rig-level only, no product touch, no
commit/push (this directory — `~/.config/opencode/session-bridge/` — is not
a git repo; nothing to commit there). Local live bridge daemon (session
`yoda`, `~/.charon/bridge.sock`) was **not** restarted or touched beyond the
on-disk source edit.

## Grounding read (before acting)
- `~/.config/opencode/session-bridge/daemon.py` — register/board/claim
  handlers, the NB1 `_PEER_VISIBLE_COLUMNS` allowlist chokepoint in
  `_row_to_dict`, the lease model from the durable-bridge Phase 0-1 rework.
- `~/.config/opencode/session-bridge/proxy.py` — thin forwarder; answers
  `tools/list` locally (must mirror daemon.py's tool schemas), forwards
  `tools/call` arguments opaquely (no field-level logic — confirmed by
  reading `_forward()`).
- `~/.config/opencode/session-bridge/SESSION.md` — doctrine doc.
- `roci-7b-report.md` / `roci-7c-report.md` — Roci coordinator layout:
  systemd units `charon-bridge-charon.service` /
  `charon-bridge-mediastack.service`, code at `/opt/charon-bridge/daemon.py`,
  DBs at `/var/lib/charon-bridge/{charon,mediastack}.db`, sockets at
  `/run/charon-bridge/{charon,mediastack}.sock`; tunnel forwards Roci's
  `charon.sock` to local `~/.charon/coordinator-charon.sock` (persistent
  wrapper script, PID 859953/859956, still running throughout).

## Code changes (local source, `~/.config/opencode/session-bridge/`)

### `daemon.py`
1. Schema: added `model TEXT DEFAULT ''` column to `sessions`; added
   `"model"` to the `_migrate()` ALTER-TABLE column list (existing DBs
   auto-gain the column on next `_db()` call — confirmed on Roci below).
2. `_PEER_VISIBLE_COLUMNS`: added `"model"` — routes through the **same**
   allowlist chokepoint as every other peer-visible field (not a bespoke
   bypass; confirmed via a new test asserting `"model" in
   daemon._PEER_VISIBLE_COLUMNS` and a full round-trip through
   `_row_to_dict`). No `status` RPC exists yet in this build (explicitly
   deferred per the module docstring — Phase 2/3), so there was nothing
   else to wire.
3. `_row_to_dict`: `d["model"] = d.get("model") or ""` for None-safety,
   matching the `repo`/`branch`/`busy` pattern already there.
4. `register` tool `inputSchema`: added optional `model` string property.
   Not in `required` — additive, existing callers unaffected.
5. `register` dispatch: `INSERT OR REPLACE` now includes `model` column,
   value `params.get("model", "")`.
6. **`claim` dispatch (correctness fix caught while implementing):** `claim`
   does its own full `INSERT OR REPLACE` of the session row (to flip
   `ticket`/`status`). Without carrying `model` forward the same way
   `name`/`repo` already are, claiming a ticket would silently wipe a
   session's previously-registered `model`. Fixed by fetching `model`
   alongside `name`/`repo` in the pre-claim `SELECT` and re-inserting it.
   Covered by `test_model_preserved_across_claim`.
7. Updated the module docstring's Phase 0-1 scope bullet list with a short
   note on the additive `model` field.

### `proxy.py`
- Added the matching `model` property to the local `register` tool schema
  (proxy.py answers `tools/list` locally, so it must stay in sync with the
  daemon's tool list — per the existing comment about `ack`).
- No forwarding-logic change needed: `_forward()` passes `tools/call`
  argument JSON through opaquely; proxy.py never inspects tool arguments,
  only tool *names* (for the local `initialize`/`tools/list` short-circuit).
  Confirmed by reading `_forward()`/`main()` before concluding this.
- Added a docstring note recording the additive schema change.

### `SESSION.md`
- `register` bullet now documents `model` (optional, self-reported, e.g.
  `claude-sonnet-5`, `gpt-5`) so the board/availability tooling can
  differentiate live sessions by model — same self-report pattern as
  opencode.db/ANNOUNCE's model self-report — and notes omitting it is fine.

### Tests (`test_daemon.py`, rig-only test file)
Added 4 tests, all passing alongside the existing 15 (19/19 total,
`python3 -m pytest test_daemon.py -q` → `19 passed in 0.52s`):
- `test_model_stored_and_exposed_via_board`
- `test_model_omitted_is_backward_compatible`
- `test_model_exposed_through_allowlist_chokepoint`
- `test_model_preserved_across_claim`

## Roci deploy

1. **Backup** (before touching the live file):
   ```
   ssh rocinante "cp /opt/charon-bridge/daemon.py /opt/charon-bridge/daemon.py.bak-20260707-173727-pre-model-field"
   ```
   sha256 of the backup: `e022db9c...c117a7` — matches the pre-change source
   exactly (same hash recorded in `roci-7b-report.md`).
2. **Copy**: `scp daemon.py rocinante:/tmp/daemon.py.new`, verified local vs.
   remote sha256 identical (`41039b88...c231f44`) before install.
3. **Install**: `sudo cp /tmp/daemon.py.new /opt/charon-bridge/daemon.py`,
   `chown stack:stack`, re-verified sha256 in place, removed the `/tmp`
   staging copy.
4. **Restart** (safe — no live sessions on Roci yet, per brief):
   ```
   ssh rocinante "sudo systemctl restart charon-bridge-charon.service charon-bridge-mediastack.service"
   ```
   Both came back `active` with fresh PIDs (1242203 / 1242207,
   `ActiveEnterTimestamp` 2026-07-08 00:37:40 UTC). Restart used `ssh
   rocinante sudo systemctl ...` — a remote command, not a local
   `Bash(systemctl *)` invocation (that pattern is denied in this repo's
   `.claude/settings.local.json` deliberately, for the *local* host only;
   confirmed `sudo -n true` works passwordlessly on Roci for user `stack`).

## Smoke test — via tunnel (`~/.charon/coordinator-charon.sock`)

Standalone AF_UNIX Python client, no MCP tools touched
(`/tmp/claude-.../scratchpad/smoke_model_field.py`, not left on either
host).

```
=== smoke test (via tunnel): /home/stack/.charon/coordinator-charon.sock ===
initialize -> {'protocolVersion': '2024-11-05', 'serverInfo': {'name': 'session-bridge-daemon', 'version': '2.0.0'}, ...}

--- WITH model (session=smoke-model-1783471081) ---
register -> {"ok": true, ..., "board": {"sessions": [{..., "model": "test-model", ...}], "count": 1, ...}}
board() row.model -> 'test-model'
PASS: model shown via tunnel board()

--- WITHOUT model / back-compat (session=smoke-nomodel-1783471081) ---
register (no model) -> {"ok": true, ...}
board() row.model (omitted) -> ''
PASS: omitting model is backward compatible (defaults to '')

--- cleanup ---
unregister a -> {"ok": true, "session_id": "smoke-model-1783471081"}
unregister b -> {"ok": true, "session_id": "smoke-nomodel-1783471081"}
PASS: both sessions removed post-unregister

=== ALL TUNNEL CHECKS PASSED ===
```

## Smoke test — direct on Roci (bypassing tunnel entirely)

```
DIRECT ON ROCI (bypassing tunnel), socket= /run/charon-bridge/charon.sock
register -> {"ok": true, ..., "model": "test-model-direct", ...}
board().model -> 'test-model-direct'
unregister -> {"ok": true, "session_id": "direct-roci-model-1783471090"}
DIRECT-ON-ROCI CHECKS PASSED
```

Post-cleanup DB check on Roci:
```
columns: [..., 'lease_token', 'lease_expires_at', 'model']
rows: []
```
Confirms the `model` column exists in the live coordinator schema (added by
`_migrate()` on first `_db()` call after restart) and all test sessions
(tunnel + direct) were fully cleaned up — coordinator DB is empty.

## Safety verification

- Local live bridge (`~/.charon/bridge.sock`, session `yoda`, PIDs
  666424/668312): same PIDs and mtime (`Jul 5 15:48`) before and after —
  never stopped, restarted, or connected to. Only the on-disk `daemon.py`/
  `proxy.py` source was edited; the running process holds its old
  in-memory code until its own next restart (staged cutover, as instructed).
- Roci restart only touched `charon-bridge-charon.service` and
  `charon-bridge-mediastack.service` — both confirmed `active` with fresh
  PIDs post-restart, no other services touched.
- No product-repo file touched; no commit/push performed anywhere.

## Proposed commit (for the manager to apply/review — not committed here)

The `~/.config/opencode/session-bridge/` directory is not a git repo, so
there is nothing to commit there directly. If this rig doctrine is meant to
be tracked, the proposed commit message for wherever it lands would be:

```
feat(session-bridge): add optional model field to sessions

Sessions can now self-report which model they run at register() time
(model="claude-sonnet-5" etc.), closing the #14/#15 gap for live
assignment differentiation. Additive-only: existing callers that omit
model are unaffected (defaults to ""). Exposed via board() through the
same _PEER_VISIBLE_COLUMNS allowlist chokepoint as every other
peer-visible field (no bespoke bypass). Preserved across claim()'s
full-row INSERT OR REPLACE, which previously would have silently wiped
it. SESSION.md doctrine updated so sessions self-report model the same
way the benchmark harness self-reports via opencode.db/ANNOUNCE.

Deployed to the Roci coordinator (backup taken first); local live
bridge (session yoda) untouched — takes effect there on its own next
restart.
```

## Files changed
- `~/.config/opencode/session-bridge/daemon.py`
- `~/.config/opencode/session-bridge/proxy.py`
- `~/.config/opencode/session-bridge/SESSION.md`
- `~/.config/opencode/session-bridge/test_daemon.py` (+4 tests, 19/19 pass)
- Roci: `/opt/charon-bridge/daemon.py` (deployed; backup at
  `/opt/charon-bridge/daemon.py.bak-20260707-173727-pre-model-field`)
