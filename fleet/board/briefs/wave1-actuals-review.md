# BRIEF — ADVERSARIAL REVIEW: ACTUALS-LEDGER (Wave 1)

ROLE: Independent adversarial reviewer. REFUTE correctness — assume the ranker is wrong until proven right. READ-ONLY. Write ONE findings file. No code, no commit, no push.

## WHAT TO REVIEW
The branch `actuals-ledger-wave1` in THIS working dir. Run:
`git diff master..HEAD` and `git log master..HEAD`.
New files: `src/charon/capability/actuals.py`, `src/charon/capability/scorecard.py`, `tests/test_actuals_ledger.py`. This is the REAL-OUTCOMES ranker with a freeze-ring LKG (last-known-good). It replaces the discredited synthetic benchmark as the ranking brain — correctness of the ranking signal matters.

## ATTACK CHECKLIST (find the failure, don't rubber-stamp)
1. **No fabrication:** does the score derive from REAL recorded outcomes, or is there any stubbed/constant/synthetic signal feeding the rank? (Recall: synthetic S0-S6 benchmark was rejected as a ranker.)
2. **Freeze-ring / LKG correctness:** when outcomes are missing/insufficient, does it correctly fall back to last-known-good rather than emit a garbage or zeroed rank? Construct an input (empty ledger, single sample, all-failures) that produces a wrong/unstable ranking.
3. **Monotonicity / determinism:** same inputs → same ranking? Any ordering that depends on dict iteration, unseeded randomness, or float ties resolving inconsistently?
4. **Ledger integrity:** can a bad/partial write corrupt the scorecard? Concurrency on the ledger?
5. **Tests fail-on-revert:** does `tests/test_actuals_ledger.py` turn RED if the ranker/LKG logic is reverted or neutered? Name any test that passes regardless.
6. **Blast radius:** who consumes this scorecard? Does an empty/cold-start ledger degrade gracefully for gateway routing / ticket-assignment?

## DELIVERABLE — write ONE file: `/home/stack/charon-private/fleet/reviews/ACTUALS-REVIEW.md`
- VERDICT: SAFE-TO-MERGE / MERGE-WITH-FIXES / DO-NOT-MERGE + confidence.
- Each finding: file:line, concrete failing input/scenario, severity.
- Explicitly answer no-fabrication and fail-on-revert (yes/no + evidence).
Tight, evidence-cited, no fluff.

## LAST STEP (required)
Print the file path. Do NOT commit, push, or edit anything else.
