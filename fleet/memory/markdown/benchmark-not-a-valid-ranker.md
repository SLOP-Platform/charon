---
description: "the synthetic S0-S6 benchmark is a smoke-test, NOT a valid quality ranker — pivot the ranking brain to real outcomes before wiring it into routing/assignment"
metadata: 
name: benchmark-not-a-valid-ranker
node_type: memory
originSessionId: fbcc2b18-3ba9-4057-b3fd-af8c3e6ffb84
type: project
tags: [benchmark]
last_referenced: 2026-07-13
---
**Adversarial validity review (2026-07-07, `fleet/BENCHMARK-VALIDITY-REVIEW.md`) verdict: the benchmark is a competent smoke-test / regression floor but NOT fit to be the routing/assignment ranking brain — "closer to theater than measure" for ranking.**

Why (ranked): (1) CRITICAL — graders are world-readable + grading is self-driven/self-reported by the model under test → gameable NOW (`cat graders/s2.py` = answer key). Ticket **#26 out-of-band grading is the top fix; nothing the benchmark says is trustworthy until it lands.** (2) Near-zero discrimination — 5/7 sections saturate at 100 for everyone (root cause of the pools-review "grades inert" finding). (3) Blind to the real failure modes it should catch (glm scored 100 on a path it BLOCKed live; deepseek confabulated). (4) N=1 + harness-artifact variance (proven live: glm-5.2 scored S3 100 then 75, S5 100 then 60 across runs → motivates #16 aggregate). (5) Spoon-fed single-file Charon-shaped tasks (construct validity).

**STRATEGIC PIVOT — CONFIRMED by operator 2026-07-08 (satele-shan session):** demote synthetic S0-S6 to a SMOKE-TEST; **re-ground the ranking/grades brain in REAL OUTCOMES** — the `source=live` actuals ledger (already out-discriminates the synthetic 100s) + **replaying real reds** (#25 — un-memorizable, self-refreshing, ready-made `check_cmd` graders). This changes the [[charon-pools-redesign]] grades-table source from "benchmark-fed" to "real-outcomes-fed" (strictly more valid). Reds-replay likely SUBSUMES the generic synthetic sections; only DELIBERATELY-DESIGNED capability probes (#22 modality, #23 memory/vague/contradiction) earn unique keep.

**Guardrails already mandatory:** the pools ADR quarantines ROUTING behind a decision-differentiation gate (keep it); #27 closes the same carve-out for #14 assignment. Provisional-vs-active (#20) lets new tests collect data without touching grades until proven to discriminate. Relates [[charon-work-composition-intelligence]].
