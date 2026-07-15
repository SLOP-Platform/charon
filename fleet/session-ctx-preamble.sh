#!/usr/bin/env bash
# session-ctx-preamble.sh — SESSION-CTX-PROPAGATE: the context-light pointer index every
# Agent/Task sub-session gets, since SessionStart hooks fire ONLY for the primary session
# (see fleet/state/SESSION-RECALL-CHALLENGE.md §1c). Wired into the SubagentStart hook
# (fleet/state/SESSION-CTX-HOOK.json) as additionalContext.
#
# WHY SubagentStart (not PreToolUse:Agent|Task): SubagentStart.additionalContext is injected
# into the SPAWNED sub-agent's own initial context. A PreToolUse:Agent hook's additionalContext
# goes to the CALLING/parent session, NOT the child — so it cannot reach a sub-agent at all.
# SubagentStart is the purpose-built lever; confirmed against Claude Code hooks docs.
#
# This is a POINTER INDEX, not full docs: it names guiding docs + when to read them, not their
# content. HARD size cap ~40 lines (rides on EVERY sub-agent spawn — blast radius = per-sub-agent
# token cost). This is the ONE shared context-light index for both this ticket and the sibling
# STARTUP-CONTEXT-DIET (primary-session ingest diet) — do not fork a second index; if the pointer
# set changes, change it here only.
#
# FRESH-WORKTREE-SAFE: every doc/script named below is git-TRACKED, so it resolves in the
# worktrees where sub-agents actually run. Do NOT add pointers to gitignored local-only state
# (e.g. fleet/state/EVAL-REGISTRY.md, fleet/state/CG-PROVIDERS.md) — those are absent in a fresh
# checkout and would dangle for exactly the sub-sessions this preamble targets. For live
# provider/eval state, route sub-agents through the commands in TOOL-INVENTORY.md instead.
#
# Output contract: SubagentStart hook JSON on stdout —
#   {"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": "<preamble>"}}
# NEVER blocks (SubagentStart cannot block subagent creation anyway) — this script only adds
# context and always exits 0. If anything fails it emits nothing and fail-opens (exit 0).
set -uo pipefail

read -r -d '' PREAMBLE <<'EOF' || true
SESSION-CTX (sub-agent pointer index -- look these up on demand, do not pre-read all)
You are an Agent/Task sub-session; no SessionStart hook reaches you. This is your only
automatic context. Every doc/script below is git-tracked, so it resolves in your worktree.

GUIDING DOCS (index, not content):
- fleet/MANAGER-OPERATING-RULES.md -- read when unsure how the session should behave
  (cadence, delegation, gates, priority order).
- fleet/TOOL-INVENTORY.md -- read when about to build/investigate/review anything; maps
  intent to the exact existing command. This is also how you reach LIVE gateway/provider/
  model state and eval history -- run the listed command, never trust a cached tier label.

TOOL-FIRST / REUSE-CHECK (non-negotiable):
- Before writing any new file/module, run fleet/reuse-check.sh against the candidate path.
- Before adopting/building around any external tool, find the eval command in
  TOOL-INVENTORY.md -- the decision may already be settled; do not re-litigate blind.

MECHANISM-SELECTION LADDER (prefer the mechanism over recall, in order):
1. Is there already a hook/gate/launcher flag that does this automatically? Use it.
2. Check TOOL-INVENTORY.md's trigger table for the exact existing command.
3. Run reuse-check.sh before creating new code.
4. Check the eval history (via TOOL-INVENTORY.md) before any new-tool adoption/rejection.
5. Only hand-build if 1-4 come up empty -- then add the new row/entry so the next
   sub-agent doesn't redo this search.

Write findings to a file; return a short pointer (FILE: <path> + <=5-line summary) --
never paste full contents back to the coordinator.
EOF

printf '%s' "$PREAMBLE" | python3 -c '
import json, sys
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SubagentStart",
        "additionalContext": sys.stdin.read(),
    }
}))
'
exit 0
