---
description: "Mechanized lean-review method — manager drives non-Claude Charon work via headless opencode, reviews a REVIEW PACKET, never reads the payload"
metadata: 
name: charon-headless-review-loop
node_type: memory
originSessionId: d0187ab4-8667-45fd-8b2a-a1c2c5b70b17
type: feedback
tags: [charon, review]
last_referenced: 2026-07-13
---
DIRECTIVE (2026-07-10): Claude is the MANAGER that reviews Charon-model work in a
smart, minimal-token way — maximize code quality while minimizing what Claude reads.

**The lean loop (proven this session):**
- The `Agent` tool CANNOT point at Charon — its subagents only run Claude models, so
  spawning them spends the Claude limit. Do NOT use `Agent` for routable sub-work.
- Route work to Charon via the durable launcher **`/build-rig/fleet/charon-run.sh`**:
  `bash fleet/charon-run.sh <cwd> <outlog> <brief-file> deepseek-v4-pro glm-5.2 deepseek-v4-flash`
  (fire with `Bash(run_in_background)`). It wraps `opencode run --model charon/<model>` headless
  against the self-hosted-runner gateway `http://<COORDINATOR_HOST>:8080/v1` with cross-model failover + exhaustion
  ledger. Models: `deepseek-v4-pro` (strong coder), `deepseek-v4-flash` (cheap), `glm-5.2` — NO
  kimi in the opencode config. **Zero Claude limit.**
- Every brief ends by requiring the agent to write a **REVIEW PACKET** to a file and do the
  work in the worktree. Packet fields: files+line-ranges changed · root-cause/why · the
  test added that FAILS ON REVERT (name + run cmd) · full-gate result (must self-run green)
  · self-identified risk/blast-radius · committed SHA. LAST STEP: commit + report SHA; do
  NOT push/merge (separate line).
- **Manager's lean review** = read ONLY the packet + the diff of the critical/blast-radius
  file (not the whole change). Verify: gate green? fail-on-revert test present and actually
  exercises the change? diff scope matches the claim? For money-path, one adversarial pass on
  the risk section. Then manager runs the gate itself, pushes via land-push.sh, merges.
- Keeps BOTH axes lean: no Claude-limit spend on the work, and the payload never enters the
  manager's Opus context (which re-reads every turn — the 07-09 drain cause).

Right-size model per work: code-fix → deepseek-v4-pro; adversarial verify → kimi-k2.6 /
deepseek-v4-pro; light investigation → deepseek-v4-flash.

TODO to fully mechanize: wire a packet-validator into the rig + fold into
MANAGER-OPERATING-RULES §3. See [[route-work-to-charon-not-claude]] [[merge-gate-is-full-ci-not-pytest]]
[[tests-must-fail-on-revert]] [[independent-review-before-merge-on-critical]].
