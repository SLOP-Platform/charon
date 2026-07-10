# BRIEF — ADVERSARIAL REVIEW: BENCH-OOB-GRADING (Wave 1)

ROLE: Independent adversarial reviewer. REFUTE correctness — assume the grader is gameable/wrong until proven right. READ-ONLY. Write ONE findings file. No code, no commit, no push.

## WHAT TO REVIEW
The branch `feat/bench-oob-grading` in THIS working dir (a RIG worktree). Run:
`git show --stat f5fc2be` then `git diff master..HEAD -- REVIEW-PACKET.md fleet/benchmark/`.
REVIEW ONLY the grader commit `f5fc2be` (5 files: `fleet/benchmark/grader-daemon.py`, `graders/reds_replay.py`, `selftest/test_grader_daemon.py`, `RUN-BENCHMARK.md`, `REVIEW-PACKET.md`). IGNORE the two unrelated commits also on this branch (handoff-check + briefs) — they are out of scope.
This is the OUT-OF-BAND grader daemon (#26): grading must NOT be readable or self-gradeable by the model under test — that was the whole reason the prior in-band benchmark was invalidated.

## ATTACK CHECKLIST (find the failure, don't rubber-stamp)
1. **Isolation:** is the grader genuinely OUT-OF-BAND — the model under test cannot read the grading key, prompt, or expected answers, and cannot self-grade? Find any path where the graded artifact leaks the answer.
2. **No product import:** does anything under `fleet/benchmark/` import the Charon PRODUCT source (`src/charon/*`)? The RIG must not leak into the product and vice-versa. Grep the diff.
3. **Versioning:** is the scorecard artifact versioned so a stale/older grader output can't be silently mistaken for current?
4. **Reds-replay validity:** does `reds_replay.py` actually replay real reds and detect a revert (fail-on-revert), or can a no-op pass it?
5. **Tests fail-on-revert:** does `selftest/test_grader_daemon.py` turn RED if the grader logic is neutered? Name any that pass regardless.
6. **Gameability:** can a model score well without doing the work (grader-readable rubric, self-report trust, deterministic-answer leakage)?

## DELIVERABLE — write ONE file: `/home/stack/charon-private/fleet/reviews/GRADER-REVIEW.md`
- VERDICT: SAFE-TO-MERGE / MERGE-WITH-FIXES / DO-NOT-MERGE + confidence.
- Each finding: file:line, concrete failing scenario, severity.
- Explicitly answer isolation, no-product-import, and fail-on-revert (yes/no + evidence).
Tight, evidence-cited, no fluff.

## LAST STEP (required)
Print the file path. Do NOT commit, push, or edit anything else.
