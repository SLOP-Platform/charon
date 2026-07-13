---
description: Answer simple questions directly in one line; always state WHERE a command runs
metadata: 
name: answer-concisely-and-say-where-to-run
node_type: memory
originSessionId: 5c492534-764e-4b91-85a1-faf64bb20be6
type: feedback
tags: [ci, presentation]
last_referenced: 2026-07-13
---
Two standing rules for operator interaction:

1. **Simple question → direct concise answer.** When the operator asks a simple/yes-no question, lead with the one-line answer (e.g. "No, run these in the WSL environment, in <path>"). Do NOT open with tables, tradeoff matrices, or scrolling context. Add detail only if truly needed, and keep it minimal.

2. **Always say WHERE to run a command.** Any command handed to the operator must state the environment/host and, if it matters, the path — e.g. "run in this WSL box", "on self-hosted-runner", "in /repo/charon". Never give a bare command without location.

**Why:** operator was given a wall-of-text table in response to a one-word question ("run these on self-hosted-runner?"), and command blocks that didn't say which host. Both waste their time and burn manager context/tokens.

**How to apply:** front-load the answer; expand only on request. Pair with [[always-give-exact-command]] (exact copy-pasteable command) and [[present-findings-in-color-tables]] (tables are for findings/status, not for answering a simple question).
