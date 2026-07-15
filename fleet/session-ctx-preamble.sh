#!/usr/bin/env bash
# session-ctx-preamble.sh — SESSION-CTX-PROPAGATE: the context-light pointer index every
# Agent/Task sub-session gets, since SessionStart hooks fire ONLY for the primary session
# (see fleet/state/SESSION-RECALL-CHALLENGE.md §1c). Wired into the existing
# `PreToolUse: Agent|Task` hook (fleet/state/SESSION-CTX-HOOK.json) as additionalContext,
# alongside the existing nudge_background_agents.py entry — NOT replacing it.
#
# This is a POINTER INDEX, not full docs: it names the guiding docs + when to read them,
# not their content. HARD size cap ~40 lines (rides on EVERY sub-agent spawn — blast radius
# = per-sub-agent token cost). This is the ONE shared context-light index for both this
# ticket and the sibling STARTUP-CONTEXT-DIET (primary-session ingest diet) — do not fork
# a second index; if the pointer set changes, change it here only.
#
# Output contract: PreToolUse hook JSON on stdout —
#   {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "<preamble>"}}
# NEVER blocks/denies (matches the existing nudge_background_agents.py convention) — this
# script only adds context and always exits 0.
set -uo pipefail

read -r -d '' PREAMBLE <<'EOF' || true
SESSION-CTX (sub-agent pointer index -- look these up on demand, do not pre-read all)
You are an Agent/Task sub-session; no SessionStart hook reaches you. This is your only
automatic context.

GUIDING DOCS (index, not content):
- fleet/MANAGER-OPERATING-RULES.md -- read when unsure how the session should behave
  (cadence, delegation, gates, priority order).
- fleet/TOOL-INVENTORY.md -- read when about to build/investigate/review anything; maps
  intent to the exact existing command.
- fleet/state/EVAL-REGISTRY.md -- read BEFORE adopting/rejecting/re-litigating any
  external tool or library; it may already be settled.
- fleet/state/CG-PROVIDERS.md -- read when you need live gateway/provider/model state;
  SOLE source of truth, probed live -- never trust a cached tier-model label.

TOOL-FIRST / REUSE-CHECK (non-negotiable):
- Before writing any new file/module, run fleet/reuse-check.sh against the candidate path.
- Before adopting/building around any external tool, grep EVAL-REGISTRY.md first.

MECHANISM-SELECTION LADDER (prefer the mechanism over recall, in order):
1. Is there already a hook/gate/launcher flag that does this automatically? Use it.
2. Check TOOL-INVENTORY.md's trigger table for the exact existing command.
3. Run reuse-check.sh before creating new code.
4. Check EVAL-REGISTRY.md before any new-tool research/adoption/rejection.
5. Only hand-build if 1-4 come up empty -- then add the new row/entry so the next
   sub-agent doesn't redo this search.

Write findings to a file; return a short pointer (FILE: <path> + <=5-line summary) --
never paste full contents back to the coordinator.
EOF

printf '%s' "$PREAMBLE" | python3 -c '
import json, sys
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": sys.stdin.read(),
    }
}))
'
exit 0
