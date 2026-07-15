# FT-QUOTA-ENGINE — free-tier quota engine (windows + persistence)

**Change under review:** complete `src/charon/quota.py` (was an inert
sliding-window tracker) into a full free-tier enforcement engine, plus
the matching test extensions in `tests/test_quota.py`.

## What the ticket asked for, and what landed

- **Rolling + calendar windows.** Legacy `rpm`/`tpm`/`rpd`/`tpd` are
  unchanged: a plain int limit is still a 60s/86400s rolling sliding
  window. New keys `rwk`/`twk` add a 7-day rolling window, and
  `rmo`/`tmo` add a calendar-anchored monthly window (UTC, resets at
  00:00 on the 1st). `rpd`/`tpd`/`rwk`/`twk` can be opted into calendar
  reset by declaring the limit as a dict
  `{"limit": N, "reset": "calendar"}` — daily resets at UTC midnight,
  weekly at the next Monday 00:00 UTC. The legacy ``{"rpm": 500}`` shape
  is byte-for-byte the same behavior, so the wiring ticket can pick up
  the engine without operator-facing config churn.

- **Persistence.** Usage (calendar scalars AND rolling deques) is written
  to `<state_dir>/quota_usage.json` on every `record()`. The atomic-write
  discipline is REUSED from `balance.py` (the b8e62d0 fix):
  - dedicated `_save_lock` so concurrent `record()`s serialize the
    snapshot → write → replace (a stale write can never win);
  - unique tmp = pid + thread id + uuid4 hex so two callers never share
    a tmp path (the race that 526/1200 calls under 4 threads
    reproduced);
  - best-effort `OSError` swallow — a disk hiccup MUST NOT propagate
    into the request path. Same `quota_save_error` counter pattern
    `balance.py` uses.
  Load on `__init__` is fail-open: a corrupt or missing file degrades to
  empty usage so a fresh install (or a half-written post-crash file)
  can never block the gateway from starting.

- **Synchronous, stdlib-only.** No async, no third-party imports. The
  existing `test_stdlib_only_imports` allow-list was widened to include
  the new stdlib names (`json`, `os`, `uuid`, `pathlib`, `dataclasses`,
  `datetime`, `calendar`); the test still catches any real third-party
  import.

- **Test coverage for the three FAIL-ON-REVERT assertions** (ticket
  spec):
  - (a) monthly tpm-style cap blocks the (N+1)th token and a calendar
    reset clears it — `test_monthly_tmo_blocks_n_plus_one`,
    `test_monthly_tmo_resets_on_calendar_boundary`,
    `test_calendar_rpd_resets_at_utc_midnight`,
    `test_calendar_rwk_resets_on_monday`,
    `test_calendar_wait_time_is_until_next_boundary`;
  - (b) usage persists across a fresh instance pointed at the same
    state file — `test_calendar_usage_persists_across_instances` (with
    a paired negative `test_persistence_required_to_pass_test` that
    asserts a no-state-dir instance sees 0, so reverting the persist
    path immediately makes the positive test fail);
  - (c) rolling window behavior is identical to before —
    `test_legacy_rpd_still_rolling`, `test_legacy_rpm_unchanged`,
    `test_dict_limit_with_rolling_reset_is_rolling`.
  Plus: state-file well-formedness, corrupt-file fail-open,
  no-state-dir mode, rolling deque persistence, unconfigured-provider
  reload.

## Design notes worth flagging

- **Two clocks.** The original `now=` clock is `time.monotonic` (used
  for rolling-window eviction). Calendar boundary math needs a wall
  clock that maps to UTC, so a separate `_utc_now` (defaulting to
  `time.time`) was added with a `set_utc_now()` injection point for
  tests. The same FakeClock-for-monotonic + UtcClock-for-UTC split is
  what made the boundary tests deterministic.
- **`rmo`/`tmo` are calendar-only.** "30 rolling days" is a different
  concept from "calendar month"; the ticket spec explicitly calls
  `tmo` the monthly calendar cap, so a `reset="rolling"` form would
  be ambiguous. The constructor coerces them to calendar.
- **Wait time on calendar limits.** A blocked calendar cap waits until
  the next boundary (UTC midnight / Monday midnight / 1st of next
  month). A request that already sees a rolled calendar gets `0.0` —
  the next call will succeed, no wait needed.
- **Snapshot/load is per-provider, not per-window.** The on-disk shape
  is `{"providers": {p: {"rolling": {key: [ts, ...]}, "calendar":
  {key: {"period_start": t, "count": n}}}}}`. Rejected anything that
  isn't an int/float in load — fail-open with a partial schema is
  worse than fail-open with an empty one.
- **Privileged core stays stdlib-only.** `json`/`os`/`uuid`/`pathlib`/
  `dataclasses`/`datetime`/`calendar` are all stdlib; the boundary
  check passes; the engine directory is unaffected (quota.py lives in
  `src/charon/`, not `src/charon/engine/`).

## Gate status

Full `pytest -q`: 1739 passed, 1 xfailed, 1 xpassed (~161s). `ruff
check` clean. `mypy src tests` clean. `check_boundary.py src` clean.
`check_version.py` reports a pre-existing pyproject/installed
metadata drift (0.5.0 vs 0.3.1) — not introduced by this change and
explicitly not a fail per the gate rule (no `pip install -e`).
