# BRIEF — FIX CRITICAL SECURITY HOLES: BENCH-OOB-GRADING (Wave 1)

ROLE: Fix two CRITICAL security holes found by an adversarial review of the out-of-band grader. This grader runs as a dedicated `bench-grader` unix user and processes input from the MODEL UNDER TEST — untrusted. Isolation is the entire point. Work on branch `feat/bench-oob-grading` in THIS working dir (`/home/stack/charon-private/wt-grader`). Review ONLY the grader commit's files (`fleet/benchmark/grader-daemon.py`, `fleet/benchmark/graders/reds_replay.py`, `selftest/test_grader_daemon.py`).

## FINDINGS TO FIX (most-severe first)
### F1 — CRITICAL: path traversal in the `run` field → deletes any bench-grader-owned path
The `run` field (attacker-controlled, from the graded model) is used in a filesystem path without confinement, so `../` traversal can reach/delete paths outside the sandbox. FIX: confine every path derived from untrusted input to a fixed sandbox root — resolve with `os.path.realpath` and REJECT (hard error, no-op) anything that escapes the sandbox root. Never delete/write outside the sandbox.
### F2 — CRITICAL: shell injection via `run` field in `reds_replay._run_check`
The `run` field is passed to a shell (shell=True / string command), allowing arbitrary code execution as `bench-grader`. FIX: never invoke a shell on untrusted input — use `subprocess.run([...], shell=False)` with an argument list, or a strict whitelist of allowed check commands. No string interpolation into a shell.
### F5 — MEDIUM: reds-replay has no pre-fix (false-green) assertion
A curated red that is ALREADY green before the fix scores 100 (false positive). FIX: require the replay to assert the check FAILS at the pre-fix baseline (red) and PASSES post-fix; a curated case that is already green pre-fix must score 0 / be flagged invalid, not 100.

## REQUIRED TESTS (must FAIL on revert)
In `selftest/test_grader_daemon.py` add security tests that go RED if the fix is reverted:
1. A `run` field containing `../` traversal is REJECTED and touches nothing outside the sandbox root.
2. A `run` field containing shell metacharacters (`; rm -rf`, `$(...)`, backticks) does NOT execute a shell — the injection is neutralized (no side effect, no ACE).
3. A curated red that is already green pre-fix scores 0 / is flagged, not 100 (F5).

## VERIFY BEFORE COMMIT
`cd /home/stack/charon-private/wt-grader && PYTHONPATH=. python3 -m pytest fleet/benchmark/selftest/test_grader_daemon.py -q` (adjust path if needed). All green, and confirm the injection/traversal tests go RED when the guard is removed.

## LAST STEP (required)
Commit on `feat/bench-oob-grading`: `BENCH-OOB-GRADING: sandbox-confine run paths (F1) + kill shell injection (F2) + pre-fix false-green guard (F5) + security tests`.
Print the new commit SHA. Do NOT push. Do NOT merge. Do NOT touch REVIEW-PACKET.md or the two unrelated commits on this branch.
