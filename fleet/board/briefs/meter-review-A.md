# BRIEF — ADVERSARIAL REVIEW (Reviewer A): METER-MODEL-PROVIDER money-path diff

ROLE: Independent adversarial reviewer. Your goal is to REFUTE correctness — assume the diff is wrong until proven right. READ-ONLY. Write ONE findings file. No code, no commit, no push.

## WHAT TO REVIEW
The branch `feat/meter-model-provider` in THIS working dir. Run:
`git diff master..HEAD` and `git log master..HEAD`.
This is MONEY-PATH: real per-(model,provider) cost metering replacing fabricated `est_cost`.

## ATTACK CHECKLIST (find the failure, don't rubber-stamp)
1. **Metering invariant:** on the identity/pass-through path, does the cost-total DELTA stay exactly 0
   (no double-count, no drift)? Construct an input where it wouldn't.
2. **No fabrication:** is cost derived from REAL usage (tokens × real price), not a stamped `est_cost`
   floor? Any path still writing fake cost?
3. **Credential shape:** are provider keys / secrets never logged or leaked into the meter record?
4. **Per-(model,provider) accuracy:** namespaced/aliased model ids attributed to the right provider?
   (recall the prior namespaced-id double-bill bug.) Off-by-one on which provider served the request?
5. **Tests fail-on-revert:** do the added tests actually EXERCISE the change — i.e. would they turn RED
   if the metering fix were reverted? A test that passes on the old code proves nothing. Name any that don't.
6. **Concurrency / partial-failure:** meter correctness under a failover mid-request or a streamed response.

## DELIVERABLE — write ONE file: `/home/stack/charon-private/fleet/reviews/METER-REVIEW-A.md`
- VERDICT: SAFE-TO-MERGE / MERGE-WITH-FIXES / DO-NOT-MERGE + confidence.
- Each finding: file:line, the concrete failing input/scenario, severity.
- Explicitly answer the metering-invariant and fail-on-revert checks (yes/no + evidence).
Tight, evidence-cited, no fluff.

## LAST STEP (required)
Print the file path. Do NOT commit, push, or edit anything else.
