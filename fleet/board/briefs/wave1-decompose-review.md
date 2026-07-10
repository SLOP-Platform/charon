# BRIEF — ADVERSARIAL REVIEW: GATEWAY-ROUTING-DECOMPOSE (Wave 1)

ROLE: Independent adversarial reviewer. REFUTE correctness — assume the refactor changed behavior until proven otherwise. READ-ONLY. Write ONE findings file. No code, no commit, no push.

## WHAT TO REVIEW
The branch `feat/gateway-routing-decompose` in THIS working dir. Run:
`git diff master..HEAD` and `git log master..HEAD`.
This extracts routing-policy logic OUT of the gateway into a new `src/charon/routing_policy/` package. It is a REFACTOR — the contract is BEHAVIOR-PRESERVING.

## ATTACK CHECKLIST (find the failure, don't rubber-stamp)
1. **Behavior preservation:** does any routing decision (spill, ordering, provider selection, failover ordering) change vs master? Construct an input where the extracted code returns a different route than the inline code did.
2. **Seam integrity:** re-exports / imports — is anything the gateway used now missing, shadowed, or imported from the wrong place? Import cycles between `routing_policy/` and `gateway.py`/`proxy.py`?
3. **Dead / duplicated logic:** did the old inline logic get deleted, or does it now exist in BOTH places (silent divergence risk)?
4. **Tests fail-on-revert:** do `tests/test_routing_policy.py` (and any changed tests) actually turn RED if the extraction is reverted / a policy branch is broken? Name any that pass regardless.
5. **Blast radius:** what else imports the moved symbols? Any caller left pointing at the old path?

## DELIVERABLE — write ONE file: `/home/stack/charon-private/fleet/reviews/DECOMPOSE-REVIEW.md`
- VERDICT: SAFE-TO-MERGE / MERGE-WITH-FIXES / DO-NOT-MERGE + confidence.
- Each finding: file:line, concrete failing input/scenario, severity.
- Explicitly answer behavior-preservation and fail-on-revert (yes/no + evidence).
Tight, evidence-cited, no fluff.

## LAST STEP (required)
Print the file path. Do NOT commit, push, or edit anything else.
