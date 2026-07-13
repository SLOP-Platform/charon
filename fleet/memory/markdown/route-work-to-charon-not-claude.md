---
description: DIRECTIVE — hand ALL droid/subsession work that CAN run through Charon Gateway to the operator with a best-fit model rec; reserve Claude only for work that truly needs it
metadata: 
name: route-work-to-charon-not-claude
node_type: memory
originSessionId: 02f0da30-0dc8-45ce-acbc-4cded96858db
type: feedback
tags: [charon, routing]
last_referenced: 2026-07-13
---
DIRECTIVE (operator, 2026-07-09): Going forward, for every substantive unit of work, first ask "does this NEED Claude?" If NOT, route it through the **Charon Gateway** — hand it to the operator as a droid/opencode task **with the best-fit model named** (rough estimate is fine), instead of spawning a Claude Agent sub-session. Reserve Claude for work that genuinely needs it (manager gating/dialogue, or Claude-specific capability).

**Why:** preserve Claude budget/use-limits (operator hit the limit this session); use Charon's cheaper/free/flat providers for everything else — the product eating its own dogfood.

**How to apply:** when I would normally launch a Claude sub-agent, instead default to: (1) decide Claude-vs-Charon; (2) if Charon, give the operator a ready-to-run brief + the recommended Charon model (from the pool: e.g. coding candidates Kimi K2.7 Code / DeepSeek V4 / GLM-5.2, or right-sized cheaper) + the tab command; (3) only keep it in Claude if it truly needs Claude. Relates [[subsession-model-and-token-policy]], [[recommend-model-for-droid-work]], [[use-free-tiers-to-their-limits]], [[dont-build-products-in-manager-session]].
