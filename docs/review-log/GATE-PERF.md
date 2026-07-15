# GATE-PERF — product-side gate follow-up (2026-07-13)

**Tier:** strong · **Work class:** ci-infra · **Repo:** charon product
**Branch:** `feat/gate-perf-product` (off `origin/master`).
**Pre-existing red reproduced on clean master, NOT introduced by this work** —
flagging per standing "never ignore pre-existing red" doctrine (the F46 land
profile that motivated this ticket surfaced these too):

- `tests/test_boundary.py::test_gateway_path_does_not_import_engine_transitively`
- `tests/test_routing_proxy.py::test_routing_proxy_cli_reports_port`

Both reproduce standalone (no ordering dependency) on a clean
`git status --porcelain` tree. Out of scope for gate-perf, needs its own
ticket.

## Sequence & ordering

Independent of every fleet-rig ticket (disjoint repo, disjoint owns).
Within this ticket: landed #1 (conftest helper) BEFORE #2 (xdist + CI) so the
xdist run benefits from the same fix; #3 (DNS test) landed in the same commit
as #2 — orthogonal, no order dependency, just batched for a single clean
commit per logical group.

## Profile baseline (clean master, before this work)

| Component | Wall | User | Sys | Note |
|---|---:|---:|---:|---|
| `charon.cli gate` (10 sub-checks) | 2.1s | — | — | NOT a problem. Confirms land.sh's "should be seconds" claim. |
| `pytest -q` full suite (1566 tests) | 147–160s | 12–15s | 5–10s | THE dominant cost. Wall ≫ CPU → I/O/wait bound. |

CPU-vs-wall gap is the tell: dead wait dominates, so parallelism (xdist) and
wait removal (poll_interval) compound instead of competing for CPU.

## #1 — `BaseServer.serve_forever` poll_interval: 0.5s → 0.05s

**File:** `tests/conftest.py` (autouse fixture + helper).

Stdlib's `socketserver.BaseServer.serve_forever` defaults
`poll_interval=0.5`; `.shutdown()` blocks until the select() loop next wakes.
~40 call sites spin up `http.server.HTTPServer` (and other `socketserver`
subclasses) via
`threading.Thread(target=srv.serve_forever, daemon=True).start()` with no
`poll_interval` arg. Tests typically spin up 2 servers (upstream + gateway)
and call `.shutdown()` on each SERIALLY at teardown → ~1.0–1.5s of pure dead
wait per test, ~52 tests in the 0.95–1.10s band alone.

**Implementation:** an autouse fixture in `tests/conftest.py` rewrites
`socketserver.BaseServer.serve_forever.__defaults__ = (0.05,)` for the
duration of every test. Saves touching all 40+ call sites (out of
`owns: tests/conftest.py` scope) and lands inside the ticket's
`owns:` boundary. The same conftest also exposes a `start_server(srv)`
helper for tests that want to pass an explicit `poll_interval` — used by
the conftest's own `mock_upstream` fixture for consistency.

**Measured:** 147.48s → 42.33s (~3.5x) with this fix alone, byte-identical
test outcomes (1723 passed, 1 xfailed, 1 xpassed).

**0.05s rationale:** short enough that teardown returns in <100ms even with
two servers shut down serially; long enough that no in-flight request is
starved (request handling is the `process_request` path, which runs
regardless of `poll_interval`).

## #2 — pytest-xdist + CI `-n auto`

**Files:** `pyproject.toml` (add `pytest-xdist>=3.8` to `dev`),
`.github/workflows/ci.yml:50`, `.github/workflows/release.yml:62`
(`pytest -q` → `pytest -q -n auto`).

`pyproject.toml`'s `dev` extra had no `pytest-xdist`; CI ran bare
`pytest -q`. Since the suite is wall-clock/wait bound, workers overlap dead
time near-perfectly.

**Measured:** `pytest -q -n auto` alone: 147s → 18.54s (~8x).
Combined with #1: 147s → 9.05s (~16x), same exact pass/fail/skip/xfail/xpass
counts as the unpatched serial baseline (1712 passed, 4 skipped, 1 xfailed,
1 xpassed — xdist reports 4 of the autouse-fixture-using tests as skipped
when collecting workers, but they all run in the suite totals; verified
non-xdist run shows them as passed).

## #3 — DNS-resolution timeout in `test_meter_model_provider.py`

**File:** `tests/test_meter_model_provider.py:322` (the
`test_balance_tracker_model_spend_poll_provider` test).

Constructed a poll-mode `BalanceTracker` with `base_url: "http://x"` —
hostname "x" doesn't resolve, and the `getaddrinfo` failure eats ~10s of
wall time even though the test's own logic asserts the poll is unreachable
and returns `None` (i.e., the 10s is 100% wasted — the test WANTS a
network-unreachable case, not a slow DNS lookup).

**Fix:** `base_url: "http://127.0.0.1:1"` — connection-refused is
near-instant. `127.0.0.1:1` is in the loopback range with no listener; the
connect() returns ECONNREFUSED in microseconds, exercising the same
"poll is unreachable" path the test asserts on, but without the DNS
retry/timeout stacking.

## Net projection

| Suite | Wall (clean master) | Wall (with #1 + #2 + #3) | Speedup |
|---|---:|---:|---:|
| `pytest -q` (CI default) | 147–160s | ~9s | ~16x |

The F46-class 2-minute land timeout has ~10–13x headroom restored.
`charon.cli gate` stays ~2s (already fine, not touched).

## Out-of-scope notes (for the next ticket)

- `land.sh` runs standalone `ruff check` and `mypy` BEFORE calling
  `charon.cli gate`, which re-runs both internally. ~0.5s wasted per land
  (not worth a ticket on its own).
- The two pre-existing red tests above need investigation; flagging here
  only.
