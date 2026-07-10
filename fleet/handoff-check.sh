#!/usr/bin/env bash
# handoff-check.sh <handoff-file> — MECHANIZED completeness+accuracy gate for a session handoff.
# Poor/inaccurate/incomplete handoffs are a recurring failure; this fails LOUD (non-zero) when a
# handoff is missing a required section or references a SHA/path/script that does not exist.
# Read-only. Usage: bash fleet/handoff-check.sh fleet/HANDOFF-YYYY-MM-DD-x.md
set -uo pipefail
F="${1:?usage: handoff-check.sh <handoff-file>}"
PRIV="/home/stack/charon-private"
fail=0
say(){ printf '%s\n' "$*"; }
miss(){ say "  ✗ $*"; fail=1; }
ok(){ say "  ✓ $*"; }

[ -f "$F" ] || { say "handoff-check: NO SUCH FILE: $F"; exit 2; }
say "handoff-check: $F"

# 1) REQUIRED SECTIONS (the shape a next session cannot start without)
say "[sections]"
declare -A NEED=(
  [bootstrap]='[Bb]ootstrap'
  [done/committed]='SHIPPED|DONE|committed'
  [next-action/in-flight]='FIRE|NEXT|in-flight|IN-FLIGHT|first action|WAVE'
  [gotchas]='GOTCHA|avoid|DENIED'
  [session-bridge]='session-bridge|SESSION-BRIDGE'
)
for k in "${!NEED[@]}"; do
  if grep -qiE "${NEED[$k]}" "$F"; then ok "has: $k"; else miss "MISSING section: $k"; fi
done
# bootstrap one-liner must be a fenced copy-paste block
grep -qE '```' "$F" && ok "has fenced block (bootstrap one-liner)" || miss "no fenced code block (bootstrap must be copy-pasteable)"

# 2) ACCURACY — every referenced SHA must exist; committed-SHA claim must match HEAD
say "[sha]"
SHAS=$(grep -oE '\b[0-9a-f]{7,40}\b' "$F" | sort -u)
nsha=0
for s in $SHAS; do
  if git -C "$PRIV" cat-file -e "$s^{commit}" 2>/dev/null || git -C /home/stack/code/charon cat-file -e "$s^{commit}" 2>/dev/null; then
    ok "SHA exists: $s"; nsha=$((nsha+1))
  else
    miss "SHA NOT FOUND in either repo: $s"
  fi
done
[ "$nsha" -ge 1 ] || miss "no valid commit SHA referenced (a handoff must name what was committed)"

# 3) ACCURACY — referenced fleet scripts/briefs/paths must exist
say "[paths]"
PATHS=$(grep -oE '/home/stack/[A-Za-z0-9._/-]+\.(sh|md|py|json|tsv)' "$F" | sort -u)
for p in $PATHS; do
  if [ -e "$p" ]; then ok "exists: $p"; else miss "PATH NOT FOUND: $p"; fi
done

# 4) ACCURACY — referenced git branches: warn (staged branches may not exist yet), don't hard-fail
say "[branches]"
BRS=$(grep -oE '\b(feat|fix|chore|refactor|docs)/[A-Za-z0-9._-]+' "$F" | sort -u)
for b in $BRS; do
  if git -C /home/stack/code/charon show-ref --verify --quiet "refs/heads/$b" 2>/dev/null \
     || git -C "$PRIV" show-ref --verify --quiet "refs/heads/$b" 2>/dev/null; then
    ok "branch exists: $b"
  else
    say "  ~ staged/not-yet-created branch: $b (ok if this handoff stages it)"
  fi
done

say ""
if [ "$fail" -eq 0 ]; then say "handoff-check: PASS"; exit 0; else say "handoff-check: FAIL ($F is incomplete/inaccurate)"; exit 1; fi
