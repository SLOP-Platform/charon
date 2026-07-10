# Durable session-bridge — Phase 0 + Phase 1 build report

**Scope:** Phase 0 + Phase 1 ONLY, per `DURABLE-BRIDGE-DESIGN-v3.md` (GO-WITH-CONDITIONS) and
`DURABLE-BRIDGE-REVIEW-v3.md`. Phase 2 (push watcher: `poll_wait`, `bridge-watch.sh`, the renewer
service, `SessionStart`/`Stop` hook wiring) and Phase 3 (`status` RPC, kill-switch, `bridge-status`
CLI, AGENTS.md heartbeat-retirement rewrite) are explicitly **not built**. No commit, no push, no
deploy, no SSH, no restart of the live daemon. The live bridge (`~/.charon/bridge.sock`, PIDs
666424/668312, session `yoda`) was verified still running the pre-existing in-memory code,
untouched, at the end of this session.

---

## Repo A — build-rig config dir (`~/.config/opencode/session-bridge/`, not a git repo)

Files changed:
- `daemon.py` — full rework (see below).
- `proxy.py` — Phase 0 shim + Phase 1 cross-host socket resolution + new `ack` tool mirror.
- `idempotency.py` **(new)** — standalone G2 ledger module, not yet wired into a consumer.
- `test_daemon.py` **(new)** — 15 pytest unit tests, run via `python3 -m pytest test_daemon.py -q`
  from that directory. All pass, against scratch DB/socket paths only (tmp_path fixtures).
- `~/.config/opencode/opencode.json` — added two **inert** env keys (`BRIDGE_HOST: ""`,
  `BRIDGE_REPO: "charon"`) to the `session-bridge` MCP entry. `BRIDGE_SOCKET` (explicit, still set)
  wins in the resolution priority, so this is a documented no-op — verified it does not affect the
  already-running `yoda` process (which read its env at its own process start, unaffected by a
  config-file edit) and would only apply to a brand-new session spawned after this edit.

### daemon.py — what changed and why

- **NB1 (lease-token leak) — CLOSED.** New `_PEER_VISIBLE_COLUMNS` allowlist; `_row_to_dict`
  rewritten to build its dict only from that allowlist (`lease_token` deliberately absent).
  `lease_token` is only ever a top-level sibling field on `register`/`claim` responses, minted as a
  local Python variable, never a row round-trip. Verified: `lease_token` value never appears in
  `json.dumps()` of any `board`/register-embedded-board response, and a synthetically-added future
  secret column is excluded by default (allowlist, not denylist).
- **NB2 (seq persistence) — CLOSED.** New `seq_counter` table (single row, id=1); `_next_seq()`
  reads+increments it inside the same transaction as the `nudge()` write. Verified persisted across
  a simulated restart (fresh connection). `_sort_key()` implements the `(0, ts)` vs `(1, seq)`
  total-order key exactly as specified — verified a legacy no-seq message sorts first alongside
  seq'd ones with no crash.
- **B1/lease model — CLOSED for Phase 0-1's claim/purge scope.** `register`/`claim` mint
  `lease_token = secrets.token_hex(16)` + `lease_expires_at = now + LEASE_POLL_TTL_S` (alias of the
  existing `SESSION_TTL_S`, so poll-mode cadence is byte-identical to today). `claim`'s steal-check
  and `_purge_stale`'s staleness check now compare `lease_expires_at` to now — **all `os.kill`/PID
  liveness logic removed from the authority path** (kept `pid` column, decorative only, per Mi5).
  Verified: a claim is correctly rejected while a fake-PID (999999, never existed) owner's lease is
  fresh, and correctly stolen once the lease is made to lapse — proving PID is genuinely never
  consulted.
