# DECOMPOSE-MODEL-WIRING — review/decision note (per-ticket fragment)

## Ticket
DECOMPOSE-MODEL-WIRING (tier: frontier, difficulty: 4, work_class: greenfield-feature)

## What landed
Wired `CHARON_DECOMPOSE_PLANNER_MODEL` env override + tier-`"high"` preference into
`_select_planner_model` (`src/charon/decompose_planner.py`), and
`CHARON_DECOMPOSE_WORKER_MODEL` env override + tier-`"high"` sort-to-front into
`recommend_tiers` (`src/charon/recommend.py`). Added fail-on-revert tests in
`tests/test_decompose_planner.py` and `tests/test_recommend.py`.

## Design decisions
- **Preserved the SG-never-Anthropic guard** in `_select_planner_model`. The plan's
  literal §3.A snippet did not include the anthropic/claude-skip filter, but the
  current code at `decompose_planner.py:380` has a HARD RULE (per docstring +
  `test_planner_never_selects_anthropic`) that the planner must NEVER select Claude.
  The pin/tier ordering is applied AFTER the detain/anthropic filter so the guard is
  preserved untouched. The plan's "behavior unchanged fallthrough" language was read
  to mean: keep all existing filters, add pin/tier preference in front of the
  remaining candidates.
- **Sort copy, don't mutate caller's list** in `recommend_tiers`. The plan's snippet
  mutated `trusted` in place; I wrapped it with `list(_find_trusted_models(...))` so
  any other caller of the helper can't be surprised by sort-order side effects. This
  is a one-line wrap, no signature change.
- **Naming collision check (plan §5)**: confirmed `CHARON_DECOMPOSE_PLANNER_MODEL`
  and `CHARON_DECOMPOSE_WORKER_MODEL` are distinct from `CHARON_REVIEW_MODEL` (the
  outcome-reviewer role in `src/charon/adapters/review.py:11`). No code change needed
  there.

## Verification
- `PYTHONPATH=src python3 -m pytest tests/test_decompose_planner.py
  tests/test_recommend.py tests/test_decompose_surface.py -q` → 35 passed.
- Full `PYTHONPATH=src python3 -m pytest -q` → 1730 passed, 1 xfailed, 1 xpassed.
- `ruff check` → pre-existing errors only in `tools/_vendor/`, unrelated to this
  ticket (verified by `git stash` + `ruff check` reproducing the same 5 errors on
  master).
- `mypy src tests` → Success: no issues found in 237 source files.
- `python3 tools/check_boundary.py src` → OK.
- `python3 tools/check_version.py` → pre-existing local editable metadata drift,
  unrelated to this ticket (reproduces on master).
- `PYTHONPATH=src python3 -m charon.cli gate` → all checks passed.
- **Fail-on-revert proven**: stashed only `src/charon/decompose_planner.py` and
  `src/charon/recommend.py` (kept the new tests), re-ran the four new tests → all 4
  RED with clear assertions (`assert 'other-model' == 'pinned-model'`,
  `assert calls[0] == 'pinned-worker'`, etc.). Stash pop restored GREEN.

## Scope self-check
`git diff --name-only master...HEAD` is empty (nothing committed yet at this point),
working-tree diff is exactly 4 files, all in `owns:`:
- `src/charon/decompose_planner.py` ✓
- `src/charon/recommend.py` ✓
- `tests/test_decompose_planner.py` ✓
- `tests/test_recommend.py` ✓

`src/charon/decompose_surface.py` is in `owns:` for sequencing only — untouched by
this diff, as the ticket's `serial_justified` note promised.

## Files added
- `docs/review-log/DECOMPOSE-MODEL-WIRING.md` (this file)
