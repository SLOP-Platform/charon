#!/usr/bin/env bash
# repo-map-single-home.sh — gate: fail if any fleet script implements its own repo->path/slug map.
# The ONE home for this map is fleet/_lib.sh (which sources fleet/repo-registry.sh).
# A second copy is the drift class REPO-MAP-CONVERGE exists to end — every hand-maintained
# parallel copy of the repo map has already diverged at least once.
#
# Exit 0 = GREEN (no private maps outside the canonical home)
# Exit 1 = RED  (at least one fleet script carries its own repo map)
#
# Usage: repo-map-single-home.sh [--warn]     (--warn = exit 0 always, report-only)
#        repo-map-single-home.sh [--fixture <dir>]  (scan a FIXTURE dir, not the real fleet/)
set -uo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ALLOWLIST=" _lib.sh repo-registry.sh "
FIXTURE_DIR=""
WARN_ONLY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --warn)   WARN_ONLY=1; shift ;;
    --fixture) FIXTURE_DIR="$2"; shift 2 ;;
    *) echo "repo-map-single-home.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

SCAN_DIR="${FIXTURE_DIR:-$FLEET}"

in_set(){ local x="$1"; shift; for e in "$@"; do [ "$x" = "$e" ] && return 0; done; return 1; }

hits=0
shopt -s nullglob 2>/dev/null || true
# Scan *.sh files only (the allow-listed homes are shell; a Python file with a map is caught too).
for f in "$SCAN_DIR"/*.sh "$SCAN_DIR"/checks/*.sh "$SCAN_DIR"/capability/*.sh; do
  [ -f "$f" ] || continue
  bn="$(basename "$f")"
  in_set "$bn" $ALLOWLIST && continue

  # ── Pattern 1: a Python dict named REPO_ROOTS (the exact copy validate_board.sh carried) ──
  if grep -qE '^REPO_ROOTS\s*=\s*\{' "$f" 2>/dev/null; then
    echo "repo-map-single-home: RED — $bn contains a REPO_ROOTS Python dict (allow-listed: $ALLOWLIST)"
    hits=$((hits + 1))
    continue
  fi

  # ── Pattern 2: a shell case/if chain that maps repo keys to hardcoded paths ──
  # A file that contains BOTH a repo key alias pattern AND a hardcoded path in a
  # case-arm or variable-assignment shape is very likely a private map.
  # The key names are the canonical set from repo-registry.sh (charon, charon-private,
  # rig, fleet, keystone, ksf, product).  We look for them in a dispatch shape.
  if grep -qE '(^|[^a-zA-Z0-9._-])(charon-private|rig|fleet|keystone|ksf)[|")]' "$f" 2>/dev/null && \
     grep -qE '/home/stack/(code/(charon|keystone)|charon-private)' "$f" 2>/dev/null; then
    echo "repo-map-single-home: RED — $bn maps repo keys to hardcoded paths (allow-listed: $ALLOWLIST)"
    hits=$((hits + 1))
    continue
  fi
done

tag="RED"; [ "$WARN_ONLY" -eq 1 ] && tag="WARN"
if [ "$hits" -gt 0 ]; then
  echo "repo-map-single-home: $tag — $hits file(s) carry a private repo->path map"
  echo "    migrate to fleet/_lib.sh / fleet/repo-registry.sh — the single canonical home."
  [ "$WARN_ONLY" -eq 1 ] && exit 0
  exit 1
fi

echo "repo-map-single-home: GREEN — no private repo->path maps outside $ALLOWLIST"
exit 0
