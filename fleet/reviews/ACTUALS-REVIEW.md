# ADVERSARIAL REVIEW — ACTUALS-LEDGER (Wave 1)

**Branch:** `actuals-ledger-wave1` (commit `6d7ec5f`)
**Reviewer:** ki-adi-mundi (READ-ONLY, no code changes)
**Date:** 2026-07-10
**Scope:** `src/charon/capability/actuals.py`, `src/charon/capability/scorecard.py`, `tests/test_actuals_ledger.py`, `src/charon/capability/__init__.py`

---

## VERDICT: MERGE-WITH-FIXES — confidence: HIGH

The scaffold is clean, well-structured, and the gate passes (12/12 tests green, ruff/mypy clean, full suite 1379 passed). The append-only ledger and freeze-ring store are genuinely sound at the storage layer. However, two correctness bugs in the freeze-ring LKG logic undermine the ticket's stated purpose, and one crash bug makes the reader unsafe against corrupted pointer files. The first finding below is architectural — it means the "last-known-good" guarantee the module advertises does not actually hold.

---

## ATTACK CHECKLIST ANSWERS

### 1. No fabrication — YES (no synthetic signal feeds the rank)

The brief asks whether the score derives from REAL recorded outcomes. In **this branch**, there is no score computation at all — `ScorecardRow.score` is a caller-supplied float field, and `ActualsLedger` stores raw byproduct columns (run_result, packet_parses, gate_pass, etc.). No stubbed constants, no synthetic S0-S6 benchmark, no heuristic ranker feeds into these modules. The `recommend.py` heuristic ranker (`_heuristic_rank`) and `router.py` static policy are pre-existing and **not wired** to the capability sub-package.

Evidence: `grep -rn 'capability' src/charon/` returns matches only in `capability/` and unrelated `router.py:71` / `recommend.py:97` comments. No consumer imports `ActualsLedger` or `ScorecardStore`. This is pure scaffold — the ranker brain does not yet exist. No fabrication concern for Wave 1.

### 2. Freeze-ring / LKG correctness — NO (LKG is broken by design)

**This is the headline finding.** The freeze-ring does not implement a last-known-good. See Finding F1 below.

### 3. Monotonicity / determinism — YES (clean)

Reads are deterministic: `read_latest()` performs no dict-iteration over unordered collections (rows are a `list`), no randomness, no unseeded operations. `read()` on the ledger iterates `splitlines()` in file order. Float scores are stored and compared by equality but no tie-breaking logic exists that could resolve inconsistently. No nondeterminism found.

### 4. Ledger integrity — PARTIAL (crash-safe on torn trailing line, drops data on mid-file corruption)

See Finding F3. The ledger handles a torn **trailing** line correctly (skips it), but a corrupt line **in the middle** causes `read()` to `break`, silently dropping all valid rows after it — including ones written *after* the corruption was injected. There is no concurrency control (no file lock, no advisory lock) but `append()` uses `fsync` and is append-only, which is acceptable for a single-writer model.

### 5. Tests fail-on-revert — PARTIAL (see Finding F4)

The headline FAIL-ON-REVERT test (`test_fail_on_revert_corrupt_latest_falls_back_to_lkg`) **does** go red if the LKG fallback in `read_latest()` is removed. Verified: the test corrupts the latest artifact file and asserts `read_latest()` returns seq=1 (LKG) instead of None. If the fallback scan were deleted, `read_latest()` would return None and the `assert now_loaded is not None` would fail.

However, the test only covers the **artifact-corruption** path. It does NOT cover the **pointer-corruption** path where LKG always points at the same seq as latest (Finding F1), and one test (`test_scorecard_latest_seq_is_incrementing`) actively **asserts the buggy behavior** (`lkg_seq() == latest_seq() == 3`) as correct. See Finding F4.

### 6. Blast radius — CONTAINED (no consumers)

`grep` confirms zero imports of `capability` outside the sub-package. The scorecard is inert — no gateway routing, no ticket assignment, no CLI wiring reads from it. Cold-start (`read_latest()` on empty store) returns `None`, which is the correct graceful degradation for an unwired consumer. The brief's concern about "degrading gracefully for gateway routing / ticket-assignment" is not answerable because no such consumer exists yet. Blast radius is zero for Wave 1.

---

## FINDINGS

### F1 — CRITICAL: LKG pointer is always set to the SAME seq as latest — there is no last-known-good

