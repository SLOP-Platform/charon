# cooldown-anchor-demotion — fixes 1 & 2 implemented

Repo: `/home/stack/code/charon` (working tree, uncommitted — manager to review/commit/push).
Source: root cause + recommended fix from `reds-triage.md` §3.

## Scope

Implemented ONLY fix 1 (clamp Retry-After-derived cooldown) and fix 2 (order
cooled bucket by remaining time, ascending). Fix 3 (anchor-awareness) is a
separate, bigger-design ticket — NOT touched here, per brief.

## Changes

### `src/charon/proxy_server.py`

1. New constructor param `max_cooldown_s: float = 120.0` on
   `GatewayProxyServer.__init__`, stored as `self.max_cooldown_s`. Same
   pattern as the existing `default_cooldown: float = 60.0` param (a plain
   constructor default, not currently wired through CLI/config anywhere —
   confirmed via `grep -rn default_cooldown` that no caller in `gateway.py`/
   `api.py` passes it explicitly, so `max_cooldown_s` needs no further
   plumbing to match existing style).

2. `set_cooldown()`: after computing `secs` (Retry-After value, or
   `default_cooldown` if none/zero — **unchanged** logic), added
   `secs = min(secs, self.max_cooldown_s)`. A huge upstream Retry-After
   (the observed ~3420s / 57min that sidelined the anchor) is now clamped to
   120s by default; the no-Retry-After 60s default path is untouched (60 <
   120, clamp is a no-op there).

3. `order_by_cooldown()`: after splitting into `fresh`/`cooled` buckets
   (unchanged bucketing — fresh always precedes cooled), added
   `cooled.sort(key=lambda r: self._cooldown.get(r.upstream_base, 0.0))` so
   the cooled bucket is ordered by soonest-recovering-first (ascending
   absolute cooldown-expiry timestamp, which is equivalent to ascending
   remaining time since `now` is fixed at the top of the call).

Full diff (both files) is in the working tree; `git diff --stat`:
```
 src/charon/proxy_server.py     | 21 +++++++++++++--
 tests/test_gateway_failover.py | 58 +++++++++++++++++++++++++++++++++++++++
 2 files changed, 77 insertions(+), 2 deletions(-)
```

### `tests/test_gateway_failover.py`

Added 4 tests (direct unit tests against `GatewayProxyServer.set_cooldown`/
`order_by_cooldown`, no live HTTP server needed — matches the file's existing
scope/theme, its docstring already mentions "provider cooldown"):

- `test_set_cooldown_clamps_huge_retry_after` — Retry-After=3420 → remaining
  cooldown clamped to ≤120s (`max_cooldown_s=120.0` explicit).
- `test_set_cooldown_default_unaffected_by_clamp` — no Retry-After → still
  ~60s (default_cooldown), clamp is a no-op.
- `test_order_by_cooldown_orders_cooled_bucket_by_remaining_time` — two
  cooled routes (100s vs 5s remaining), passed in reverse order; asserts the
  5s-remaining route sorts first.
- `test_order_by_cooldown_fresh_before_cooled_no_regression` — one fresh +
  one cooled route, cooled listed first in input; asserts fresh still always
  sorts first (no regression to R7 bucketing).

Note: these tests construct `GatewayProxyServer()` without calling
`serve_in_thread()`/`serve_forever()`, so cleanup uses `gw.server_close()`
(matches `test_gateway.py:39`'s pattern) — NOT `gw.shutdown()`, which would
hang forever waiting on an internal event that's only set inside
`serve_forever()`'s loop. Caught this before it shipped as a hung test.

## Verification

```
$ cd /home/stack/code/charon && PYTHONPATH=src python3 -m charon.cli gate
CHARON GATE — running all validation checks...
  [ruff] OK
  [mypy] OK
  [SLOP-boundary] OK
  [version] OK
  [gate-registry] OK
  [public-clean] OK
CHARON-GATE: all checks passed

$ PYTHONPATH=src python3 -m pytest -q
1250 passed in 107.65s (0:01:47)
```

(Baseline before this change was presumably 1246 passed — 4 new tests
account for the delta; `test_gateway_failover.py` alone: 14 passed, up from
10.)

## Proposed commit message

```
fix(gateway): clamp Retry-After cooldown + order cooled bucket by remaining time

cooldown-anchor-demotion: an upstream-reported Retry-After with no upper
bound (observed ~3420s / 57min) could sideline a provider — anchor or
not — for tens of minutes. set_cooldown() now clamps to a configurable
max_cooldown_s (default 120.0). order_by_cooldown() now orders the
cooled bucket by soonest-to-recover first instead of arbitrary
(insertion) order, so among several cooled providers the closest-to-
returning one is preferred. Fresh-before-cooled bucketing (R7) and the
no-Retry-After 60s default are unchanged.

Anchor-awareness (protecting the pool's designated primary from
demotion even when cooled) is a separate, larger design change — not
in scope here.
```

## Not done (out of scope per brief)

- Fix 3 (anchor-awareness in `order_by_cooldown`) — separate ticket.
- No commit, no push — working tree left dirty for manager review.
