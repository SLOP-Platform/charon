repo: charon
tier: strong
difficulty: 2
work_class: ci-infra
branch: feat/gate-perf-product
depends_on:
owns: pyproject.toml, tests/conftest.py, tests/test_meter_model_provider.py
note: CI workflow lines (.github/workflows/ci.yml:50, release.yml:62) need a one-word
  `pytest -q` -> `pytest -q -n auto` edit too (see fix #2 below) but are NOT claimed in `owns` —
  release.yml/heavy.yml are already owned live by DOCKER-SMOKE-CLEANUP; ci.yml is unclaimed by any
  live ticket (verify with `grep -l ci.yml fleet/board/*.md` before touching it) but is a
  single-line, low-risk edit not worth a formal owns-collision entry.
accept: |
  GATE-PERF product-side follow-up (fleet-side half already landed on feat/gate-perf — see
  fleet/gate.sh parallel *.test.sh + lint). Profiled on 2026-07-13 against /home/stack/code/charon
  @ clean master. Numbers are real wall-clock (`time .venv/bin/python -m pytest -q`), not estimates.

  ## Dependencies & sequence
  No depends_on — this repo (charon product) is disjoint from the fleet-rig ticket that already
  landed (owns fleet/gate.sh only). Single ticket, single wave, no ordering needed. Land-order
  within itself: fix #1 (conftest helper) before #2 (adopt in CI/pyproject) so the xdist run
  benefits from the same fix; #3 (DNS test) is independent and can land in any order.

  ## Ranked cost breakdown (product gate: `charon.cli gate` + `pytest -q`)
  - `charon.cli gate` (ruff+mypy+boundary+version+gate-registry+public-clean+no-rig-import+
    check-arch+security-scan+test-patterns, 10 checks): 2.1s. NOT a problem — land.sh's claim
    that "should be seconds" is TRUE and confirmed. land.sh ALSO runs standalone `ruff check` and
    `mypy` before calling `charon.cli gate`, which re-runs both internally — pure redundancy
    (~0.5s wasted per land; not worth a ticket, noted here only for completeness).
  - `pytest -q` (full suite, 1566 tests): 147-160s wall-clock — THE dominant cost, and the one
    that actually blew the F46 land's 2-minute timeout. Root-caused to 3 independent sinks below.
    CPU time is TINY relative to wall time (user 12-15s + sys 5-10s vs 147-160s wall) — this is
    the tell: the suite is dominated by wall-clock WAITING (I/O/select-poll), not computation, so
    both fixes below (dead-time removal + parallelism) compound instead of competing for CPU.

  ### #1 — serve_forever() default poll_interval (est. ~50s of the 147s, confirmed ~105s saved)
  ~40+ call sites across tests/*.py (test_gateway_failover.py, test_proxy_server.py,
  test_capability_gating.py, test_forwarder_billing.py, test_latency_signal.py,
  test_catalog_refresh.py, test_gateway_gui_auth.py, test_provider_response_contract.py,
  test_router_core_r2.py, test_tier_lifecycle.py, tests/conftest.py, and ~25 more — full list via
  `grep -rn serve_forever tests/*.py`) spin up `socketserver.ThreadingMixIn` HTTP test doubles via
  `threading.Thread(target=srv.serve_forever, daemon=True).start()` with NO poll_interval arg.
  `socketserver.BaseServer.serve_forever()` defaults `poll_interval=0.5`; `.shutdown()` BLOCKS
  until that select() loop next wakes (stdlib docstring: "Blocks until the loop has finished").
  Most of these tests spin up 2 servers (upstream + gateway) and call `.shutdown()` on each
  SERIALLY at teardown → up to ~1.0-1.5s of pure dead wait per test, ~52 tests in the
  0.95-1.10s band alone (measured via `pytest --durations=0`, band-summed to 52 tests).
  FIX (verified locally via a sitecustomize.py monkeypatch of
  `socketserver.BaseServer.serve_forever.__defaults__ = (0.05,)` — proves the win WITHOUT
  touching any tracked file): add a small helper in tests/conftest.py, e.g.
    def start_server(srv, *, poll_interval: float = 0.05):
        t = threading.Thread(target=srv.serve_forever, args=(poll_interval,), daemon=True)
        t.start(); return t
  and switch the ~40 call sites from `threading.Thread(target=srv.serve_forever, ...).start()` to
  `start_server(srv)`. Zero behavior change (same HTTP servers, same requests served) — purely
  faster teardown. MEASURED: full suite 147.48s -> 42.33s with ONLY this fix (sitecustomize
  monkeypatch proxy for the real fix), same 1659 passed / 2 failed (pre-existing, see below) / 4
  skipped / 1 xfailed / 1 xpassed — byte-identical test outcomes, ~3.5x faster.

  ### #2 — no pytest-xdist / no parallelism (147s serial on a 16-core box)
  `pyproject.toml`'s `dev` extra has no `pytest-xdist`; CI (`.github/workflows/ci.yml:50`,
  `.github/workflows/release.yml:62`) runs bare `pytest -q`. Since the suite is wall-clock/wait
  bound (see CPU-vs-wall gap above), workers overlap dead time near-perfectly. MEASURED (installed
  pytest-xdist 3.8.0 into .venv for the experiment only, then uninstalled — pyproject.toml
  untouched): `pytest -q -n auto` alone: 147s -> 18.54s (~8x). Combined with fix #1: 147s -> 13.38s
  (~11x), same exact pass/fail/skip/xfail/xpass counts as the unpatched serial baseline.
  FIX: add `"pytest-xdist>=3.8"` to the `dev` extra in pyproject.toml; change
  `.github/workflows/ci.yml:50` and `release.yml:62` from `pytest -q` to `pytest -q -n auto`.
  Land AFTER #1 lands (xdist worker crash isolation makes the poll_interval fix easier to verify
  test-by-test first; not a hard dependency, just cleaner sequencing).

  ### #3 — single-test DNS-resolution timeout (10.03s, tests/test_meter_model_provider.py:322)
  `test_balance_tracker_model_spend_poll_provider` constructs a poll-mode BalanceTracker with
  `base_url: "http://x"` — hostname "x" doesn't resolve, and the getaddrinfo failure eats ~10s of
  wall time (DNS resolver retry/timeout stacking) even though the test's own logic asserts the
  poll is unreachable and returns None (i.e., the 10s is 100% wasted — the test WANTS a
  network-unreachable case, not a slow DNS lookup). FIX: use a base_url that fails FAST instead of
  slow-DNS — e.g. `http://127.0.0.1:1` (connection refused, near-instant) or monkeypatch the
  `_poll_deepseek`/adapter function directly. Saves ~10s on its own; independent of #1/#2.

  ## Pre-existing failures found while profiling (NOT introduced by this work — same on master,
  reproduce in isolation too; out of scope for gate-perf, flagging per standing "never ignore
  pre-existing red" doctrine — needs its own ticket/investigation):
  - FAILED tests/test_boundary.py::test_gateway_path_does_not_import_engine_transitively
  - FAILED tests/test_routing_proxy.py::test_routing_proxy_cli_reports_port
  Both reproduce standalone (`pytest tests/test_boundary.py::... tests/test_routing_proxy.py::...`
  in isolation, no ordering dependency) — confirmed on a clean `git status --porcelain` tree, so
  this is NOT test-order pollution from other work in this session.

  ## Net projection if all 3 land
  ~147-160s -> ~10-13s for `pytest -q -n auto` (fix #1 + #2 + #3 combined), i.e. the F46-class
  2-minute land timeout has ~10x headroom restored. `charon.cli gate` stays ~2s (already fine,
  not touched).
scope: |
  GATE-PERF ticket (fleet sub-session investigation, 2026-07-13). Larger/riskier product-repo
  changes than the fleet-side fix (which landed directly on feat/gate-perf in the
  charon-private-GATEPERF worktree: fleet/gate.sh now runs its 14 *.test.sh files + shellcheck
  concurrently — 5.92s -> ~1.98s, ~3x, same PASS/FAIL/exit output, verified 4x for flake).
  This ticket covers ONLY the product repo (/home/stack/code/charon) since no worktree was
  provisioned for it in this session and its changes (pyproject.toml, CI workflow, ~40 test call
  sites) are a wider blast radius than a fleet-rig-only fix.
ds: charon product repo. depends_on EMPTY — independent of every fleet-rig ticket (disjoint repo,
  disjoint owns). Internal to this ticket: land #1 before #2 (cleaner verification), #3 any order.
