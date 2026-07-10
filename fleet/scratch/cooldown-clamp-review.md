# cooldown-anchor-demotion — ADVERSARIAL review (fixes 1+2)

Reviewer: read-only. Repo `/home/stack/code/charon`, working tree (uncommitted).
Tests RUN: `PYTHONPATH=src python3 -m pytest -q tests/test_gateway_failover.py`
→ **14 passed in 8.66s, EXIT 0**.

## Verdict: SHIP  (fixes 1+2 are a strict improvement; fix 3 remains a real but non-blocking follow-up)

---

## 1. Clamp completeness — PASS (verified by trace)

`self._cooldown[...]` is WRITTEN in exactly ONE place: `proxy_server.py:1155`, inside
`set_cooldown`, and the clamp `secs = min(secs, self.max_cooldown_s)` (1153) sits on
the line above it. Every read/other-lock use (1107 apply_routes, 1120 chain_for, 1166
note_request, 1195 status) is NOT a cooldown write. `grep` across all of `src/` finds
no other `_cooldown[` write, no direct dict mutation, no second setter.

There are exactly TWO `set_cooldown` call sites, both clamped:
- `787` connection-unreachable → `set_cooldown(route, None)` → falls to default 60s → clamp no-op.
- `809` `obs.exhausted` (429/402 account-level/billing) → `set_cooldown(route, obs.retry_after)` → the extreme-Retry-After path → CLAMPED.
Retry-After, default-60, and the billing/429 path ALL funnel through the one clamped
setter. No bypass. Clamp is complete.

## 2. Ordering correctness — PASS

`now = time.monotonic()` captured once (1137); `fresh = expiry <= now`, `cooled = expiry
> now`; `cooled.sort(key=expiry ascending)` (1141). Absolute expiry ascending ≡ remaining
ascending because `now` is fixed → no sign error. Boundary: an entry expiring exactly at
`now` lands in `fresh` (`<=`), so a just-expired entry can't mis-sort into cooled. Ties →
Python stable sort keeps insertion order (benign). Clock is consistent (monotonic stored,
monotonic compared). `return fresh + cooled` unchanged → fresh-before-cooled holds exactly.

## 3. Behavioral tradeoff — BENIGN (confirmed)

Clamping a legit 1h backoff to 120s → provider re-enters `fresh`, gets retried, may 429
again → re-cooled 120s → poll-every-120s loop. Not harmful: a 429 is recorded with
`count_usage=False` (806) — NOT billed, no double-charge; failed attempts fail over, they
don't serve. Cost impact nil; only cost is one wasted round-trip per ~120s while genuinely
throttled. For the money-path this is the CORRECT trade: probe the free anchor every 2min
instead of sidelining it 57min. (Minor real-world caveat, not a code bug: a provider that
said "back off 1h" is now hit every 2min — some upstreams escalate penalties for ignoring
Retry-After. Low risk; note only.)

## 4. Does the root cause get fixed? — PARTIAL (honest)

Primary harm was: extreme Retry-After (~3420s) put the free NanoGPT anchor in the `cooled`
bucket (tried LAST) for 57min, so a working *paid fresh* provider served instead → cost
leak + anchor unused. Clamp cuts that window 3420→120s (~28×). Big real-world win.

Residual (the triage's separate issue) is REAL and untouched here:
- A peer broken via a NON-cooldown path never calls `set_cooldown`, so it stays `fresh`
  and sorts AHEAD of a cooled anchor. Confirmed two such paths: `810` a 404 (model-level)
  deliberately does NOT cool; `909→912` a broken/dropped stream records but does NOT cool.
- Net effect during any 120s window the anchor is cooled: fresh-but-broken peers are tried
  first. Mitigant: those peers are failover-eligible (404 / stream-error) so they fail over
  and the chain still REACHES the cooled anchor (cooled = last-resort, not excluded) — they
  add a wasted hop, they don't steal the completion. The completion is stolen only by a
  working *paid* fresh provider, and only for ≤120s now.
- Steady-state: if the anchor is genuinely throttled, it's demoted ~100% of the window but
  probed every 120s (vs once/57min). Faster recovery, at wasted-hop cost.

**Honest call:** fixes 1+2 are SUFFICIENT to kill the primary 57-min cost-leak sideline and
are a strict improvement. They do NOT fully eliminate anchor demotion — the anchor is still
deprioritized up to 120s per exhaustion event, and a non-cooldown-broken peer still outranks
a cooled anchor. Fix 3 (anchor-awareness: keep the pool's designated primary ahead of the
cooled bucket, and/or cool no-cooldown-broken peers) is still WANTED for the full real-world
scenario, but is a legitimately separate, larger design change — not a blocker for shipping 1+2.

## 5. Regression / blast radius — LOW / contained

- `max_cooldown_s` new ctor param default 120.0; grep confirms NO caller in api.py/gateway.py
  passes it (nor `default_cooldown`) → both stay at defaults, matches existing style. No
  CLI/config plumbing changed.
- `order_by_cooldown` only reorders WITHIN the cooled bucket; fresh/cooled split + `fresh +
  cooled` composition unchanged → no change to which providers are tried, only cooled-among-
  cooled order. No change to selection/billing/exhaustion logic elsewhere.
- One latent footgun (LOW): the clamp `min(secs, max_cooldown_s)` also caps the DEFAULT path,
  so a future caller setting `default_cooldown > max_cooldown_s` (e.g. 200 vs 120) would be
  silently capped. No such caller today; consistent with documented "ceiling on ANY cooldown."
- 4 new tests genuinely exercise the claims: huge-Retry-After clamp (`≤120`), default no-op
  (`55<r≤60`), cooled-bucket soonest-first (reverse input → asserts order flips), fresh-before-
  cooled no-regression. Gaps (non-blocking): no end-to-end test that the `809` billing path is
  clamped (covered transitively — all paths hit the one setter), no 3-way/tie test.

---

## Must-fix-before-commit (ranked)
1. (none are blockers) — SHIP as-is.
Nice-to-have / follow-up tickets, not gating this commit:
2. Track fix 3 (anchor-awareness + cool the non-cooldown-broken paths at 810/909) as the
   named follow-up — it's the residual for the actual reported scenario.
3. Optional: assert-comment or guard that `default_cooldown <= max_cooldown_s`, or clamp only
   the Retry-After branch, to remove the silent-cap footgun if the two ever get config-wired.
