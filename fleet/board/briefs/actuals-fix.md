# BRIEF — FIX ADJUDICATED DEFECTS: ACTUALS-LEDGER (Wave 1)

ROLE: Fix correctness defects found by an independent adversarial review of the actuals-ledger freeze-ring. Work on branch `actuals-ledger-wave1` in THIS working dir (`/home/stack/code/charon`). This is the real-outcomes ranking substrate — correctness of the last-known-good (LKG) guarantee is the whole point.

## THE DEFECTS (from review, most-severe first)
### F1 — CRITICAL: LKG is fake — pointer always equals latest
`freeze()` currently sets the LKG pointer to the SAME seq as latest on every write, so there is NO last-known-good to fall back to when the latest is bad/corrupt.
**Correct semantics:** the LKG pointer must advance to the new seq ONLY when the new scorecard is GOOD — i.e. it passed the gate / fail-on-revert (`gate_pass` AND `fail_on_revert_pass` true). If the new scorecard is NOT good, LKG stays pointing at the previous good seq. On a cold start with no good scorecard yet, LKG is unset (reader returns None, not garbage).
**Reader:** `read_latest()` returns the latest artifact if readable AND good; otherwise it falls back to the LKG seq (the last GOOD one), which must be a DIFFERENT seq than a bad latest.

### F2 — HIGH: non-numeric LKG pointer crashes `read_latest()`
A corrupted/non-numeric LKG pointer file raises an uncaught `ValueError`. Guard the parse: treat an unparseable pointer as "no LKG" (return None / skip fallback), never crash.

### F3 — MEDIUM: `read()` silently drops rows after a mid-file corrupt line
`read()` currently `break`s on the first corrupt line, dropping all valid rows AFTER it. Change to SKIP the corrupt line and continue (log/count it if there's a cheap way), so later valid rows are not lost. Keep the torn-trailing-line handling.

### F4 — MEDIUM: a test enshrines the F1 bug
`test_scorecard_latest_seq_is_incrementing` asserts `lkg_seq() == latest_seq()` as correct — that encodes the bug. Fix it to assert the CORRECT LKG semantics (LKG tracks the last GOOD seq, which diverges from latest when a bad scorecard is frozen).

## REQUIRED NEW/UPDATED TESTS (must FAIL on revert of the fix)
1. **Real-LKG fallback:** freeze a GOOD scorecard (seq=1), then freeze a BAD one (seq=2, gate_pass/fail_on_revert_pass false) OR corrupt the latest artifact; assert `read_latest()` returns the **seq=1 GOOD** scorecard — NOT seq=2 and NOT None. This must go RED if F1's fix is reverted (i.e. if LKG==latest).
2. **Non-numeric pointer guard (F2):** write a garbage LKG pointer; assert `read_latest()` returns gracefully (None or latest-good) and does NOT raise.
3. **Mid-file corruption (F3):** inject a corrupt line in the middle of the ledger; assert rows written AFTER it are still returned by `read()`.
Keep F5/F6 (bool-coercion, concurrency) OUT of scope — they are LOW / Wave-2; a one-line note in the module is fine but no behavior change required.

## VERIFY BEFORE COMMIT
`cd /home/stack/code/charon && PYTHONPATH=src python3 -m pytest tests/test_actuals_ledger.py -q`
All tests green. Then confirm the fail-on-revert guard actually bites: temporarily make LKG==latest again and confirm the new fallback test goes RED (then restore the fix). Report that you did this.

## LAST STEP (required)
Commit on `actuals-ledger-wave1` with message `ACTUALS-LEDGER: real last-known-good (F1) + pointer guard (F2) + mid-file-corruption skip (F3) + fix bug-enshrining test (F4)` and print the new commit SHA.
Do NOT push. Do NOT merge.
