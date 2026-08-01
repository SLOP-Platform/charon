# AMBIENT-COUPLED-TESTS review note

**Date:** 2026-08-01
**Ticket:** AMBIENT-COUPLED-TESTS
**Branch:** fix/ambient-coupled-tests

## What changed

Replaced the wall-clock and hardcoded-month assertions in
`tests/test_spend_limits.py` with a local `frozen_month` pytest fixture that
pins `charon.spend_limits.datetime.now()` to a known `YYYY-MM`. Tests now
derive the expected month from the same clock the code under test sees, so
they cannot fail simply because the calendar rolled forward.

## Why

The two failures (`:77` and `:91`) hard-coded `"2026-07"` as the expected
month for the spend limiter's `_month_start` field, while the production code
(`spend_limits.py:57`) reads the same field from `datetime.now().strftime("%Y-%m")`.
When UTC rolled to 2026-08 on CI, the real clock no longer matched the
hard-coded expectation, and the gate went RED with no code change between
local and CI. This is the same class of bug that hit
`tests/test_autoland.py` via `git config init.defaultBranch` earlier today:
the test's correctness depended on ambient environment nothing declares.

## Clock-freeze design

A test-local `_FrozenDatetime(datetime)` subclass replaces
`charon.spend_limits.datetime` for the duration of the test. It is deliberately:

- **Local to this test file** (not a `conftest.py` autouse). Other tickets own
  conftest edits; widening scope there would double-claim.
- **Class-attribute state (`frozen_year_month`)**, set per-test via
  `frozen_month.frozen_year_month = "YYYY-MM"`. Lets different tests pin
  different months without parameterization machinery.
- **Mid-month at noon (`YYYY-MM-15 12:00:00`)**. Far from any month boundary,
  so non-UTC timezones (the widest real-world TZs: `Etc/GMT+12`, `Pacific/Kiritimati`)
  cannot push the visible clock across a month boundary either.
- **Subclass, not replace.** `datetime.now()` is the only shimmed method;
  arithmetic, comparison, and JSON serialization all keep working because
  every instance is a real `datetime`.

Adopted libraries (`freezegun`, `time-machine`) checked against `pyproject.toml`
— neither is installed. A one-line pytest fixture beats both per the ticket's
"simplest thing that fully solves it" rule.

## Done-contract proofs

| Check | Command | Result |
|---|---|---|
| (a) gate excluding pre-existing out-of-scope failures | `python3 -m pytest -q --ignore=tests/test_autoland.py` | 2412 passed, 0 failed |
| (b) tests pass under clock forced to a DIFFERENT month | direct driver script with `frozen_year_month="2027-03"` | all 3 formerly-failing tests pass |
| (c) tests pass under `TZ=Pacific/Kiritimati` (UTC+14) | `TZ=Pacific/Kiritimati python3 -m pytest tests/test_spend_limits.py` | 12 passed |
| (c) tests pass under `TZ=Etc/GMT+12` (UTC-12) | `TZ=Etc/GMT+12 python3 -m pytest tests/test_spend_limits.py` | 12 passed |
| (d) sweep report | see below | — |

## Sweep results (all of `tests/`)

Every ambient-coupled test found. Each row says: what is coupled, what is its
current symptom, and whether it was fixed in this ticket.

| File | Line | Coupling | Symptom | Status |
|---|---|---|---|---|
| `tests/test_spend_limits.py` | 77, 91, 62, 83 | Wall clock (month) — `datetime.now()` against hard-coded `"2026-07"` / `"2020-01"` | **LIVE**: CI went RED on 2026-08-01 UTC | **FIXED in this ticket** |
| `tests/test_autoland.py` | 62, 250 | Host's `git config init.defaultBranch` (currently `main`) — `_branch_sha(repo, "master")` and `base_branch="master"` | **LIVE**: gate red on this host; same class as the previous AUTOLAND ticket's surface symptom | **OUT OF SCOPE** (`owns:` line is `tests/test_spend_limits.py` only); recommend a follow-up ticket that edits `src/charon/gitutil.py:init_repo` to pass `-b master` and adds a per-repo `default_branch` to the `git_repo` fixture |
| `tests/conftest.py:git_repo` | 67–72 | Calls `gitutil.init_repo` which reads host `init.defaultBranch` (production bug, not a test bug) | Same surface symptom as the row above | **OUT OF SCOPE** (conftest owned by another ticket); needs production-code fix in `gitutil.py:init_repo` |
| `tests/test_quota.py` | 248 | The string `"datetime"` appears as an allowed top-level import in an AST check | No assertion against a real clock — just a literal whitelist | **NOT AMBIENT-COUPLED** (false positive in the grep) |
| `tests/test_balance.py`, `tests/test_cost_budget.py`, `tests/test_forwarder_billing.py`, `tests/test_meter_*`, `tests/test_ledger.py` | — | None use `datetime.now` / `strftime` / `date.today` / `time.time()` against an assertion | — | **CLEAN** |
| All other `tests/test_*.py` | — | `monkeypatch.setenv("CHARON_HOME", str(tmp_path))` is the universal pattern | Already fully injected via fixture | **CLEAN** |

**Two classes of ambient input were swept and not found**:

- `os.environ[key]` reads without `monkeypatch.setenv` fixture. Every site that
  reads an env var does so via a `monkeypatch.setenv` fixture; the only
  unconditional `os.environ.pop` / `os.environ.get` calls are in
  `test_setup_tiers.py:83`, `test_routing_proxy.py:26`, `test_work_bearings.py:31`,
  `test_console_provider_mgmt.py:117`, `test_run_task_routing.py:85`,
  `test_config.py:128`, `test_decompose_sizing.py:378`, `test_tier_lifecycle.py:87`,
  `test_setup_web.py:78` — all of these read CHARON_HOME or OPENROUTER_API_KEY
  which are either pop-with-default (test setup) or read into a copy of `os.environ`
  for harness construction (legitimate use, not an assertion).
- `socket.gethostname`, `os.getlogin`, `os.getcwd` reads in test code — none
  found (only `os.getpid` in `test_ledger.py:102` for a lock file payload,
  which is content-not-assertion).

## Follow-ups recommended (not done — outside `owns:`)

1. **AMBIENT-COUPLED-TESTS follow-up #1**: fix `src/charon/gitutil.py:init_repo`
   to pass `-b master` (or any branch the caller wants) so the
   `tests/test_autoland.py` failures stop depending on the host's
   `init.defaultBranch`. This would unblock the gate on this host.
2. **AMBIENT-COUPLED-TESTS follow-up #2**: replace `datetime.now()` in
   `src/charon/spend_limits.py:57` with a configurable clock (e.g.
   `_now()` method, defaulting to `datetime.now()`) so that not just tests
   but also prod-callers could inject a clock if needed. Optional; the
   test-side fixture already solves the gate-blocking case.
