repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
priority: 0
branch: feat/session-bridge-converge
depends_on:
owns: fleet/handoff-notes/BRIDGE-CONVERGE-TRIAGE.md, fleet/board/SESSION-BRIDGE-CONVERGE.md
serial_justified: |
  ONE triage pass over 4 bridge tickets. The table and consumer count must be written before
  any action; the verification (Phase 2) validates findings. Splitting triage and verification
  ships stale analysis.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session. Graded sample. Own worktree.
source: |
  Operator brief: /home/stack/charon-private/fleet/state/agent-briefs/SESSION-BRIDGE-CONVERGE.md
  (P0, rig-meta, operator's #1 priority)
note: |
  ## PHASE 1 — TRIAGE (read-only)
  Four bridge tickets exist with at least two contradictions. Establish which is still real.
  Ground every finding in file:line or command transcript.

  ## PHASE 2 — VERIFY
  Drive the highest-blast-radius item: verify BRIDGE-PROXY-HEARTBEAT is actually built and
  working via hermetic red/green tests in the session-bridge repo.
accept: |
  DONE-CONTRACT:
  - Phase 1 table written to fleet/handoff-notes/BRIDGE-CONVERGE-TRIAGE.md (<150 lines)
  - True consumer count listed with file:line evidence
  - Contradictions called out loudly
  - Recommended sequence with what blocks what
  - Phase 2: verify heartbeat via test_proxy.py (red→green transcripts pasted)
  - Board ticket created at fleet/board/SESSION-BRIDGE-CONVERGE.md
  - Commit on this branch, SHA printed
  - No push

## Dependencies & sequence
- **Depends on: NOTHING** for Phase 1 (read-only triage); Phase 2 depends on Phase 1 output.
- **Blocks:** retirement of stale bridge tickets, resolution of REPLACE-vs-WIRING contradiction.
- **Makes moot:** any further BRIDGE-PROXY-HEARTBEAT work — the heartbeat is already built.
