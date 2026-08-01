repo: charon
tier: strong
difficulty: 2
work_class: tests
priority: 0
branch: fix/ambient-coupled-tests
depends_on:
owns: tests/test_spend_limits.py
serial_justified: |
  ONE class with one cause. The live breakage and the sweep are the same deliverable — patching
  the two failing assertions without sweeping guarantees the next boundary breaks us again.
execution: |
  Off-Claude via fleet-droid.sh, own worktree. PRODUCT repo (/home/stack/code/charon).
source: |
  Found 2026-08-01T00:02Z (session tott-doneeta) — CI `gate` went RED on PR #202 while the SAME
  gate was GREEN locally minutes earlier. Cause: CI runs UTC and the month rolled to 2026-08; the
  local box had not yet rolled. BLOCKS EVERY PRODUCT LAND (required check).
note: |
  ## THE LIVE BREAKAGE
  `tests/test_spend_limits.py` hard-codes the current month:
    - `test_persistence_survives_reload` (:77) — `assert lim2._month_start == "2026-07"`
    - `test_atomic_write` (:91) — `assert data["month_start"] == "2026-07"`
  Both now fail with `AssertionError: assert '2026-08' == '2026-07'`. Nothing changed in the code;
  the calendar changed. This was a time bomb from the day it was written.

  ## THE CLASS — this is the SECOND instance in one hour
  A test that depends on AMBIENT ENVIRONMENT NOTHING DECLARES:
    1. `tests/test_autoland.py` — depended on the host's `git config init.defaultBranch`.
       8 failures on a host set to `main`. Fixed + merged today (PR #202).
    2. `tests/test_spend_limits.py` — depends on the WALL CLOCK's current month. THIS ticket.
  Same shape, different ambient input. Both produce the worst failure mode we have: **green on one
  machine, red on another, with no code change between them** — which trains everyone to distrust
  the gate rather than the test.

  ## SCOPE
  1. Fix the two assertions. **Do NOT hard-code "2026-08"** — that just moves the bomb one month.
     Derive the expected month from the same clock the code under test uses, or inject a frozen
     clock. Prefer INJECTION over patching a global.
  2. **Sweep `tests/` for the whole class** and fix what you find. Ambient inputs to hunt:
     wall clock / current date / timezone · `git config` (any global) · `$HOME`, `$USER`, `$PATH` ·
     network availability · locale · hostname · CWD · env vars with no default.
     Report every instance found, including ones that are currently green — a latent one is the
     same bug that simply has not fired yet.
  3. If a frozen-clock helper is warranted, check for an ADOPT first (`freezegun`, `time-machine`)
     before hand-rolling one. Record the choice; a one-line pytest fixture may well beat both, and
     "simplest thing that fully solves it" wins [[best-not-defensible]].

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
    a. `PYTHONPATH=src python3 -m charon.cli gate` is GREEN.
    b. The spend-limit tests pass with the clock forced to a DIFFERENT month than "now" — prove it
       by running under an injected/frozen clock set to e.g. 2027-03. A fix that only passes
       because it is currently 2026-08 has not fixed anything.
    c. They pass under a non-UTC timezone (`TZ=Pacific/Kiritimati` and `TZ=Etc/GMT+12` — the two
       extremes will straddle a date boundary).
    d. Report the sweep results: every ambient-coupled test found, fixed or ticketed.

D&S — Deps & Sequence:
  - Depends on: nothing. Do it FIRST — the product `gate` is a REQUIRED check and is RED, so every
    product land (including GATE 2's ADR-0021) is blocked until this clears.
