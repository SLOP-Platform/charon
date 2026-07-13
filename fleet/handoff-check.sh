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

# 1c) DATE STAMP — a handoff must carry an absolute date (ordering + staleness)
say "[date]"
if grep -qE '(^|[^0-9])20[0-9][0-9]-[01][0-9]-[0-3][0-9]([^0-9]|$)' "$F"; then
  ok "has date stamp (YYYY-MM-DD)"
else
  miss "MISSING date stamp — add a '**Date:** YYYY-MM-DD HH:MM TZ' line near the top"
fi

# 1d) PROVENANCE — anti-clobber: a handoff seeded by copying ANOTHER session's file (e.g.
# 3647e0e, which seeded mace-windu's file with obi-wan's old handoff) is only obviously wrong
# if the embedded "Session:" stamp is checked against the FILENAME's session slug. A plain
# copy carries the donor session's name/HEAD, so this mismatch is the tell.
say "[provenance]"
fname_session=""
case "$(basename "$F")" in
  SESSION-HANDOFF-*.md) fname_session="$(basename "$F" .md)"; fname_session="${fname_session#SESSION-HANDOFF-}" ;;
esac
if [ -n "$fname_session" ]; then
  stamped_session="$(grep -m1 -E '^\*\*Session:\*\*' "$F" | sed -E 's/^\*\*Session:\*\* *//' | tr -d '\r')"
  if [ -z "$stamped_session" ]; then
    miss "no '**Session:** <name>' provenance stamp — cannot verify this handoff wasn't copied from another session (regenerate via handoff.sh)"
  elif [ "$stamped_session" = "$fname_session" ]; then
    ok "session stamp matches filename: $stamped_session"
  else
    miss "SESSION MISMATCH — filename says '$fname_session' but stamp says '$stamped_session' (looks like a COPIED/stale placeholder handoff from another session)"
  fi
else
  say "  ~ filename doesn't match SESSION-HANDOFF-<name>.md — skipping session-stamp check"
fi

# 1e) FRESHNESS — a handoff generated while the local repo was behind origin (and could not
# fast-forward) is stale by construction: the state it describes is not the real current state.
# handoff.sh stamps "⚠ STALE" into the Product/Rig HEAD lines when behind > 0 — catch it here
# so a stale handoff cannot be committed/closed as if it were current.
say "[freshness]"
if grep -qE '⚠ STALE' "$F"; then
  miss "STALE marker found in provenance stamp — local repo was behind origin when this handoff was generated; sync-checkouts.sh + regenerate before closing"
else
  ok "no STALE marker in provenance stamp"
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
