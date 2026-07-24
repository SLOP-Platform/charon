repo: charon-private
tier: economy
difficulty: 2
work_class: rig-meta
parked:
reserved_note: The compaction MECHANISM (fleet/hooks/memory-compact.sh) is a self-contained bash script that takes the memory dir as a PARAM and is tested against fixtures — fully SG-claimable. It must NEVER hardcode the ~/.claude path (per no-hardcoded-cross-boundary-paths) and NEVER delete a memory topic file — only compact the INDEX. The manager reviews the run against the real memory dir before wiring.
branch: feat/memory-index-compaction
owns: fleet/hooks/memory-compact.sh
serial_justified: Single mechanism. Wiring is via a settings.json PostToolUse/SessionStart hook ENTRY (config, not a shared script) to avoid the fleet/hooks/session-start.sh owns-collision with SYNC-SCHEDULE — so this ticket owns only the new standalone script.
depends_on:
dep-kind:
work_class_note: manager-memory hygiene; recurring — the compaction hook keeps firing (2026-07-15).
note: |
  OBSERVED 2026-07-15 (manager session): the memory index MEMORY.md at
  ~/.claude/projects/-home-stack-code-charon/memory/ grew to 20.3KB, approaching
  the 24.4KB read limit; a PostToolUse hook fires "compact it to under 17.1KB" but
  the compaction itself is a MANUAL step that gets deferred every session. This is
  a dynamic-tools-never-on-demand violation: the fix must be a MECHANISM, not a
  reminder.
accept: |
  - NEW fleet/hooks/memory-compact.sh: when MEMORY.md exceeds a threshold (e.g.
    17KB), it enforces the one-line-per-entry invariant (any entry whose detail
    leaked into the index is truncated to its pointer line), flags stale/duplicate
    pointers for review, and reports the new size. It NEVER deletes a memory topic
    file — only compacts the INDEX. Idempotent; safe to run every session.
  - WIRED into SessionStart (and/or a PostToolUse trigger on the memory dir), per
    dynamic-tools-never-on-demand — not a manual step.
  - fail-on-revert test: a bloated fixture index -> hook brings it under threshold
    with every pointer preserved (one line each); a compact index -> no-op.
  - Because this edits files OUTSIDE the repo (~/.claude/...), the script takes the
    memory dir as a parameter/env (no hardcoded cross-boundary path per
    [no-hardcoded-cross-boundary-paths]); the repo holds only the mechanism + test.
scope: |
  Manager-memory hygiene mechanization. Blast radius: the manager's own recall —
  a bad compaction could drop a pointer. Claude-reserved; manager builds + reviews.
ds: Now (rig-only, parked/claude-reserved). Low-difficulty, high-recurrence-annoyance.
