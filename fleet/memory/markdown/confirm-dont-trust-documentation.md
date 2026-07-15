---
description: "Don't trust documentation/board/docstrings/prior-analysis — ALWAYS confirm against real code; recommendations must be FACTS not inference"
metadata: 
name: confirm-dont-trust-documentation
node_type: memory
originSessionId: a95dc541-223e-4053-8197-6848f0322d6b
type: feedback
tags: [memory]
last_referenced: 2026-07-13
---
FEEDBACK (2026-07-11): **"Don't trust documentation — ALWAYS confirm."** Every recommendation, sequence, blocker, and effort estimate must be based on FACTS read from the actual code/state — never inferred from docs, board status, docstrings, or a prior analysis.

**Why:** the ROUTER-NEXT-PLAN inferred R11 was "blocked — balance mechanics exist but unwired," so I recommended deferring live-API balance as "bespoke work." Reality (found only when the operator pushed): `balance.py` already had working poll adapters (DeepSeek `/user/balance`, OpenRouter `/api/v1/credits`, NanoGPT `/api/check-balance`) + a `BalanceTracker` already wired into gateway/proxy_server/forwarder. The inference-based "blocked/defer" was wrong and would have wasted a rebuild + given a bad recommendation.

**How to apply:** before recommending / sequencing / estimating effort, `grep`+read the real code and cite file:line. Treat board `parked/designed`, a plan's `blocked/not-built`, and docstrings (`"unwired"`, `"stub"`) as **claims to verify, not facts** — a docstring can lie. When unsure, run a focused code-confirmed audit rather than repeating a doc's claim. Extends [[document-model-self-report-lies]], [[never-ignore-preexisting-issues]].
