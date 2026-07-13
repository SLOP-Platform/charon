---
description: "FEEDBACK — adopt best-in-class existing tools instead of building; evaluate on CODE QUALITY + FEATURES + freshness mechanism, NOT stars/age/recency. A new low-star project with clean code beats a stale popular one. Charon/SLOP are new with zero stars too"
metadata: 
name: evaluate-tools-by-code-not-stars
node_type: memory
originSessionId: fffc7f6f-75c2-4588-b70e-1d3885da5281
type: feedback
tags: [memory]
last_referenced: 2026-07-13
---
Operator (2026-07-12): don't dismiss a project for being new or low-star. "Charon/SLOP are completely new and have ZERO stars." Judge on the code and the features, not popularity or recency.

**Why:** the reflex to prefer popular/old projects (or to build-from-scratch rather than adopt) throws away better options and reinvents solved problems. Getting LLM/provider pricing, web change-detection, memory stores, etc. are SOLVED — plenty of people do them. The manager kept mislabeling solved problems as "NEW" work to build.

**How to apply:** when a capability is needed, FIRST investigate existing best-in-class tools to ADOPT/wrap ([[ksf-modular-plugin-best-in-class]]). In the eval, clone + READ the actual code (structure, tests, dep weight, license, the freshness/update mechanism — the hard part), assess coverage/features, and rank on that — stars/age are NOT a scoring axis and low-star is NOT a disqualifier. Only build the thin glue that adapts the best tool to Charon. Reframe "NEW: build X" tickets as "ADOPT best-in-class X" before building. Applies to product AND rig.