**File:** `src/charon/capability/scorecard.py:103-114`
**Severity:** CRITICAL (defeats the ticket's stated purpose)

`freeze()` writes both pointers to the same value:
```python
self._write_pointer(LATEST_FILENAME, seq_str)   # line 112
self._write_pointer(LKG_FILENAME, seq_str)      # line 113 — SAME seq_str
```

The docstring on `freeze()` (line 104) says "update latest + lkg pointers" and the module docstring (line 5) says "falls back to the last-known-good." But `lkg` is always identical to `latest` — it is never the *previous* good artifact. A true LKG would point to the **prior** frozen artifact (seq N-1 when latest is seq N), so that corrupting the latest artifact naturally falls back to a known-good predecessor.

**Concrete failing scenario:**
1. Freeze seq=1 (score=0.5). Both `latest` and `lkg` → `0000001`.
2. Freeze seq=2 (score=0.9). Both `latest` and `lkg` → `0000002`.
3. Corrupt the seq=2 artifact file.

Expected behavior: `read_latest()` returns seq=1 via LKG pointer → trivially correct, O(1).
Actual behavior: LKG pointer points at `0000002` (the corrupt file), so `read_latest()` reads it, gets None, then falls into the backward-scan (line 138-142) which walks from `lkg_int - 1 = 1` downward and finds seq=1. The **backward scan rescues the broken LKG pointer** — but this is an accidental save, not the designed mechanism. If the LKG pointer were set correctly to `0000001` at freeze time, no scan would be needed.

**Why this matters:** The backward scan (lines 139-142) is O(n) and only exists because the LKG pointer is broken. The comment on line 137 says "Scan backward from LKG-1 until we find a readable artifact" — but if LKG were truly the last-known-good, LKG itself would be readable and the scan would be dead code. The entire LKG fallback mechanism as designed is a no-op masked by a linear scan.

** reproduced empirically:** `lkg ptr == latest ptr == '0000002'` after freezing seq 1 then seq 2.

---

### F2 — HIGH: Non-numeric LKG pointer crashes `read_latest()` with uncaught `ValueError`

**File:** `src/charon/capability/scorecard.py:138`
**Severity:** HIGH (unhandled crash on corrupted pointer file)

```python
lkg_int = int(lkg)   # line 138 — crashes if lkg pointer contains non-numeric text
```

`_read_pointer()` (line 176) returns the raw string content of the pointer file. If the LKG pointer file is corrupted to contain non-numeric text (e.g. garbage, empty, or a partial write), `int(lkg)` raises `ValueError` which is **not caught** by any `try/except` in the reader.

**Concrete failing scenario:**
1. Freeze seq=1 and seq=2 (both valid).
2. Corrupt the `lkg` pointer file to contain `"garbage"` (e.g. a partial write, disk error, or manual tampering).
3. Call `read_latest()` → **`ValueError: invalid literal for int() with base 10: 'garbage'`** propagates to the caller.

Note: the `latest` pointer has the same issue but is accidentally saved by a guard — `_read_artifact()` returns None for a non-numeric seq (no matching file), so `read_latest()` falls through to the LKG path. But once it reaches the LKG path and the LKG pointer is also non-numeric, line 138 crashes.

The existing test `test_scorecard_corrupt_pointer_file` (line 230) claims to test corrupt pointer files, but it only corrupts the **latest** pointer (to the string `"not-a-number\n"`), leaving the LKG pointer intact. It does NOT test a corrupted LKG pointer.

** reproduced empirically:** `lkg=garbage → ValueError: invalid literal for int() with base 10: 'garbage'`

**Same bug in `latest_seq()` and `lkg_seq()`** (lines 156, 162): both call `int(raw)` on the raw pointer string with no guard. A non-numeric pointer crashes these methods too.

---

### F3 — MEDIUM: `read()` breaks on first corrupt mid-file line, silently dropping all valid rows after it

**File:** `src/charon/capability/actuals.py:100-101`
**Severity:** MEDIUM (silent data loss)

```python
except json.JSONDecodeError:
    break    # line 101 — stops reading at first corrupt line
```

The docstring (line 90) says "a torn trailing line is skipped, not misread." This is true for a torn **trailing** line. But a corrupt line **anywhere in the middle** of the JSONL file causes `read()` to `break` and return only the rows before it — silently dropping every valid row after the corruption, including rows written later by subsequent successful appends.

**Concrete failing scenario:**
1. Append row m1 (valid).
2. Append row m2 (valid).
3. A corrupt line is injected at position 3 (e.g. a partial write that was never completed, then the process restarted and appended cleanly).
4. Append row m3 (valid).
5. `read()` returns `[m1, m2]` — m3 is silently lost, with no error.

** reproduced empirically:** `rows read: 2`, `m3 (valid, AFTER corrupt line) is LOST: True`

**Impact:** A single corrupt line poisons all downstream data. The ledger is append-only, so this is not a torn-write-during-crash scenario (which produces a trailing bad line). It's a "one bad line in the middle silently truncates history" scenario. The fix is to `continue` instead of `break`, or to use a skip-and-warn approach.

---

### F4 — MEDIUM: Test suite enshrines the LKG bug as correct behavior

**File:** `tests/test_actuals_ledger.py:138-148`
**Severity:** MEDIUM (test encodes bug, blocks future fix)

```python
def test_scorecard_latest_seq_is_incrementing(tmp_path: Path) -> None:
    ...
    assert store.latest_seq() == 3       # line 143 — correct
    assert store.lkg_seq() == 3          # line 143 — WRONG: LKG should be < latest
```

This test asserts that `lkg_seq() == latest_seq() == 3` after freezing seqs 1, 2, 3. A correct last-known-good implementation would have `lkg_seq() == 2` (the prior good freeze) when `latest_seq() == 3`. The test **encodes the F1 bug as the expected behavior**, meaning a future developer who fixes the LKG pointer to lag behind latest will see this test go red and may "fix" it by reverting the actual fix.

Additionally, no test covers thescenario where both the latest artifact is corrupt AND the LKG pointer points at the latest (the F1 scenario). The only FAIL-ON-REVERT test (`test_fail_on_revert_corrupt_latest_falls_back_to_lkg`) corrupts the **artifact file** while leaving **both pointers intact** — it never tests a scenario where the LKG pointer itself is stale or mis-pointed.

**Tests that pass regardless of the ranker/LKG logic:** No test would pass regardless of the core logic — the tests are specific. But `test_scorecard_latest_seq_is_incrementing` passes *because* the LKG is broken, not despite it. This is the inverse of a fail-on-revert test: it fails-on-fix.

---

### F5 — LOW: `bool()` coercion on string values silently converts `"false"` → `True`

**File:** `src/charon/capability/actuals.py:59, 60`
**Severity:** LOW (requires upstream malformed input)

```python
fail_on_revert_pass=bool(d.get("fail_on_revert_pass", False)),   # line 59
gate_pass=bool(d.get("gate_pass", False)),                       # line 60
```

`bool("false")` evaluates to `True` in Python (non-empty string). If the ledger file ever contains a JSON line where these boolean fields are stored as the string `"false"` instead of the JSON boolean `false`, `from_dict()` will read them as `True` — silently flipping a failed gate into a pass.

** reproduced empirically:** `fail_on_revert_pass stored as string "false" -> bool: True`, `gate_pass stored as string "false" -> bool: True`

**Mitigating factor:** The `to_dict()` method (lines 34-50) always writes actual Python booleans, so well-formed internal writes are fine. This only triggers on externally-injected or hand-edited malformed JSON. The brief asks "can a bad/partial write corrupt the scorecard?" — this is a narrow instance where a *bad external write* (not a torn write) produces a *silently wrong* boolean. Low severity because the write path is controlled, but worth a defense-in-depth guard.

---

### F6 — LOW: No concurrency control on `freeze()` — concurrent writers can pick the same seq

**File:** `src/charon/capability/scorecard.py:103-114`
**Severity:** LOW (Wave 1 is single-writer; risk materializes in Wave 2)

`freeze()` does not auto-increment `seq` from `latest_seq()` — the caller supplies an arbitrary seq. Two concurrent freeze processes that both read `latest_seq()` and both choose `latest + 1` will write to the same artifact path (`scorecard.0000003.json`) and clobber each other's pointer updates. The atomic rename (line 110) protects the artifact file itself, but the pointer updates (lines 112-113) are not atomic relative to each other or to a concurrent freeze.

The tmp-file suffix uses `os.getpid()` (line 108), which prevents tmp-file collisions but not seq-selection races. There is no file lock, advisory lock, or CAS on the pointer.

**Impact for Wave 1:** None — single-writer. **Risk for Wave 2+:** HIGH if a cron job and a manual trigger can freeze simultaneously. The ticket should document this as a known limitation or add a flock.

---

## SUMMARY TABLE

| ID | Severity | File:Line | Issue |
|---|---|---|---|
| F1 | **CRITICAL** | `scorecard.py:113` | LKG pointer set to same seq as latest — no actual last-known-good |
| F2 | **HIGH** | `scorecard.py:138` | Non-numeric LKG pointer crashes `read_latest()` (uncaught `ValueError`) |
| F3 | **MEDIUM** | `actuals.py:101` | `read()` breaks on mid-file corrupt line, drops all valid rows after it |
| F4 | **MEDIUM** | `test_actuals_ledger.py:143` | Test asserts `lkg_seq() == latest_seq()`, encoding the F1 bug as correct |
| F5 | **LOW** | `actuals.py:59-60` | `bool("false")` → `True` on string-coerced boolean fields |
| F6 | **LOW** | `scorecard.py:103` | No seq-selection lock; concurrent freeze can clobber (Wave 2 risk) |

---

## EXPLICIT ANSWERS (per brief)

**No fabrication — YES, no synthetic signal.** `ScorecardRow.score` is caller-supplied; `ActualRow` stores raw deterministic byproducts. No constants, no stubs, no synthetic benchmark feeds into these modules. The ranker brain does not exist in this branch — it is pure storage scaffold.

**Fail-on-revert — PARTIAL.** The named test (`test_fail_on_revert_corrupt_latest_falls_back_to_lkg`) DOES go red if the LKG fallback scan is removed. Verified. BUT: the test only covers artifact-file corruption, not pointer corruption; `test_scorecard_latest_seq_is_incrementing` actively encodes the F1 bug; and no test catches the F2 crash on non-numeric LKG pointer. The fail-on-revert guarantee holds for the one tested path but fails for the untested paths.

---

*End of review.*
