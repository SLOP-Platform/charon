# NANOGPT-PRIMARY-REVIEW — Review whether drainable balances should outrank NanoGPT

## Context
Operator decision #30: keep NanoGPT primary unless a specific drain fast-path applies,
AND create a parked ticket to review whether drainable balances should generally outrank
NanoGPT later.

## Review criteria (after DRAIN-ROUTING is live)
1. Did NanoGPT's $12/mo flat sub get underutilized because drainable balances were spent
   first? (Check usage logs for NanoGPT token volume vs. drainable provider volumes.)
2. Did any drainable balance expire unused because NanoGPT was always primary? (Check
   balance expiry events.)
3. Should the policy change to "drain expiring balances first, then NanoGPT, then metered"?
   (Compare cost outcomes: expired-balance-wasted vs. NanoGPT-underutilized.)
4. Is the 60M tok/wk NanoGPT cap ever hit? If so, does drainable-first help avoid it?

## Deliverable
A data-driven review with a recommendation to the operator. Not a code change. If the
recommendation is to change the policy, create a follow-up build ticket.

## Dependencies & sequence
- depends_on: DRAIN-ROUTING (must be live to observe actual behavior).
- PARKED — do not build this session.