- **G1 (durable delivery, ack, redeliver window, GC, queue caps, oversized-frame) — built for
  Phase 0-1's non-push scope.** `nudge_messages` entries gained `seq`/`delivered_at`/`ack_at`
  (additive; legacy objects read via `.get(...)`). `board()`/`update()` read paths are now
  **non-destructive**: `_process_read()` stamps `delivered_at` on first read, keeps replaying an
  unacked message until either the new `ack` RPC clears it or `REDELIVER_WINDOW_S` (120s) elapses
  since first delivery (auto-ack). New `ack(session_id, lease_token, message_ids)` RPC — additive,
  requires the caller's own lease_token (rejects a wrong/missing token). `_gc_nudge_ttl_all()` drops
  any message older than `NUDGE_TTL_S` (24h) regardless of ack state, on every `_purge_stale` tick,
  logged to stderr (visible, not silent). `nudge()` now rejects outright (`{ok:false, error:"target
  queue full"}`) past `MAX_QUEUE_LEN`/`MAX_QUEUE_BYTES` instead of silently truncating. `_recv_all`
  now returns `(data, overflowed)`; the daemon loop sends an explicit `-32000` error before closing
  an oversized-frame connection instead of silently dropping it.
  - **Deliberately NOT done (Phase 2):** `poll_wait`, the waiter registry, push-mode lease renewal,
    the always-on renewer service. Without those, `ack`/`seq`/redeliver-window are dormant-but-real
    capabilities any existing `board()`/`update()` caller already benefits from (replay-safe reads),
    not yet driven by an active push consumer.
- **M5 (per-fleet isolation) — code-level enabler only, not deployed.** `DB_PATH` is now
  `BRIDGE_DB`-env-driven (was hardcoded), alongside the already-env-driven `BRIDGE_SOCKET`. Verified
  two daemon module instances, given distinct `BRIDGE_DB`/`BRIDGE_SOCKET` env vars, keep fully
  separate SQLite files with zero cross-visibility. **Not done:** the actual two-systemd-unit
  deployment on `$COORDINATOR_HOST`, the two independent SSH tunnel units, the disk-quota mounts —
  all of that is real infra standup on Roci, explicitly out of scope (no SSH/deploy).
- **G2 (idempotency) — standalone scaffold, not wired in.** New `idempotency.py`: `claim()` (atomic
  `INSERT OR IGNORE` on `(session_id, message_id)`, returns whether this is the first claim) +
  `gc()` (prunes past the same `NUDGE_TTL_S` horizon as the server queue). Verified redelivery
  dedup and GC pruning. Not wired into any consumer because the consumer (`bridge-watch.sh`) is
  Phase 2, out of scope.
- **Mi5 — fixed.** `import struct` moved to module top-level (was inside `if __name__ ==
  "__main__":`, meaning it would `NameError` if `daemon.py` were ever imported as a module rather
  than run as a script — which every test in `test_daemon.py` now does).

### proxy.py — what changed and why
- **Phase 0 shim:** `BRIDGE_HOST` unset + no `bridge-hosts.env` → `SOCKET_PATH` resolves to exactly
  today's default (`/tmp/charon-bridge.sock`), verified. An explicit `BRIDGE_SOCKET` env var (as
  `opencode.json` sets today) always wins regardless of `BRIDGE_HOST` — verified — so the live setup
  is untouched.
- **Phase 1:** when `BRIDGE_HOST` is set and no explicit `BRIDGE_SOCKET` override exists, the socket
  path resolves from the gitignored `~/.charon/bridge-hosts.env` (`BRIDGE_SOCKET_<REPO>` keyed by
  `BRIDGE_REPO`, falling back to a generic `BRIDGE_SOCKET` key). Verified against a scratch
  `bridge-hosts.env` fixture for both `charon` and `mediastack` repo values. **No real coordinator
  host/IP appears anywhere in `proxy.py`'s source** — verified by grep; the real value only ever
  lives in the gitignored env file, per the hard constraint.
