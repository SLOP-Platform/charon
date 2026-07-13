---
description: "use any free-tier provider resource when possible, up to its daily/weekly/monthly (rate/quota) limits, before paid — treat free-tier quota like a balance and spill when exhausted"
metadata: 
name: use-free-tiers-to-their-limits
node_type: memory
originSessionId: aaf1f929-5adf-4f7f-862d-792cd64617af
type: feedback
tags: [free-tier, routing, tier]
last_referenced: 2026-07-13
---
FEEDBACK / DIRECTIVE (operator, 2026-07-08): any free-tier resource should be USED when possible, up to its daily/weekly/monthly limits, before spending on paid.

**How to apply:**
- Free-first routing is already the cost-sort default (free rank-0 sorts ahead) — good for OPEN-model pools; ADD capable free-tier members (groq / mistral / together / cerebras / opencode-go-free) to the open pools they can actually serve (capability-matched only — a free model must NOT front a closed premium pool it can't serve, and the config pass showed free rank-0 members silently hijack the happy path if mis-placed).
- **Track free-tier quota / rate-limit REMAINING like a balance:** generalize the P3 balance-monitoring work from "balance for paid" to "resource availability" = balance (paid) + quota/rate-remaining (free), so routing spills to the next option when a free tier hits its daily/weekly/monthly wall instead of erroring.
- Respect per-provider caps (e.g. cerebras 5 req/min, groq 14.4k req/day).

**Caveat:** free tiers are PERSONAL-account ToS (see [[charon-free-tier-routing]]) — legitimate for a single-user gateway only; revisit if the gateway ever fronts anyone but the operator. Relates [[charon-pools-redesign]], [[charon-free-tier-routing]].
