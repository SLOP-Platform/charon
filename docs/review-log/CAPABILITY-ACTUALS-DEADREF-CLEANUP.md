# CAPABILITY-ACTUALS-DEADREF-CLEANUP review

Per-ticket fragment (CAPABILITY-ACTUALS-DEADREF-CLEANUP). Companion to
`DEDUP-ACTUALS-DELETE.md` (PR #160), which deleted the actuals module
itself but left three surviving stale references that this ticket removes.

## Context

PR #160 (DEDUP-ACTUALS-DELETE, merged 2026-07-15) deleted
`src/charon/capability/actuals.py` (the `ActualsLedger` / `ActualRow`
module) and removed the `:54` calibration-TODO comment in
`decompose_sizing.py` that named `capability.actuals.ActualsLedger` as a
still-pending source. It left three downstream stale references behind
(this ticket's work):

1. `src/charon/decompose_sizing.py:32` — module docstring still named
   ``capability.actuals`` / ``wall_clock_ms`` as the calibration source.
2. `src/charon/decompose_sizing.py:90` — `Overhead` dataclass docstring
   said "calibrate from the actuals ledger once enough rows exist" —
   same dead pointer, lower-case prose form.
3. `tools/check_inert_code.py:13` — own docstring cited
   ``capability/actuals.py::ActualsLedger`` as a worked example of a
   hand-rolled-audit find.
4. `tools/inert-code-disposition.json:14,18` — two whitelist entries
   for `charon.capability.actuals.ActualRow` /
   `charon.capability.actuals.ActualsLedger` that now name a module
   that doesn't exist (the JSON would never be cleaned by the detector
   itself, since dead symbols can no longer be flagged after deletion).

## Changes

1. **EDITED** `src/charon/decompose_sizing.py:32` — module docstring no
   longer names the dead `capability.actuals` module. Reworded to
   "calibration against accumulated real-run data (no dedicated ledger
   module reads from this layer — it stays network/clock-free, callers
   feed calibrated values via kwargs or env)".
2. **EDITED** `src/charon/decompose_sizing.py:90` — `Overhead` dataclass
   docstring's "calibrate from the actuals ledger" lowered to "calibrate
   against accumulated real-run data" (the dead module name is no longer
   the calibration source).
3. **EDITED** `tools/check_inert_code.py:13` — replaced the
   ``capability/actuals.py::ActualsLedger`` worked example with a pair of
   still-live "detector false positive" symbols the gate currently
   tracks (`charon.cache.format_stats` /
   `charon.engine.reconcile.FindingKind`).
4. **EDITED** `tools/inert-code-disposition.json` — deleted the
   `charon.capability.actuals.ActualRow` and
   `charon.capability.actuals.ActualsLedger` entries (now names a module
   that doesn't exist; would never be re-detected as dead, so they'd
   just lie there forever as a contradiction with `check_inert_code`'s
   "stale entries are safe to remove" advisory).
5. **EDITED** `tests/test_check_inert_code.py` — added
   `TestActualsDeadrefFailOnRevert` (a) scanning the three owned files
   for any of the three deadref strings (`capability.actuals` /
   `ActualsLedger` / `ActualRow`) and (b) asserting those three files
   still exist on disk so a future refactor/rename can't silently turn
   the grep into a no-op.

## Replacements

- The `wall_clock_ms` metric-name mention on the old `:32` line is
  intentionally **not** preserved in the new prose — the dead-pointer
  was the parenthetical as a whole ("from the actuals ledger
  (`capability.actuals`, `wall_clock_ms`)"). The metric itself is
  still the right per-chunk duration signal; callers feed calibrated
  `exec_rate` via kwargs / env, the module never reads a ledger.
- The `Overhead` docstring keeps "real-run data" as the calibration
  target — no invented replacement for the deleted module.
- The `check_inert_code.py` worked example swap is to symbols the gate
  actually tracks TODAY in the disposition file (verified at the time
  of this change: both `charon.cache.format_stats` and
  `charon.engine.reconcile.FindingKind` are present in
  `inert-code-disposition.json` as `keep-detector-false-positive-module-unreachable-cascade`).

## Accept verification

- `grep -nE "capability\.actuals|ActualsLedger|ActualRow" src/charon/decompose_sizing.py tools/check_inert_code.py tools/inert-code-disposition.json`
  → zero hits.
- `PYTHONPATH=src python3 -m pytest tests/test_check_inert_code.py -q`
  → 9 passed (the new `TestActualsDeadrefFailOnRevert` class adds 2
  tests, both green).
- `PYTHONPATH=src python3 tools/check_inert_code.py` → still green
  (the disposition file's removal of the two stale entries does NOT
  re-flag them, because deleted symbols can no longer be detected as
  dead).
- Full gate: `PYTHONPATH=src python3 -m pytest -q` → 1827+ passed (all
  pre-existing tests still pass; no behavior change).

## Out-of-scope (intentionally untouched)

- `decompose_effort.py`'s `TierActuals` / `ScorecardStore` live
  actuals-reading path is a different concept (per-tier average
  effort, not the now-deleted global ActualsLedger) — the
  `decompose_sizing.py` docstring previously named it as a calibration
  source but the path lives behind caller-supplied kwargs, not in this
  module. Not invented a replacement reference here (per ticket
  `accept:` "do not invent one").
- `src/charon/capability/__init__.py`'s `"""Capability tracking —
  actuals ledger and freeze-ring scorecard."""` docstring is a
  package-level overview, not a deadref to the deleted module — left
  alone.
- `docs/review-log/DEDUP-ACTUALS-DELETE.md` belongs to another
  ticket — not modified.
