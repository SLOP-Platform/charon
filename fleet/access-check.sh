#!/usr/bin/env bash
# access-check.sh — DURABLE, MECHANIZED access report so no session re-discovers "is X set up?".
# Every probe is timeout+BatchMode wrapped so it can NEVER hang a boot; purely INFORMATIONAL
# (always exits 0). Wired into preflight.sh so it runs at every session start. Update the probes
# here when a host/path/route changes — this file, not a handoff line, is the source of truth for
# HOW the manager reaches each resource. (2026-07-10: Roci + push were repeatedly re-discovered
# because stale "denied / operator-only" handoff lines were trusted over reality.)
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
T=5
ok(){ printf '  \033[32m✓\033[0m %-22s %s\n' "$1" "$2"; }
no(){ printf '  \033[31m✗\033[0m %-22s %s\n' "$1" "$2"; }

echo "== ACCESS (mechanized — how the manager reaches each resource) =="

# Push — via the sanctioned wrapper, gated by the AUTONOMOUS lever (NOT operator-only).
if [ -e "$FLEET/state/AUTONOMOUS" ]; then
  ok "push" "land-push.sh — AUTONOMOUS lever ON → manager pushes without asking"
else
  ok "push" "land-push.sh — lever OFF → ask first (autonomous.sh on to enable)"
fi

# Rocinante (durable-bridge coordinator) — via the ssh config alias, NOT bare stack@10.0.1.51.
if timeout $T ssh -o BatchMode=yes -o ConnectTimeout=$T rocinante 'true' 2>/dev/null; then
  ok "roci ssh" "\`ssh rocinante\` (user stack, key ~/.ssh/mediastack) — rootless, WORKING"
else
  no "roci ssh" "\`ssh rocinante\` failed — check ~/.ssh/config alias + ~/.ssh/mediastack"
fi

# 4-LOM gateway (Charon) — health endpoint (401 = up+auth) and the deploy ssh key.
code="$(timeout $T curl -s -m $T -o /dev/null -w '%{http_code}' http://10.0.1.60:8080/health 2>/dev/null || echo 000)"
if [ "$code" = "401" ] || [ "$code" = "200" ]; then
  ok "charon gateway" "http://10.0.1.60:8080 (4-LOM) up ($code) — route sub-work: opencode run --model charon/<id>"
else
  no "charon gateway" "http://10.0.1.60:8080 unreachable ($code)"
fi
if timeout $T ssh -o BatchMode=yes -o ConnectTimeout=$T -i "$HOME/.ssh/4lom" stack@10.0.1.60 'true' 2>/dev/null; then
  ok "4-lom ssh" "\`ssh -i ~/.ssh/4lom stack@10.0.1.60\` — deploy path (fleet/deploy.sh), WORKING"
else
  no "4-lom ssh" "\`ssh -i ~/.ssh/4lom stack@10.0.1.60\` failed — deploy will be blocked"
fi

echo "== end access =="
exit 0
