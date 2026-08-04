repo: charon
tier: economy
priority: 2
difficulty: 3
work_class: ci-infra
branch: feat/tool-enable-ratchet
owns: pyproject.toml, Makefile, .bandit-baseline.json
depends_on:
dep-kind:
work_class_note: ci-infra — D-004/D-005 enablement. Turns on tooling we already own so defects are
  caught mechanically instead of by luck. This is how the operator gets quality without reading code.
note: |
  D-004: TOOL-UTILIZATION-AUDIT measured ~20% of owned tool capability switched on, and its Top-5
  were approved 2026-08-01 and never started. This lands them, RATCHETED — bare enablement would
  have redded the gate on thousands of pre-existing findings and blocked every push.

  MEASURED, per tool (agent's numbers, manager-verified green):
    ruff           0 findings -> 5227 raw (198 src / 4998 tests / 31 tools across 217 files) -> 0 vs baseline
    mypy           0 -> 192 errors across 72 modules -> 0 vs baseline
    pytest-timeout none -> --timeout=60 (slowest real test measured at 7.03s)
    bandit         0 in CI -> 56 findings (3 HIGH, 1 MED, 52 LOW) on src/ -> 0 vs baseline
  Full `charon.cli gate` GREEN and full suite 2380 passed with all baselines in place.

  REAL BUG FIXED IN PASSING: `mypy_path` was nondeterministic, which had silently made the 3
  PRE-EXISTING mypy overrides no-ops. Pinned to `["src"]`. So mypy was even less enforced than
  0-of-14 suggested — three overrides were configured and doing nothing.

  ⚠ HONEST COVERAGE LIMIT — DO NOT DESCRIBE THIS AS "ruff/mypy ENFORCED" ⚠
  The baselines are per-FILE (`per-file-ignores`, 217 entries) and per-MODULE
  (`disable_error_code`, 72 blocks), NOT per-occurrence. Therefore:
    - a new violation of a rule that file did NOT already have  -> CAUGHT  (probe-verified)
    - a new violation of a rule ALREADY baselined in that file   -> NOT CAUGHT
  MANAGER-VERIFIED 2026-08-03, not taken on report: appending a fresh `BLE001` to
  `src/charon/__init__.py` (whose baseline is exactly `["BLE001"]`) leaves `ruff check` PASSING.
  The agent's probe used a scratch construct that also tripped an unbaselined rule (S110), so it
  did not isolate this case; isolating it exposed the hole.

  Consequence: the 4998 baselined findings in tests/ mean those rules are effectively unenforced
  in tests/ for the files that already carry them. This is the standard weakness of per-file
  baselines and is ACCEPTABLE AS STEP ONE (it strictly dominates 0 enabled), but it must not be
  reported as full enforcement.

  FOLLOW-UP (file separately): replace per-file ignores with a COUNT RATCHET — store per-rule
  counts and fail when any count increases. That catches new violations even inside already-baselined
  files, and the count monotonically declines as debt is paid. bandit already has the better shape
  (line/hash baseline via `-b`).

  bandit is deliberately NOT wired into the CI gate: ruff's S-rules cover the same ground
  (see src/charon/scanners.py). It is exposed as `make security` with `.bandit-baseline.json`.
  Judgement accepted, but note that with the S-rules baselined per-file, existing S findings are
  suppressed in BOTH tools — so the 3 HIGH-severity findings are recorded, not currently enforced.
  Triaging those 3 HIGHs is worth its own ticket.

  Probes that DID pass (new-violation-in-clean-file): ruff S404/S602/S110/BLE001/ARG001 caught;
  mypy no-any-return/unreachable/assignment caught; pytest-timeout killed a 120s sleep at 60.08s;
  bandit caught a new B324 weak-MD5.
