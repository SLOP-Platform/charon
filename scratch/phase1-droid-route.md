# Phase-1 droid route — PROXY-FAILOVER-FIX (P1 + P5)

Prep date: 2026-07-08 · verdict: **BLOCKED** (do NOT un-park; would add NEW owns-collisions)

## Prompt
- Path: `/home/stack/charon-private/prompts/proxy-failover-fix.md` (WRITTEN)
- Scope: Phase 1 ONLY = P1 (bounded `Retry-After` on terminal 503 + clamp upstream 402/429/503
  relays ≤120s) + P5 (browser-like outbound User-Agent). NOT P2/P3/P4.
- Anchors baked in (verified against live source):
  proxy_server.py `_send_resp_headers` def ~483, terminal 503 ~827, single-upstream relay ~840,
  `retry_after_hint` helper (reuse `self._cooldown`/`default_cooldown`/`max_cooldown_s`);
  `_DEFAULT_UA`:71, `_BANNED_UA_PREFIXES`:74, serve UA :542-546; balance.py UA :41/:70/:100.
- Includes `## Dependencies & sequence` (D&S standing-rule section — required once un-parked),
  the P1/P5 acceptance tests, STANDALONE constraint, and LAST STEP commit rule
  ("do NOT push or merge" on its own line).

## Ticket edits (PROXY-FAILOVER-FIX.md.parked — kept PARKED)
- `owns:` trimmed to Phase-1 files ONLY:
  `src/charon/proxy_server.py, src/charon/balance.py, tests/test_proxy_server.py, tests/test_balance.py`
  (dropped gateway.py/config.py/test_gateway_failover.py/test_gateway_tiers.py — those are P2/P3).
- `accept:` trimmed to `tests/test_proxy_server.py tests/test_balance.py`.
- `prompt:` repointed to `/home/stack/charon-private/prompts/proxy-failover-fix.md`.
- Added `phase1-note:` (work_class stays money-path for P2 framing; Phase-1 code is
  header-only/outbound-only, LOW-RISK, not a money-path change).
- Fixed latent bug: `depends_on: none` → empty `depends_on:` (validator treats the literal
  "none" as a missing ticket → spurious bad-dep on activation; GUI-SVELTE-BUILD uses empty).

## validate_board result — NEW REDS? **YES**
Baseline (PARKED): **5 RED** — all pre-existing GUI-SVELTE-BUILD issues
(missing-prompt + Dockerfile + config.py + gateway.py + proxy_server.py collisions).

Momentary un-park test (then restored to .parked): **7 RED**. New reds introduced by activation:
1. **owns-collision `src/charon/proxy_server.py`** — PROXY-FAILOVER-FIX (depends_on empty →
   ordered against nothing) adds 8 NEW unsequenced pairs vs every live owner:
   `DRAIN-ROUTING | GUI-SVELTE-BUILD | INC-401-FAILOVER | RFL-2 | RFL-3 | RFL-4 | SR-13 | SR-6`.
2. **owns-collision `tests/test_proxy_server.py`** (was INFO/1-live-owner) → NEW red line:
   `GUI-SVELTE-BUILD | PROXY-FAILOVER-FIX`.
(`balance.py` + `test_balance.py` have no other owner → clean, no collision there.)

## Verdict: **BLOCKED**
`src/charon/proxy_server.py` and `tests/test_proxy_server.py` are already-hot files. Un-parking a
Phase-1 ticket that owns them adds new concurrent-collision reds. Per the collision-check rule,
NOT un-parking. Ticket left `.md.parked`; prompt + owns are staged and ready for a clean launch
window.

## Conflict + recommended sequencing (safest)
The board is ALREADY structurally red purely because GUI-SVELTE-BUILD (a large multi-phase
frontend rebuild, `depends_on:` empty) sits unsequenced on the hot files. Nothing can launch a
clean wave on `proxy_server.py` until that is resolved. There are **zero active claims**
(state/claims empty) — nothing is in flight, so this is a sequencing decision, not a live race.

Recommendation, in priority order:
1. **Land PROXY-FAILOVER-FIX Phase-1 FIRST, solo.** It is a tiny, well-anchored, header-only /
   outbound-only fix and the highest-value money-path bug (prevents the ~8h client-stall 503).
   To launch it clean, temporarily **PARK the competing live owners of `proxy_server.py`** for the
   duration of this one tab: `GUI-SVELTE-BUILD, DRAIN-ROUTING, INC-401-FAILOVER, RFL-2, RFL-3,
   RFL-4, SR-13, SR-6` (park at minimum GUI-SVELTE-BUILD + whichever of the others are not being
   worked this cycle). With the failover fix as the only live `proxy_server.py` owner + its
   `depends_on:` empty, the board clears to GREEN on that file.
2. After the failover fix merges, un-park the larger tickets and **rebase them on top** — the
   header/UA diff is trivial for GUI-SVELTE-BUILD and the RFL/INC/DRAIN/SR chain to absorb.
3. Do NOT try to make PROXY-FAILOVER-FIX `depends_on` its way clean: to be `ordered` against all
   owners it would need a transitive dep reaching each of 8 tickets (incl. the unsequenced
   GUI-SVELTE-BUILD), which is both impossible via one edge and wrong — it would block a critical
   bugfix behind a giant GUI rebuild.

## Operator command (only after the block is cleared — competing owners parked)
Tier = `strong` (from the ticket). Once `bash /home/stack/charon-private/fleet/validate_board.sh`
is GREEN on proxy_server.py:
```
mv /home/stack/charon-private/fleet/board/PROXY-FAILOVER-FIX.md.parked /home/stack/charon-private/fleet/board/PROXY-FAILOVER-FIX.md
bash /home/stack/charon-private/fleet/validate_board.sh    # confirm no new reds
bash /home/stack/charon-private/fleet/fleet-droid.sh strong --wait 3 --retries 10
```
