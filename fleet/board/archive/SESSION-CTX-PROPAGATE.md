repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/session-ctx-propagate
depends_on:
owns: fleet/session-ctx-preamble.sh, fleet/tests/session-ctx-preamble.test.sh, fleet/state/SESSION-CTX-HOOK.json
accept: |
  FIX the #1 session-recall driver (see fleet/state/SESSION-RECALL-CHALLENGE.md): SessionStart hooks fire only for the
  PRIMARY session, so every Agent/Task SUB-session starts BLIND and the coordinator must hand-re-brief it every time —
  the dominant "surface the same thing multiple times per session" cost.
  DO:
  - fleet/session-ctx-preamble.sh: emit a CONTEXT-LIGHT preamble — a POINTER INDEX, not full docs. Include: the guiding-docs
    list (MANAGER-OPERATING-RULES, TOOL-INVENTORY, EVAL-REGISTRY, the CG-PROVIDERS env-registry) each with a one-line
    "read this when X"; the reuse-check + tool-first reminders; the mechanism-selection ladder. HARD size cap (~40 lines) —
    it rides on EVERY sub-agent, so it must stay tiny (blast radius = per-sub-agent token cost).
  - Wire it into the EXISTING `PreToolUse: Agent|Task` hook so the preamble is injected as additionalContext on every
    sub-agent launch. Write the EXACT settings.json hook JSON to fleet/state/SESSION-CTX-HOOK.json for the MANAGER to apply +
    verify. Do NOT edit ~/.claude/settings.json yourself — it governs the live running session.
  FAIL-ON-REVERT (fleet/tests/session-ctx-preamble.test.sh): assert the preamble outputs the pointer index AND stays under
  the size cap (revert → empty/oversized → test fails); assert the hook JSON targets Agent|Task and carries the preamble.
