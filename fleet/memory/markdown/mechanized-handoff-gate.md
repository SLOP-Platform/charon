---
description: Handoffs must pass fleet/handoff-check.sh; poor/inaccurate handoffs are a recurring failure fixed by the gate
metadata: 
name: mechanized-handoff-gate
node_type: memory
originSessionId: 5c492534-764e-4b91-85a1-faf64bb20be6
type: feedback
tags: [gate, handoff]
last_referenced: 2026-07-13
---
Poor / inaccurate / incomplete session handoffs are a **recurring** problem. Root cause: `fleet/handoff.sh`
(a machine-state GENERATOR) existed but was under-used and incomplete, and there was **no validator** to
catch a bad handoff — so hand-typed facts (SHAs, paths, branches, missing sections) rotted.

**The fix (mechanization, not memory):** `fleet/handoff-check.sh <file>` — a completeness+accuracy GATE
that exits non-zero if the handoff is missing a required section (bootstrap one-liner, done/committed@SHA,
next-action/in-flight, gotchas, session-bridge) or references a SHA/path/script that doesn't exist. Built
2026-07-10.

**How to apply:** before ending ANY session, run `bash fleet/handoff-check.sh <handoff>` and fix until it
PASSES. Prefer generating the machine-state block via `fleet/handoff.sh` over hand-typing facts. Rule added
to MANAGER-OPERATING-RULES.md as `[mechanized-handoff-gate]`. Full enrichment (auto-emit worktrees /
in-flight charon-run jobs / exhaustion tail / bridge board + wire into preflight) = ticket HANDOFF-MECHANIZE.

Relates to [[manager-gives-new-session-prompt]] and [[answer-concisely-and-say-where-to-run]].
