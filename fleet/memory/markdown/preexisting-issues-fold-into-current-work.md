---
description: "Pre-existing failures/reds ALWAYS get folded into the current work branch, never spun off as a separate \"cleanup later\" ticket"
metadata: 
name: preexisting-issues-fold-into-current-work
node_type: memory
originSessionId: a95dc541-223e-4053-8197-6848f0322d6b
type: feedback
tags: [memory]
last_referenced: 2026-07-13
---
FEEDBACK (2026-07-11): pre-existing issues — failing tests, reds, latent bugs surfaced during a wave — are **always folded into the CURRENT work/branch**, not filed as a separate ticket or deferred.

**Why:** "cleanup later" tickets rot; folding fixes them while the context is hot and keeps master honest (full green as the wave's acceptance bar).

**How to apply:** when a wave's suite shows pre-existing failures (e.g. tonight's `test_boundary::...transitively` + `test_routing_proxy_cli_reports_port`, which fail under bare pytest but pass with `PYTHONPATH=src`), fix them on the SAME branch as part of that wave's acceptance — don't defer, don't loosen the assertion, fix the root cause. Extends [[never-ignore-preexisting-issues]].
