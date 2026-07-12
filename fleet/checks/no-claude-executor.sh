#!/usr/bin/env bash
# no-claude-executor.sh — LEAK-GUARD (mechanical). FAIL LOUD if any fleet WORK-EXECUTOR would route
# to Anthropic instead of running OFF Claude through the Charon gateway.
#
# THE BUG THIS CATCHES: fleet-droid.sh once ran `claude -p --model opus/sonnet` as the droid work
# agent with no ANTHROPIC_BASE_URL -> hit Anthropic directly = burned Claude tokens. Fleet WORK must
# run off Claude via the gateway ($CHARON_AGENT_CMD -> charon-run.sh -> `charon/<model>` on 4-LOM).
# The MANAGER stays on Claude; the WORK does not.
#
# Exit 0 = CLEAN (no `claude -p/--print/--bg` work agent; gateway client wired).
# Exit 1 = RED  (a work-executor invokes claude, or the gateway dispatch is missing).
#
# Consumed by preflight.sh via reds.tsv (row `fleet-executor-hits-anthropic`); runnable standalone.
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
rc=0

# WORK-EXECUTOR scripts that must NEVER launch claude as the agent. (charon-run.sh is the gateway
# client; the manager's own claude session is out of scope — this is about the DROID WORK step.)
EXECUTORS=("$FLEET/fleet-droid.sh")

for f in "${EXECUTORS[@]}"; do
  [ -f "$f" ] || continue
  # Match `claude -p/--print/--bg` anywhere on the line (incl. a line that STARTS with it), then
  # drop comment lines (`<lineno>:` prefix followed by optional space + '#').
  hits="$(grep -nE '\bclaude[[:space:]]+(-p|--print|--bg)\b' "$f" | grep -vE '^[0-9]+:[[:space:]]*#')"
  if [ -n "$hits" ]; then
    printf '%s\n' "$hits"
    echo "LEAK: $f invokes 'claude -p/--print/--bg' as the work executor — routes to Anthropic, burns Claude tokens. Route work off-Claude via \$CHARON_AGENT_CMD (gateway)." >&2
    rc=1
  fi
done

# Positive assertion: the droid launcher must dispatch its work through the swappable gateway client.
if ! grep -q 'CHARON_AGENT_CMD' "$FLEET/fleet-droid.sh"; then
  echo "LEAK: fleet-droid.sh no longer dispatches work via \$CHARON_AGENT_CMD (the off-Claude gateway client)." >&2
  rc=1
fi

[ "$rc" -eq 0 ] && echo "no-claude-executor: CLEAN — fleet work runs off Claude via the gateway client."
exit $rc
