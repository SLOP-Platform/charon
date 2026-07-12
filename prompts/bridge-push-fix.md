# BRIEF — BRIDGE PUSH: FIX the 5 review defects (concurrency-critical)

An independent adversarial review found the earlier build BROKEN. You are fixing it. This is
concurrency-sensitive infra that will be adopted into SLOP — correctness over speed. Portable:
pure Python stdlib, no charon-only coupling.

## Where you are / safety
- You are in a git WORKTREE already checked out on branch `feat/bridge-push-debate` (HEAD 53cf4dd)
  of the session-bridge repo. Fix IN PLACE and commit on THIS branch. There is no remote — do NOT push/merge.
- The real daemon is LIVE elsewhere. Do NOT restart/kill/signal any `daemon.py` process and do NOT touch
  any live DB. ALL testing runs against a SCRATCH DB + spare port inside this worktree.

## READ FIRST (authoritative)
- `/home/stack/charon-private/fleet/state/overnight/BRIDGE-PUSH-REVIEW.md` — the 5 concrete defects (file:line, failure scenarios). Fix ALL of them.
- `/home/stack/charon-private/fleet/state/overnight/BRIDGE-PUSH-BUILD-REPORT.md` — the original build report.

## The crux defect (MUST fix — review proved 12/40 concurrent posts silently dropped)
Concurrent `thread_post` to ONE thread loses messages. Root cause:
1. **Non-atomic seq allocation** (`daemon.py:832`) — a read-modify-write of the per-thread seq counter races.
   Fix: allocate seq ATOMICALLY — a single SQL statement (e.g. `INSERT ... SELECT COALESCE(MAX(seq),0)+1 ... WHERE thread_id=?`) and/or a `BEGIN IMMEDIATE` transaction, so N concurrent posts get unique, contiguous, monotonic seq with NONE lost.
2. **Over-broad `IntegrityError` catch** (`daemon.py:843`) — a PRIMARY-KEY collision is being misread as an idempotency dedup and returned as `ok:True, deduplicated:True`. Fix: treat ONLY the idempotency-key UNIQUE violation as dedup (inspect the constraint/message); RE-RAISE every other IntegrityError. Never silently swallow.
Then fix the remaining defects from the review packet.

## Mandatory regression test (FAIL-ON-REVERT)
Add a concurrency test to `test_daemon.py`: M (>=20) threads, barrier-synced, each `thread_post` to ONE thread.
Assert: all M rows persisted; seq is a unique contiguous monotonic sequence 1..M; NONE returned a false
`deduplicated:True`. Reverting the seq-atomicity fix MUST make this test FAIL (verify that it does).

## Committed E2E artifact (so "E2E worked" is verifiable, not a claim)
Produce AND COMMIT a real transcript file `e2e_debate_transcript.txt` in the repo showing: the 2-critic
push debate (C1 posts → C2 pushed via bridge-watch → rebuttal → consensus) AND the concurrent-post stress
result (all M landed). Real captured output, not prose.

## LAST STEP (required)
- Full suite pipe-free: `python3 -m pytest test_daemon.py -q; echo "EXIT=$?"` → 0, including the new concurrency test.
- `git add -A && git commit` on `feat/bridge-push-debate`; report the SHA.
- Do NOT push. Do NOT merge. Do NOT restart the live daemon. (deliberate, separate line.)
- Write `/home/stack/charon-private/fleet/state/overnight/BRIDGE-PUSH-FIX-REPORT.md`: each of the 5 defects and
  how fixed (file:line), the concurrency-test REAL output (all M posts landed, unique seq), the committed E2E
  transcript path, pytest EXIT, and the new SHA. Note any defect you could NOT fix.
- Print `PACKET: fleet/state/overnight/BRIDGE-PUSH-FIX-REPORT.md` + an ≤8-line honest summary. Real outputs only — never a fabricated SUCCESS line.
