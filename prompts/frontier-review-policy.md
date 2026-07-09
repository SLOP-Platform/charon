# FRONTIER-REVIEW-POLICY — Spec the "frontier review for free-tier work" policy

## Context
Operator caveat on decision #2 (DRAIN priority: free-first-then-drain): "Work done by free
tiers should have a frontier model review." Operator decision #22/#23: create a parked
ticket to review/spec this policy, but do NOT implement/enforce it this session.

## Open questions to resolve in the spec
1. Is it a hard gate for ALL free-tier-generated code, or only for
   money/auth/routing/deploy-sensitive changes?
2. Which models count as "frontier" for review purposes? (Claude Opus 4.8? GPT-5.5-pro?
   Gemini 3.1 Pro?)
3. Does the review happen pre-merge or post-merge-as-follow-up?
4. How does this interact with the autonomous land-push workflow?
5. What constitutes "free-tier work"? (Any code generated while the session model was a
   free-tier model? Or only code that shipped via a free-tier routing path?)

## Deliverable
A spec document, not enforcement code. The spec should define the policy, the gate
mechanism, the model list, and the merge interaction. After operator approval, a separate
build ticket would implement it.

## Dependencies & sequence
No depends_on. PARKED — do not build this session.
