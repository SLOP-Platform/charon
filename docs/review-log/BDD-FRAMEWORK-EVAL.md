# BDD-FRAMEWORK-EVAL review notes

## Verdict
**DO NOT ADOPT.** Plain pytest with disciplined given/when/then naming and docstrings wins
over pytest-bdd, behave, and Cucumber. The `.feature` gherkin file is a second artifact that
must be kept in sync — in an agent-driven rig, this is a work multiplier. The null hypothesis
delivers equivalent legibility at zero new-dependency cost.

## Execution
- pytest-bdd 8.1.0: 11 tests across 6 feature files, all passing (Scenario Outlines, step
  reuse via conftest, fixture composition with session scope, tags/markers, xdist -n 2, gherkin
  drift demo, failure-legibility comparison)
- behave 1.2.6: 4 scenarios, 16 steps passing
- Null hypothesis (plain pytest): 8 tests, all passing — given/when/then in docstrings,
  `@pytest.mark.parametrize` for tabular cases
- All tests in scratch venv at `/tmp/bdd-eval/`

## Key findings
- **Work multiplier confirmed:** Every behaviour change requires updating TWO artifacts
  (`.feature` + `.py`) vs ONE with plain pytest.
- **Step-collision is runtime-only:** Undefined steps fail at collection time, not lint time.
  Ambiguous steps (two definitions for same text) resolve silently to first-discovered.
- **Failure legibility is IDENTICAL:** BDD assertion output matches plain pytest assertion
  output character-for-character. The claimed reporting benefit does not materialise.
- **Gherkin drift invisible to accept gate:** accept runs `pytest -q` and checks exit 0.
  A drifted gherkin (text unchanged, code changed) still passes the gate.
- **accept:-gate integration confirmed:** `acceptance.py:49-61` runs `subprocess.run(cmd,
  shell=True, timeout=600)` and checks `returncode == 0`. Both pytest-bdd and plain pytest
  integrate for free.
- **Keystone branch absent:** `chore/remove-stdlib-only-prohibition` @ `ca7d046` does not
  exist in keystone checkout. No automated gate enforces the stdlib-only posture.

## Registry rows
Appended in separate earlier commit (e99d967): pytest-bdd, behave, Cucumber, Hypothesis
(cross-referenced to HYPOTHESIS-FAILOVER-EVAL, not duplicated).

## Files changed
- `fleet/state/BDD-FRAMEWORK-EVAL.md` — full deliverable
- `docs/review-log/BDD-FRAMEWORK-EVAL.md` — this fragment
- `fleet/state/EVAL-REGISTRY.md` — 4 rows appended (separate prior commit)
