# GATE-INTEGRITY-B — gate-coverage side

## Charge

Add three declared-but-unwired gates to `charon gate` so the unified gate
actually exercises the full set of enforcers declared in `tools/gates.json`.

## Decision (with rationale)

### 1. `render-review-log` runs in *generate* mode, not `--check`

The ticket spec said "MUST use `--check`; bare form mutates `docs/REVIEW-LOG.md`".
This was followed literally impossible in a fresh checkout: `docs/REVIEW-LOG.md`
is **gitignored** (see commit `56c2f28` — `fix(review-log): untrack generated
rollup; fragments are the source of truth`). The rollup is a generated artifact
from the canonical per-ticket fragments under `docs/review-log/*.md`.

Following `.github/workflows/ci.yml` lines 52-55 (which already calls the bare
form and comments explicitly: "docs/REVIEW-LOG.md is gitignored (generated);
`--check` would always fail on a fresh CI checkout"), I wired the bare form.
The "mutation" is an idempotent regeneration from the SoT fragments — no
arbitrary side effect. Documented inline in `gate_runner.py`.

The `--check` form remains available for developer-time validation but is not
CI-suitable for this repo.

### 2. `render-review-log` must run *before* `check-decisions`

D002 and D011 in `docs/DECISIONS.md` reference `REVIEW-LOG`. If the rollup file
doesn't exist, `tools/check_decisions.py --check` reports
`REVIEW-LOG: docs/REVIEW-LOG.md not found` and exits 1. So the order in
`CHECKS` is: `render-review-log` → `check-decisions`. This is recorded inline
in `gate_runner.py`.

### 3. `validate-board` and `charon-gate` stay excluded

Per the spec: `validate-board` is fleet-external (an enforcer living outside
this repo's working tree, in the sibling private rig checkout) and
`charon-gate` is self-referential (the gate cannot list itself as one of its
own sub-checks). Both stay declared in `tools/gates.json` but remain un-wired
in `gate_runner.py`. This is a documentation choice — the registry still
requires them, but the unified runner does not invoke them.

## Files changed

- `src/charon/gate_runner.py` — added `pytest`, `render-review-log`,
  `check-decisions` to `CHECKS`. Order: render-review-log before check-decisions
  so D002/D011 resolve. Excluded: `validate-board` (fleet-external),
  `charon-gate` (self-referential).
- `tools/check_gate_registry.py` — added `ci-infra` and `no-rig-import` to
  `ALL_DOMAINS` so the `gates.json` registry self-validator stops flagging the
  two gates that were already declared in the registry but missing from the
  domain set (silent drift; the registry's `extra` counter was non-fatal but
  the alignment is now canonical).

## Verification

- `PYTHONPATH=src python3 -m charon.cli gate` → GREEN; output shows all three
  newly-wired checks execute (`[pytest] OK`, `[render-review-log] OK`,
  `[check-decisions] OK`).
- `PYTHONPATH=src python3 -m pytest` → 1795 passed, 1 xfailed, 1 xpassed.
- `python3 tools/check_gate_registry.py` → OK, 17 gates, 17 domains covered
  (no `Unknown domains`, no `uncovered`).

## Dependencies

`depends_on: GATE-INTEGRITY-A`. A's deterministic inert scan is the
prerequisite for the full `charon gate` to be green — verified by running
`gate` post-A on this branch baseline: `[inert-code] OK` is already
deterministic in the current state, so the dependency is satisfied.

## Scope

Disjoint from A. No two-writer hazard. Only owned files modified:
- `src/charon/gate_runner.py`
- `tools/check_gate_registry.py`
- this fragment.
