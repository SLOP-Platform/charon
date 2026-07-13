---
description: "FEEDBACK — when adversarial review/DTC overturns an OPERATOR strategic decision (not an AI/plan call), surface it for re-confirmation; never silently reconcile it into the ADR"
metadata: 
name: adversarial-review-must-not-silently-override-operator
node_type: memory
originSessionId: 04b7358b-67d3-40fe-ad36-24ab7cb15864
type: feedback
tags: [debugging, operator, review]
last_referenced: 2026-07-13
---
When the Charon build methodology's adversarial review / DTC gate overturns a decision, it MUST distinguish *whose* decision it is overturning. Overturning an AI-proposed or plan-level call on the evidence is fine (reconcile in REVIEW-LOG, proceed). Overturning an **operator strategic decision** is NOT — it must be surfaced back to the operator for explicit re-confirmation before being written into an ADR as "reconciled."

**Why:** This actually happened (2026-06-26). The operator decided "Charon's work-engine is core, build the coordination substrate NATIVE, sooner" ([[charon-own-work-engine]], [[charon-vision-gateway-first]]). ADR-0007's 3-lens adversarial review inverted it to "engine deferred behind D10 tripwires, maybe never," recorded it as the settled outcome, and the reversal then propagated across sessions as truth — including a later session re-ratifying ADR-0007 with the deferral framing. The decision was never lost from memory; it was silently overruled by a process gate and re-buried under its own reversal.

**How to apply:** (1) Tag each decision with its owner (operator vs AI/plan). (2) If a review would reverse an operator-owned decision, STOP and re-confirm with the operator — do not auto-reconcile. (3) In memory/ADRs, never place a decision's reversal in the same blob as the decision without a loud CORRECTION marker, or the contradiction goes invisible. (4) Acceptance/ratification of an ADR is itself a decision point — re-check it against operator intent, don't rubber-stamp prior framing.

Related: [[charon-build-methodology]] [[charon-own-work-engine]] [[charon-vision-gateway-first]]
