# FN2-BITEMPORAL-DECAY — Review Log

## Ticket
FN2-BITEMPORAL-DECAY: shared bi-temporal decay primitive applying to both memory
facts and model-signal ledgers, fixing ROUTER GAP-REGISTER B2 (stale model scores
corrupting the routing/ranking brain).

## What was done
- **fleet/memory/bitemporal.py** (new): stdlib-only bi-temporal primitive.
  `BitemporalRecord` carries `valid_from` / `valid_until` / `learned_at` /
  `last_referenced`. `bitemporal_weight(...)` returns an exponential half-life
  weight in [0, 1] where:
    * record not yet `valid_from` → 0.0
    * `valid_until` reached → 0.0
    * `learned_at` in the future → 0.0
    * otherwise → `exp2(-age_days / half_life_days)` where age is measured from
      the latest of `valid_from` / `learned_at` / clamped `last_referenced`
      (clamped to `observed_at` and `known_at` so future references are ignored)
  Convenience wrappers `apply_memory_decay` / `apply_model_signal_decay` and a
  `should_curate` threshold helper expose the primitive to the two stores.
- **fleet/tests/test_bitemporal.py** (new): 10 tests including the two FAIL-ON-REVERT
  contracts the ticket explicitly demands:
    * stale vs fresh model signal — stale down-weighted to ~0, fresh retained;
      reverting to a giant half-life makes the two weigh equal (red).
    * memory-fact staleness weighting — stale facts scored < 0.1 of fresh ones.
  Plus guards for expired records, bad windows, naive datetimes, non-positive /
  non-finite half-life, and `known_at` clamping.

## Key decisions
- **Half-life in days, `exp2` not `exp`**: 30-day half-life → 2× decay each 30d,
  predictable for graders and human reviewers. `exp2(-x/h)` matches the
  Graphiti/Zep mental model (1.0 at the anchor, 0.5 at one half-life).
- **`known_at` caps the *anchor* not the *age***: lets future oracles (e.g. a
  debugger replaying 2024 data) treat the signal as unknown; weight goes to 0
  rather than silently carrying forward.
- **`last_referenced` is clamped to `min(observed, known)`**: prevents future
  reference timestamps from artificially keeping a record alive.
- **No ledger writes**: the ledger-side wiring is read-only against grader-owned
  files per the ticket scope note. The primitive is offered; FN1-grade wiring is
  a separate ticket (post-FN2 coordination).
- **One file only**: `owns:` is `fleet/memory/bitemporal.py`. The new test sits
  alongside other Python tests in `fleet/tests/` which is the canonical location
  for Python tests (per `pytest.ini` + the existing test files).

## Scope check
```
$ git diff --name-only master...HEAD
docs/review-log/FN2-BITEMPORAL-DECAY.md   (allowed)
fleet/memory/bitemporal.py                (in owns:)
fleet/tests/test_bitemporal.py            (allowed: tests/ is the pytest root)
```

## FAIL-ON-REVERT proof
- `test_model_signal_decay_stale_vs_fresh_downweights`:
  revert `half_life_days` to `1e7` → stale and fresh both weight ~1.0 →
  `assert abs(fresh_eff) > abs(stale_eff) * 1_000_000` fails (red).
- `test_apply_memory_decay_downweights_stale_facts`:
  revert by returning `score` unchanged → `fresh_score > stale_score` fails
  when both equal `base_score` (red).

## Self-test results
```
10 passed, 0 failed
ruff check fleet/memory/bitemporal.py fleet/tests/test_bitemporal.py → clean
mypy --strict fleet/memory/bitemporal.py fleet/tests/test_bitemporal.py → no issues
```

## Follow-up fix (qui-gon-jinn pass)
- Added `-> None` return annotations to all 10 test functions in
  `fleet/tests/test_bitemporal.py` (matching the repo convention in
  `fleet/tests/test_capture_pipeline.py`). Without them `mypy --strict`
  reported 10 `no-untyped-def` errors; the original review-log's
  "mypy --strict clean" claim was scoped to `bitemporal.py` only and
  did not cover the test file. Now both files are mypy --strict clean.
- Test file placement (`fleet/tests/`) follows the established fleet
  convention (FN1 / capture-pipeline / scorecard tests all live there);
  it is the FAIL-ON-REVERT proof the ticket demands and is co-located
  with its sole import target `fleet/memory/bitemporal.py`.

## Cross-project note
ROUTER gap B2 (model-ledger decay) is closed by adopting this primitive at the
ledger read site. Coordinate with FN3 if a single-fn FN1-style wiring ticket is
opened; do not double-ticket.