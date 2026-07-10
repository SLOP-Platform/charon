# Dedup + decomposition-prep apply log

Board-writer sub-session · 2026-07-08 · executes the operator-APPROVED actions from
`fleet/scratch/proxy-decomposition-analysis.md`. NO commit/push (manager lands).
validate_board.sh: **GREEN (exit 0)** after all changes, no new reds.

---

## 1. INC-401-FAILOVER — VERIFIED + CLOSED

**Verify (in /home/stack/code/charon, commit 307652d "classify wrapped/unknown 401s as
failover-eligible + synthesize all-exhausted terminal"): CONFIRMED — BOTH parts present in
current master source (HEAD f369b7c):**
- (1) 401 classification patterns — `src/charon/proxy.py:74-75` `_UNSUPPORTED_BODY_PATTERNS`
  contains "not supported", "no such model", "model not found", "unknown model" (+ more);
  gated by `_UNSUPPORTED_STATUSES = {400, 401, 422}` and driven via `_is_unsupported_model`
  → the loop fails over instead of relaying the raw 401.
- (2) `all_providers_exhausted` synth — `src/charon/proxy_server.py:830`
  `"type": "all_providers_exhausted"` (synthesized terminal, not raw-relay).
- Ticket's old line refs (:751-756) confirmed stale/obsolete.

**Action taken (board done convention = live `.md` + `state/done/` marker, mirrors SR-1 etc.):**
- Annotated `> CLOSED 2026-07-08 — superseded by 307652d (verified)` block at top of the ticket.
- Renamed `board/INC-401-FAILOVER.md.parked` → `board/INC-401-FAILOVER.md` (un-parked to live so
  the done-marker matches a board ticket — a marker with no matching live `.md` would trip the
  validator's orphan-marker RED).
- Created `state/done/INC-401-FAILOVER` marker.
- Validator now lists INC-401-FAILOVER as an all-done/historical owner of proxy.py /
  proxy_server.py / test_proxy.py — no live collision.

**Deps de-listed (dep now satisfied):**
- `DRAIN-ROUTING.md.parked`: `depends_on: SR-5b, INC-401-FAILOVER` → `depends_on: SR-5b`
  (+ dep-pruned annotation; historical real-dep prose retained but moot).
- `SR-6.md.parked`: `depends_on: SR-2, INC-401-FAILOVER` → `depends_on: SR-2`
  (+ dep-pruned annotation).

---

## 2. UX-POLISH — owns edited (drop proxy_server.py)

- `owns:` `cli.py, proxy_server.py, gateway.py, connect.py` → `cli.py, gateway.py, connect.py`.
- Annotated why: both its proxy_server.py items already shipped (item 9 Setup link ~:95-107;
  item 10 token cookie `_maybe_set_token_cookie` ~:452-458 / cookie set ~:569-575). Leaves the
  proxy_server.py contention set. Stays PARKED.

## 3. SR-6-Phase2 — fold annotation

- Annotated `> FOLD into SR-6 (Phase 2); revisit-trigger unmet, stays parked`. No owns change.
  It is SR-6's Phase 2 (grows translate.py), coupled by construction; REVISIT-TRIGGER unmet.

## 4. COOLDOWN-FIX3 — VERIFIED + TRIMMED

**Verify (f3a73f2 / v0.3.6): CONFIRMED LANDED —** `max_cooldown_s=120.0`
(proxy_server.py:1013/1062), clamp `min(secs, self.max_cooldown_s)` (proxy_server.py:1153),
cooled-bucket ordering by soonest-to-recover (`order_by_cooldown`, proxy_server.py:1130-1142).
NOTE: the clamp/ordering landed in **proxy_server.py** (routing state on GatewayProxyServer),
NOT proxy.py.

**Action:** annotated VERIFIED+TRIMMED; scope TRIMMED to the RESIDUAL proxy.py edge-case audit
only (Retry-After parse path: missing/garbage/negative/overflow, all-cooled pools, DRAIN
pre-flight interaction) — "CLOSE if the audit surfaces nothing actionable". owns kept = proxy.py
(per its D&S flag). Stays PARKED. Not closed (genuine residual audit remains).

## 5. BRIDGE-RELAYFEATURES — reconcile annotation

- Annotated `> RECONCILE before build: likely overlaps the RFL-* RelayFreeLLM port; trim to
  non-RFL transformative gaps OR confirm it subsumes RFL-* (don't build both)`. Stays PARKED
  (also gated on BRIDGE-HARDEN).

## 6. GUI-SVELTE-BUILD — DEFERRED (operator)

- Annotated `> DEFERRED 2026-07-08 (operator): inline console ships now via SR-13/RFL-2/RFL-4;
  Svelte SPA revisited later. Contradicts those inline tickets — do NOT build until
  re-prioritized`. Already `.parked`; confirmed parked.

## 7. PROXY-SERVER-DECOMPOSE — FILED

- New `board/PROXY-SERVER-DECOMPOSE.md.parked`. tier: frontier · work_class: refactor ·
  branch: refactor/proxy-server-decompose · depends_on: PROXY-FAILOVER-FIX (real-dep:
  single-owner-file hard sequence — PFF-P1 holds proxy_server.py, decompose rebases after).
- owns: proxy_server.py, proxy_console_assets.py, proxy_response.py, console_router.py,
  forwarder.py, tests/test_check_arch.py.
- accept: `PYTHONPATH=src python3 -m pytest -q` (full suite green after each staged move).
- Scope encodes the §2/§3 4-module split, facade re-exports (public surface preserved),
  add 4 modules to `_ENGINE_FORBIDDEN`, 4 behavior-preserving verbatim-move commits
  (assets→response→console_router→forwarder, hardest last), forwarder = HIGH-risk adversarial
  review, product STANDALONE.

## 8. Build prompt — AUTHORED

- `prompts/proxy-server-decompose.md` — seams + approx line ranges, mandatory facade re-export
  list, `_ENGINE_FORBIDDEN` requirement, 4-commit staging (suite green each), behavior-preserving
  hard constraint, a `## Dependencies & sequence` section (so the D&S validator gate passes on
  un-park), and a LAST STEP (required) commit + report-SHA with "Do NOT push or merge" on its
  own line.

---

## validate_board result
`bash validate_board.sh` → **GREEN, exit 0.** No RED. No orphan-marker, no owns-collision,
no bad-dep, no WCI redundancy/false-blocking-dep. INC-401-FAILOVER correctly resolves as a
done/historical owner.

## Flags for manager attention
1. **GPT5-POOL-REORDER.md.parked** still carries `depends_on: INC-401-FAILOVER` (+ a rebase-after
   note). Out of this session's APPROVED scope (task named only DRAIN-ROUTING and SR-6), so left
   untouched. It's parked (not validator-scanned), but on un-park its INC-401 dep is now
   satisfied/closed and should be pruned the same way. REQUEST-NORMALIZER already self-pruned its
   INC-401 dep (it's done) — no action needed there.
2. **INC-401-FAILOVER done-representation:** closed as live `.md` + `state/done/` marker (the
   board's actual convention — every existing done ticket keeps its `.md` in board and has a
   marker). Did NOT delete/move the `.md` out of board, because a marker with no matching board
   `.md` trips the validator's orphan-marker RED. If the manager prefers pure archival, move BOTH
   the `.md` and the marker together (but that diverges from the SR-1/SR-2/... precedent).
3. **COOLDOWN-FIX3** clamp/ordering actually landed in proxy_server.py, though the ticket owns
   proxy.py; residual audit legitimately spans the proxy.py Retry-After parse path. Left owns =
   proxy.py per instruction; flagged in-ticket.
4. Nothing committed/pushed — all edits are on-disk in fleet/board + fleet/state + prompts, for
   the manager to land.
