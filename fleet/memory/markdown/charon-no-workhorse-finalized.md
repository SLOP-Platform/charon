---
description: "NO model is finalized as the workhorse for ANY tier — gpt-5.4's heavy usage was ONE long TEST session, not a choice; per-tier model selection is PENDING real-code testing + the benchmark. Never assert a chosen workhorse."
metadata: 
name: charon-no-workhorse-finalized
node_type: memory
originSessionId: aaf1f929-5adf-4f7f-862d-792cd64617af
type: project
tags: [charon]
last_referenced: 2026-07-13
---
STANDING CORRECTION (operator, 2026-07-08 — has had to remind repeatedly): **the operator has NOT finalized a workhorse model for ANY tier.**

- gpt-5.4's large observed usage (~18.9M tokens / 19h in the usage profile) was a **single long TEST session** — the last model being trialed — NOT a chosen default. Do NOT infer "workhorse" from usage volume.
- Every tier (frontier / strong / open-weight coding / etc.) is **OPEN, under test.** Candidates are being trialed; none selected.
- Selection is **pending extensive real-code testing + the real-outcomes benchmark (#26 / BENCH-REGROUND-LIVE)** — the [[benchmark-not-a-valid-ranker]] pivot exists precisely so DATA picks each tier's model, per [[multiple-tested-options-per-tier]].

**How to talk about it:** call gpt-5.4 (or any model) an "incumbent / current default under test," never "the workhorse" or "your primary." Provider-stack / routing framing must say "candidates per tier, selection pending" — never bake in a chosen model. This is why Cline Pass etc. are added as TEST legs, not commitments. Relates [[charon-pools-redesign]], [[charon-work-composition-intelligence]].
