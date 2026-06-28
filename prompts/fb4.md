Fix the engine concurrency/fencing defects found by the 2026-06-27 fragility audit
(THEME 7). These are in MERGED product code (E1's claim.py, E2's scheduler.py) and they
undermine the exact "never two live holders" guarantee the fence exists for. Read
docs/adr/0010-native-work-engine-substrate.md (D2 claim+scheduler, the fence choke-point),
docs/DECISIONS.md (D008, D009), and docs/review-log/E1.md + E2.md FIRST.

Each fix needs a PROVEN-RED test (failing before, passing after). Keep the gate green.

1. **Reclaim two-holder race [HIGH] — `engine/claim.py` (~the reclaim path, ~L200-211).**
   Reclaim does `os.unlink(path)` then `_create_exclusive()` with NO lock and NO
   re-validation between the staleness read (`_is_live`) and the unlink. Two reclaimers
   that both read the same stale record each become a live holder on a distinct worktree —
   violating the docstring guarantee. FIX: make test-and-set atomic — either a per-unit
   lock around unlink+create, or CAS via `os.replace(stale -> tmp)` and proceed only if the
   record still matches what was read; re-validate staleness immediately before unlink.
   TEST: two concurrent reclaims of one stale claim → exactly one wins, the other gets
   StaleReclaim/ClaimContended (never two holders).

2. **Disposition.RETRY is dead — `engine/scheduler.py` (~L128-130).**
   The runner calls `Ledger.create`, which raises if `ledger.json` already exists, so every
   RETRY re-fails at ledger creation and loops to the attempt cap; `self._attempts` never
   resets across `drain()`. FIX: create-or-load the ledger in the runner; scope/reset
   `_attempts` per drain. TEST: a unit that fails once then succeeds on retry actually lands.

3. **Capacity slot leak + non-fresh worktree — `engine/scheduler.py` (~L292-304).**
   The claim path catches only `ClaimContended`; any other exception (worktree factory
   mkdir/init, StaleReclaim, BoardError) propagates WITHOUT releasing the capacity slot
   acquired just before, and tears down the whole drain. FIX: try/finally with a `launched`
   flag so the slot is always released on a non-launch; make the default worktree factory
   unique per attempt. TEST: a claim that raises post-acquire releases the slot and the
   drain continues.

4. **Stale-epoch release tears down drain — `engine/scheduler.py` (~L335-339).**
   In `_settle`, a `StaleReclaim` from `release_claim` propagates out of the `for fut in
   done` loop, aborting settlement of in-flight siblings (left CLAIMED). The exact
   double-exec case the fence detects crashes instead of logging-and-skipping. FIX: catch
   StaleReclaim, mark the unit superseded, do NOT advance, continue the loop. TEST: one
   unit's stale release does not abort settlement of its siblings.

CONSTRAINTS: own ONLY engine/claim.py, engine/scheduler.py, tests/test_claim.py,
tests/test_scheduler.py — nothing else. Preserve all existing passing tests and public
behavior; these are surgical correctness fixes, not redesigns. Do NOT introduce a second
lock subsystem or a heartbeat/remote-lease (D009). Stdlib-only core. Gate green every commit
(pytest, ruff, mypy src tests, check_boundary, check_version). Write your review note as
docs/review-log/FB4.md. Conventional commits. Open a DRAFT PR base=master; do NOT merge.
