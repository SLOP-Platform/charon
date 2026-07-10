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
# bootstrap one-liner must be a fenced copy-paste block AND a SINGLE SENTENCE (not a paragraph).
# The FILE holds complete instructions; the bootstrap only points at it. Recurring drift = paragraphs.
if grep -qE '```' "$F"; then
  ok "has fenced block (bootstrap one-liner)"
  BLOCK=$(awk '/```/{c++; next} c==1{print}' "$F")
  nlines=$(printf '%s\n' "$BLOCK" | grep -c '[^[:space:]]')
  splits=$(printf '%s' "$BLOCK" | grep -oE '[.;!?][[:space:]]+[^[:space:]]' | wc -l | tr -d ' ')
  if [ "${nlines:-0}" -eq 1 ] && [ "${splits:-0}" -eq 0 ]; then
    ok "bootstrap is a single-sentence one-liner"
  else
    miss "bootstrap must be ONE sentence pointing at the handoff FILE (found ${nlines} line(s), ${splits} sentence-break(s)) — move first-actions/hard-rules INTO the file body, not the bootstrap"
  fi
else
  miss "no fenced code block (bootstrap must be copy-pasteable)"
fi

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