- New `ack` tool added to proxy.py's own `_TOOLS` mirror (proxy.py answers `tools/list` locally, not
  by forwarding to the daemon, so it must stay in sync) — verified via a live daemon.py +
  proxy.py subprocess pair over a real (scratch) Unix socket that `tools/list` reports exactly the
  7 original tools + `ack`, and that `register`'s real wire response carries `lease_token`
  top-level while it's absent from the embedded `board`.

### Deliberate scope exclusions (confirmed, not silently dropped)
- `poll_wait`, `bridge-watch.sh`, `charon-bridge-renewer.service`, `SessionStart`/`Stop` hook
  wiring, `active-sessions.<repo>.list` — Phase 2, the "push watcher."
- `status` RPC, `bridge-status` CLI, kill-switch sentinel/`bridge-killswitch.sh`, `AGENTS.md`
  heartbeat-retirement rewrite — Phase 3.
- Actual two-daemon/two-tunnel/disk-quota deployment on `$COORDINATOR_HOST` — real infra standup,
  forbidden this session (no SSH/deploy/touch Roci). Only the client-side code that *would* use it
  once deployed is built and tested.
- NB3's renewer-liveness fix and the review's two Phase-2-tracked follow-ups (same-host PID check
  on the renewer; `_purge_stale`'s clobber-vs-queue-cap reconciliation) are Phase-2 material by the
  review's own verdict — untouched, not silently dropped, tracked for whoever builds Phase 2.

### A note on the design's own regression-test spec (found during implementation)
`_PATTERNS`-style break-on-first-match logic in `check_file()` (repo B) means a `10.0.1.42` string
is caught by the **generic** `10\.\d+\.\d+\.\d+` pattern before the list ever reaches the newly
added named `10.0.1.\d+` pattern (list order: generic, then named, per the design's own placement
instruction). The design's suggested regression test ("assert '`coordinator LAN subnet`' in the
violation string for `10.0.1.42`") would fail as literally written. Implemented instead: a direct
test against `_PATTERNS` proving the named pattern exists and matches `10.0.1.42`, plus an
end-to-end `check_file()` assertion that the line is flagged (by whichever pattern wins) — same
protective coverage, accurate to actual runtime behavior. Flagging this rather than silently
"fixing" the spec.

---

## Repo B — Charon product repo (`/home/stack/code/charon`, public)

Files changed (all uncommitted, working tree only):
- `tools/check_public_clean.py` — added 3 new patterns after the existing generic `10\.\d+\.\d+\.\d+`
  entry: named `10\.0\.1\.\d+` ("coordinator LAN subnet"), `192\.168\.\d+\.\d+`, and
  `172\.(1[6-9]|2\d|3[01])\.\d+\.\d+` (full RFC1918 coverage).
- `tools/.public-clean-exceptions.json` — **populated** (was `{}`). Contains every pre-existing
  legitimate hit in the current tree (26 files, ~100 lines after the new patterns added a few more
  self-referential hits inside the guard's own pattern list and its own test file's fixtures): the
  documented `4-lom` runner label (workflows, `CONTRIBUTING.md`, `actionlint.yaml`), pinned GitHub
  Action commit SHAs, and doc/test-fixture references to `charon-vm`/`charon-private`/`/home/stack`
  that are intentional narrative content in ADRs/review-logs/tests, not leaks. Regenerated
  mechanically (ran the checker against the live tree, parsed its own violation output into the
  exceptions JSON) rather than hand-curated, to guarantee it's exhaustive and matches actual
  guard behavior line-for-line.
- `tests/test_public_clean.py` — added 3 regression tests for the new patterns (coordinator-subnet
  named-pattern existence + match, 192.168/16, 172.16/12), see the note above on why the
  "coordinator LAN subnet" string assertion is tested against `_PATTERNS` directly rather than via
  `check_file()`'s reported description.
- `src/charon/gate_runner.py` — added `(["python3", "tools/check_public_clean.py"],
  "public-clean")` as the 6th `CHECKS` tuple. No `.github/workflows/*.yml` change needed — `ci.yml`
  already runs `python3 -m charon.cli gate`, which iterates `CHECKS`.
- `.pre-commit-config.yaml` **(new file)** — local hook running `check_public_clean.py`,
  `always_run: true`, `pass_filenames: false` (per design §10-AMEND Fix 2). This is the first
  pre-commit config in the repo; nothing runs it automatically until a contributor does
  `pre-commit install` (not done in this session — no commit/push, and installing/activating
  pre-commit hooks system-wide was out of scope).
- **Not touched:** `tools/gates.json` (the `charon-gate` entry's `covers` text now slightly
  undercounts — reads "...(ruff check, mypy, boundary, version, gate-registry)" but a 6th check
  (`public-clean`) now runs too. Left as-is since `gates.json` wasn't in the design's touch-point
  list and doesn't gate anything (informational doc drift only, flagging rather than
  scope-creeping a fix).

### Verification (both green, re-run at the end of this session)
```
$ PYTHONPATH=src python3 -m charon.cli gate
CHARON GATE — running all validation checks...
  [ruff] OK
  [mypy] OK
  [SLOP-boundary] OK
  [version] OK
  [gate-registry] OK
  [public-clean] OK
CHARON-GATE: all checks passed

$ PYTHONPATH=src python3 -m pytest -q
1244 passed in 84.31s
```
`git status --short` in the product repo shows exactly: `gate_runner.py`, `test_public_clean.py`,
`tools/.public-clean-exceptions.json`, `tools/check_public_clean.py` modified, plus the new
`.pre-commit-config.yaml` — nothing else, no commit made.

---

## Proposed commit messages (not committed — for when the operator is ready)

**Repo A** (not a git repo today — no commit applicable; listed for reference if it's ever
versioned):
> Durable session-bridge Phase 0-1: lease model (not PID), persisted seq, non-destructive
> ack/redeliver-window delivery, per-repo DB/socket isolation, idempotency-ledger scaffold,
> cross-host proxy shim. Phase 2 (push watcher) and Phase 3 (status/kill-switch/docs) deferred.

**Repo B** (product, `/home/stack/code/charon`):
> fix(gate): wire check_public_clean.py into CHARON-GATE + pre-commit, close RFC1918 pattern gap
>
> Populates tools/.public-clean-exceptions.json (was empty, guard previously ran manually-only
> and would have gone CI-red on first wiring) and adds named 10.0.1.0/24 + full RFC1918 (192.168/16,
> 172.16/12) detection patterns. Prereq for the build-rig's cross-host session-bridge work
> (DURABLE-BRIDGE-DESIGN-v3.md) to have a real, automated leak guard before any coordinator-host
> code lands. No coordinator IP/hostname is committed anywhere — enforced by this guard itself.

---

## Full test evidence trail (all against scratch state, live daemon never touched)
- 15/15 `test_daemon.py` unit tests pass (lease redaction, allowlist-excludes-future-column, seq
  persistence across simulated restart, None/int total-order sort, claim/purge lease-not-PID x2,
  ack valid/invalid lease, replay-until-ack, MAX_QUEUE_LEN rejection, oversized-frame signal,
  idempotency claim/GC x2, per-repo DB isolation).
- End-to-end real-socket test: live `daemon.py` subprocess + `proxy.py` subprocess over a scratch
  Unix socket, full JSON-RPC wire round trip (`initialize`/`tools/list`/`tools/call` register),
  confirmed `tools/list` reports 8 tools (7 original + `ack`) and `lease_token` redaction holds
  over the real wire path, not just the in-process `_dispatch()` shortcut.
- Confirmed at the very end: `~/.charon/bridge.sock` and `~/.charon/session-bridge.db` timestamps/
  process PIDs unchanged from session start; a live `board()` call against the running daemon still
  returns the `yoda` session correctly (proving it's still up, still serving, running its
  pre-existing in-memory code — my on-disk edits have no effect on it until an explicit restart,
  which was not performed).
