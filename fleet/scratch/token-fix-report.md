# TOKEN-CAPTURE fix — report

## Files changed
- `fleet/benchmark/lib/charon_cost.py`
- `fleet/benchmark/lib/grade_state.py`
- `fleet/benchmark/bench.sh`
- `fleet/model-scorecard.sh`
- NEW: `fleet/benchmark/selftest/token_capture_selftest.py`

**Deliberately untouched:** `fleet/benchmark/run.sh` (its `grade_section()` already
hardcodes `cost_usd="-"` unconditionally — a pre-existing gap, out of this fix's
scope — so it gets `tokens_in`/`tokens_out` as `"-"` for free via
`model-scorecard.sh`'s new env-var default, with zero code changes needed there).
Also untouched: `model-scorecard.tsv` (no rows/header touched — it's being
actively appended to by the operator's live run right now, confirmed via `git diff`
showing +38 lines there that are NOT from this change), `benchmark/runs/**`,
`lib/tier_chart.py`, `cmd_render`'s awk in `model-scorecard.sh`.

## Path traced
1. `charon_cost.py::snapshot_cost_usd()` hit the gateway's `/charon/status`
   (or per-session `/charon/cost`) endpoint and read only `usage["cost_usd"]`,
   discarding `tokens_in`/`tokens_out` that were already in the same response body.
2. `grade_state.py::cmd_init()` snapshots cost at section start into `meta.json`
   (`cost_start_usd`); `cmd_record()` diffs it against a snapshot at grade time
   into `cost_usd`, written into `meta.json` and returned in the `record` JSON.
3. `bench.sh::do_grade()` reads `cost_usd` from that JSON (`jget`) and passes it
   as a positional arg to `model-scorecard.sh append`, which writes it as TSV
   column 11.

## What changed (diff summary)
- **`charon_cost.py`**: added `snapshot_usage() -> dict | None` returning
  `{"cost_usd", "tokens_in", "tokens_out"}` from the *same* HTTP response
  (works for both the global `/charon/status` body — nested under `"usage"` —
  and the per-session `/charon/cost` body, which is already flat). Missing/
  non-numeric fields become `None` per-field, never a crash. `snapshot_cost_usd()`
  is now a thin wrapper over it (identical return type/semantics, zero extra
  network calls). Added `int_delta_str(start, end)`, the integer-counter twin of
  the existing `delta_str()` (same `"-"` semantics: missing snapshot or counter
  went backwards → `"-"`).
- **`grade_state.py`**: `cmd_init()` now calls `snapshot_usage()` once, storing
  `tokens_in_start`/`tokens_out_start` in `meta.json` alongside the existing
  `cost_start_usd` (same value/meaning, unchanged). `cmd_record()` calls
  `snapshot_usage()` once (still exactly one network round-trip, same as
  before), derives `cost_usd` from it (unchanged behavior) plus new
  `tokens_in`/`tokens_out` deltas via `int_delta_str()`, stores
  `final_tokens_in`/`final_tokens_out` in `meta.json` on finalize, and adds
  `tokens_in`/`tokens_out` keys to the printed JSON — purely additive keys,
  existing readers (`jget` picks by key name) unaffected.
- **`bench.sh`**: `do_grade()` reads the two new JSON keys and passes them to
  `model-scorecard.sh append` via new env vars `CHARON_SCORECARD_TOKENS_IN` /
  `CHARON_SCORECARD_TOKENS_OUT` (not new positional args — `append`'s trailing
  `note` arg is variadic `"$*"` and already swallows all remaining argv, so
  there's no positional slot after it without an incompatible reshuffle).
- **`model-scorecard.sh`**: `cmd_append()` reads those two env vars (default
  `"-"` if unset — covers `run.sh`'s untouched call site and any pre-existing
  caller), validates them (non-negative int or `-`), and appends them as
  **new trailing TSV columns 14 and 15**, after `note` (column 13) — column
  order 1–13 is completely unchanged.

## Backward-compat verification (no real run/data touched)
Ran `python3 benchmark/selftest/token_capture_selftest.py` against scratch
copies only (temp dir + temp TSV, never the real `model-scorecard.tsv` or
`benchmark/runs/`):
- `snapshot_usage()` correctly parses a full response (cost+both tokens), a
  token-less response (simulating an older gateway/other provider — fields
  come back `None`, not a crash), and a garbage-token response (non-numeric /
  null → `None`); returns `None` cleanly when the gateway is unreachable.
  `snapshot_cost_usd()`'s value matches `snapshot_usage()["cost_usd"]` exactly
  (no drift from the refactor).
- `int_delta_str()`: normal delta, `None` start/end → `"-"`, counter went
  backwards → `"-"`, zero delta → `"0"`.
- `model-scorecard.sh append`: a legacy-style call (no token env vars set) still
  succeeds and now writes 15 columns with `"-","-"` trailing (never crashes);
  a new-style call (env vars set) writes the real integers in columns 14/15.
  Then hand-appended a genuine **13-column** legacy row (no trailing columns at
  all, simulating a row written before this fix) — `render` still exits 0 and
  produces correct output referencing the model.
- `tier_chart.py`: fed a mixed TSV (one true 13-column legacy row + two new
  15-column rows, one with real tokens and one with `"-","-"`) for the same
  model — `load_rows`/`bench_rows_for` (which slice `cols[:13]`) parse all
  three correctly, `note` is NOT shifted/corrupted by the extra trailing
  columns, and `render()` produces the expected tier chart with no exception.
- Re-ran the pre-existing `session_cost_selftest.py` — still PASS (no
  regression from the `snapshot_cost_usd()` refactor).
- `bash -n` on all 3 touched shell scripts; `python3 -m py_compile` on both
  touched Python files — all clean.
- Confirmed via `git diff --stat` that only the 4 intended files (+ the new
  selftest) changed; `model-scorecard.tsv`'s own diff (+38 lines) is from the
  operator's concurrent live run, not this change — it was never opened for
  writing by any of this fix's edits.
- Did NOT launch a real benchmark run (per instructions).

## Proposed commit message
```
feat(benchmark): capture tokens_in/tokens_out alongside cost_usd (TOKEN-CAPTURE)

charon_cost.snapshot_usage() reads tokens_in/tokens_out from the same
gateway response cost_usd already comes from (zero extra network calls);
grade_state.py threads the per-section token delta into meta.json and the
`record` JSON the same way cost_usd already flows. bench.sh passes the two
new fields to model-scorecard.sh via env vars (append's trailing `note` arg
is variadic and already swallows the rest of argv) which appends them as
new trailing TSV columns 14/15 - column order 1-13 (incl. `note`) is
unchanged, so every existing reader (tier_chart.py's cols[:13] slicing,
cmd_render's $1-$12 awk) keeps working on old 13-column rows and new
15-column ones alike. run.sh's pre-existing cost_usd="-" gap is left as-is;
it now gets tokens_in/tokens_out="-" for free via the same default.

Added selftest/token_capture_selftest.py (scratch-only, never touches the
real ledger/runs/ tree) covering: snapshot_usage() parsing of full/
token-less/garbage gateway responses; int_delta_str() delta semantics;
model-scorecard.sh append+render on a legacy no-token call, a new
with-token call, and a hand-written genuine 13-column legacy row side by
side; tier_chart.py tolerating the mixed column widths.
```
