# TSV-APPEND-UNIFY — review log

Date: 2026-07-15. Ticket: TSV-APPEND-UNIFY (parent DEDUP-GRAPHS-LEDGERS, filed by
DEDUP-ACTUALS-DELETE from fleet/state/TOOL-AUDIT-REDUNDANCY.md finding 6).

## Decision: unify by delegating Python -> shell (reverse of the audit's sketch)

Finding 6 offered two shapes: (a) shell delegates to `capability/auto_append.py`,
or (b) delete one impl. Landed a third that satisfies the same goal — ONE
validate+append implementation, two callers — but with the delegation running the
OTHER way: `model-scorecard.sh cmd_append` stays the single source of truth and
`auto_append.py` becomes a thin subprocess delegator. Reasons:

1. **cmd_append is the live path.** Every real call site (`benchmark/bench.sh:446`,
   the `sudo -u bench-grader … model-scorecard.sh append` seam in
   ADR-BENCH-OOB-GRADING, manual appends) already invokes the shell. Keeping the
   live impl in place is the minimum blast radius; `auto_append.py` had zero real
   callers (audit-confirmed), so rewriting IT risks nothing live.
2. **Shell -> Python delegation would break a test I don't own.**
   `fleet/benchmark/selftest/token_capture_selftest.py` (part 2) copies
   `model-scorecard.sh` ALONE into a temp dir and runs it there — a script that
   shells out to `$HERE/capability/auto_append.py` cannot resolve the helper from
   the copy. Verified: with reverse delegation the selftest still PASSES unmodified.
3. **The sudoers seam stays clean.** ADR-BENCH-OOB-GRADING password-gates the exact
   `model-scorecard.sh append` invocation; keeping validation+write inside that one
   whitelisted script avoids widening what the sudo rule effectively executes.

## What changed

- `fleet/model-scorecard.sh`: `TSV` is now `${CHARON_SCORECARD_TSV:-$HERE/model-scorecard.tsv}`
  (override exists for the Python delegation + hermetic tests; unset = real ledger,
  behavior unchanged). Comment marks cmd_append as THE single appender.
- `fleet/capability/auto_append.py`: dropped its full mirror of the shell validator
  (the "kept in lockstep only by comment discipline" duplicate); now builds
  argv/env, invokes `bash model-scorecard.sh append`, and maps `die` output back to
  `ValueError` (same messages, so `fleet/tests/test_auto_append.py`'s 75 cases pass
  unchanged). One transport guard remains — rejecting `""` for
  tokens_in/tokens_out/stage — because the `${VAR:-default}` env channel cannot
  distinguish empty from unset; that is an encoding guard, not a second field
  grammar.
- `fleet/capability/tests/test_tsv_append_unify.py` (new): shell and Python paths
  produce byte-identical rows; rejection surfaces through the wrapper with nothing
  written; a stubbed `SCORECARD_SH` proves the wrapper truly delegates (fails if an
  inline writer regrows).

## Audit-doc note (out of owns)

`fleet/state/TOOL-AUDIT-REDUNDANCY.md` is untracked rig state outside this
ticket's `owns:` — annotating finding 6 as resolved there is a RIG-side operator
step at merge; this change is the resolution itself (one implementation, two
callers, no comment-discipline sync left).

## Verification

- `PYTHONPATH=src python3 -m pytest -q` — 79 passed (75 baseline + 4 new).
- `ruff check` — 18 errors, all pre-existing, none in owned files; owned files clean.
- `mypy fleet/capability/auto_append.py fleet/capability/tests/test_tsv_append_unify.py` — clean.
- `python3 fleet/benchmark/selftest/token_capture_selftest.py` — PASS, unmodified.
- `bash -n fleet/model-scorecard.sh` — OK.
