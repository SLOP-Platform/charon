# Shared fleet helpers. `source` this AFTER setting FLEET.
# Single home for id canonicalization + dependency checks so the gating scripts
# (claim/board/status) can't diverge again (audit 2026-06-27, THEMEs 1 & 5).
FLEET_LIB_BOARD="${FLEET:?_lib.sh: set FLEET before sourcing}/board"
FLEET_LIB_STATE="$FLEET/state"

# canon <id> -> exact board basename (case-insensitive). Non-zero + stderr if no match.
canon(){ local w="$1" f b; for f in "$FLEET_LIB_BOARD"/*.md; do b="$(basename "$f" .md)"
  [ "${b,,}" = "${w,,}" ] && { printf '%s' "$b"; return 0; }; done
  echo "no board ticket matching '$w'" >&2; return 1; }

# deps_done <comma-separated-list> -> 0 if EVERY dep is done, else 1. Empty list = 0 (no deps).
# Splits on commas (multi-dep) and canonicalizes each id, so `depends_on: E6, FB4` works.
deps_done(){ local raw="${1:-}" d dc; [ -n "$raw" ] || return 0
  for d in $(echo "$raw" | tr ',' ' '); do
    dc="$(canon "$d" 2>/dev/null)" || dc="$d"
    [ -e "$FLEET_LIB_STATE/done/$dc" ] || return 1
  done; return 0; }
