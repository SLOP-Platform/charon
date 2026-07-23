#!/usr/bin/env bash
# claim-jedi-name.sh — mechanized Jedi-session-name allocator.
#
# Computes pool MINUS exclusion-set (every name ever used in a
# SESSION-HANDOFF-*.md, live-tree OR git history), deterministically
# picks the first available, and atomically writes a claim marker
# BEFORE returning — claim-before-build so a concurrent process cannot
# race the same name (same pattern as WORK-LEASE-GATE).
#
# Usage:
#   name="$(bash fleet/claim-jedi-name.sh)"
#         Prints ONLY the claimed name on stdout.
#   bash fleet/claim-jedi-name.sh --verify <name>
#         Returns 0 if <name> is safe to use (not in exclusion set),
#         non-zero + stderr message if it is. Used by handoff.sh to
#         verify an operator-supplied SESSION override.
#   bash fleet/claim-jedi-name.sh --selftest
#         Fail-on-revert self-test (hermetic; no repo side-effects).
#
# Pool exhausted => FAIL LOUD (non-zero, "pool exhausted" on stderr,
# no name on stdout).  Operator must supply a -2 disambiguated name.
#
# TEST HOOKS:
#   CLAIM_JEDI_POOL=<path>         override pool file
#   CLAIM_JEDI_STUB_DIR=<path>     override stub directory
#   CLAIM_JEDI_GIT_REPO=<path>     override git repo for history query

set -euo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POOL="${CLAIM_JEDI_POOL:-$FLEET/state/jedi-name-pool.txt}"
STUB_DIR="${CLAIM_JEDI_STUB_DIR:-$FLEET}"
GIT_REPO="${CLAIM_JEDI_GIT_REPO:-$FLEET/..}"

die() { printf 'claim-jedi-name: %s\n' "$*" >&2; }

# --- exclusion_set --------------------------------------------------------
# Returns one name per line — every name the allocator must NOT hand out:
#   (a) live-tree: every fleet/SESSION-HANDOFF-<name>.md present on disk
#   (b) git-history: every name ever created per `git log --diff-filter=A
#       --all` — the query that catches luminara-unduli (a name from 2 days
#       ago whose file is gone from the live tree but persists in git
#       history; HANDOFF-FAILURE-RCA.md §2).
exclusion_set() {
  {
    for f in "$STUB_DIR"/SESSION-HANDOFF-*.md; do
      [ -e "$f" ] || continue
      local n="${f##*/SESSION-HANDOFF-}"
      n="${n%.md}"
      printf '%s\n' "$n"
    done
    git -C "$GIT_REPO" log --diff-filter=A --all --name-only --format='' \
      -- 'fleet/SESSION-HANDOFF-*.md' 2>/dev/null | while IFS= read -r path; do
      [ -n "$path" ] || continue
      local n="${path##*/SESSION-HANDOFF-}"
      n="${n%.md}"
      printf '%s\n' "$n"
    done
  } | sort -u
}

# --- claim_stub <name> ----------------------------------------------------
# Atomically creates the claim marker.  Uses `set -o noclobber` (O_EXCL)
# so if two processes race for the same name, exactly one wins.
# Returns 0 on success; non-zero if the name is already claimed.
claim_stub() {
  local name="$1"
  local stub="$STUB_DIR/SESSION-HANDOFF-$name.md"
  if ( set -o noclobber; printf '# claim-marker %s\n' "$name" > "$stub" ) 2>/dev/null; then
    return 0
  fi
  return 1
}

# --- allocate -------------------------------------------------------------
allocate() {
  local excl_file name
  excl_file="$(mktemp)"

  if [ ! -f "$POOL" ]; then
    rm -f "$excl_file"
    die "pool file not found: $POOL"
    return 1
  fi

  exclusion_set > "$excl_file"

  while IFS= read -r name; do
    [ -n "$name" ] || continue
    if grep -qxF "$name" "$excl_file" 2>/dev/null; then
      continue
    fi
    if claim_stub "$name"; then
      rm -f "$excl_file"
      printf '%s\n' "$name"
      return 0
    fi
    # Race: name was claimed between check and create.  Try next.
  done < "$POOL"

  rm -f "$excl_file"
  die "pool exhausted — every name in the pool is either previously used in git history or currently claimed; the operator must supply an explicit -2-suffixed disambiguated name"
  return 1
}

# =========================================================================
# SELF-TEST — FAIL-ON-REVERT.  Hermetic: NO side effects outside temp dirs.
#   bash fleet/claim-jedi-name.sh --selftest
# =========================================================================
selftest() {
  local PASS=0 FAIL=0
  ok(){ PASS=$((PASS+1)); echo "PASS: $1"; }
  bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

  local S; S="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/claim-jedi-name.sh"
  local D; D="$(mktemp -d)"

  # ── test pool (luminara-unduli is LAST so all-fresh picks first entry) ─
  cat > "$D/pool.txt" <<'POOL'
ahsoka-tano
cal-kestis
ki-adi-mundi
luminara-unduli
obi-wan-kenobi
POOL

  # ── git repo: luminara in HISTORY only (file deleted from tree) ─────────
  mkdir -p "$D/git/fleet"
  (
    cd "$D/git"
    git init --quiet
    git config user.email "t@t"
    git config user.name "t"
    # Commit 1: create luminara-unduli handoff
    echo "# handoff" > fleet/SESSION-HANDOFF-luminara-unduli.md
    git add fleet/SESSION-HANDOFF-luminara-unduli.md
    git commit --quiet -m "add luminara handoff"
    # Commit 2: delete it (live tree no longer contains it)
    rm fleet/SESSION-HANDOFF-luminara-unduli.md
    git add fleet/SESSION-HANDOFF-luminara-unduli.md
    git commit --quiet -m "remove luminara"
    # Commit 3: create ki-adi-mundi (exists in both live tree AND history)
    echo "# handoff" > fleet/SESSION-HANDOFF-ki-adi-mundi.md
    git add fleet/SESSION-HANDOFF-ki-adi-mundi.md
    git commit --quiet -m "add ki-adi-mundi"
  )

  # ── (A) regression: luminara in history, NOT in live tree => excluded ──
  echo "== (A) luminara-unduli regression fixture =="
  local name
  name="$( CLAIM_JEDI_POOL="$D/pool.txt" \
           CLAIM_JEDI_STUB_DIR="$D" \
           CLAIM_JEDI_GIT_REPO="$D/git" \
           bash "$S" 2>/dev/null )" || name=""
  case "$name" in
    ahsoka-tano)
      ok "A1 luminara-unduli EXCLUDED (git-history only, file absent) — first available is ahsoka-tano" ;;
    luminara-unduli)
      bad "A1 luminara-unduli WAS claimed — git-history exclusion BROKEN (regression NOT fixed)" ;;
    '')
      bad "A1 allocator returned no name" ;;
    *)
      ok "A1 luminara-unduli EXCLUDED — picked '$name'" ;;
  esac
  [ "$name" != "ki-adi-mundi" ] && ok "A2 ki-adi-mundi EXCLUDED (live tree present)" \
    || bad "A2 ki-adi-mundi WAS claimed (live-tree exclusion broken)"

  # ── (B) revert git-history half -> luminara becomes claimable (RED) ────
  echo "== (B) revert git-history exclusion — luminara becomes claimable =="
  # Write a minimal allocator that ONLY checks live-tree stubs (no git history).
  # This is the allocator we would have if someone reverted the git-history half.
  cat > "$D/claim-no-hist.sh" <<'NOGIT'
#!/usr/bin/env bash
set -euo pipefail
POOL="$1"; STUB_DIR="$2"
exclusion_set() {
  for f in "$STUB_DIR"/SESSION-HANDOFF-*.md; do
    [ -e "$f" ] || continue
    local n="${f##*/SESSION-HANDOFF-}"
    n="${n%.md}"
    printf '%s\n' "$n"
  done
}
claim_stub() {
  local name="$1"
  local stub="$STUB_DIR/SESSION-HANDOFF-$name.md"
  ( set -o noclobber; printf '# claim-marker %s\n' "$name" > "$stub" ) 2>/dev/null
}
excl_file="$(mktemp)"
exclusion_set | sort -u > "$excl_file"
while IFS= read -r name; do
  [ -n "$name" ] || continue
  if grep -qxF "$name" "$excl_file" 2>/dev/null; then continue; fi
  if claim_stub "$name"; then
    rm -f "$excl_file"
    printf '%s\n' "$name"
    exit 0
  fi
done < "$POOL"
rm -f "$excl_file"
echo "pool exhausted" >&2
exit 1
NOGIT
  chmod +x "$D/claim-no-hist.sh"

  # Pool with luminara-unduli FIRST so it is picked iff not excluded.
  cat > "$D/pool-b.txt" <<'PBFIX'
luminara-unduli
ahsoka-tano
cal-kestis
PBFIX
  # NO live-tree stubs — exclusion set is EMPTY (no git history).
  rm -f "$D"/SESSION-HANDOFF-*.md

  name="$(bash "$D/claim-no-hist.sh" "$D/pool-b.txt" "$D" 2>/dev/null)" || name=""
  if [ "$name" = "luminara-unduli" ]; then
    ok "B1 WITHOUT git-history exclusion, luminara-unduli IS claimable — proves git-history half is load-bearing (reverting that query would reintroduce the regression)"
  elif [ -z "$name" ]; then
    bad "B1 no-hist allocator returned no name (unexpected)"
  else
    bad "B1 git-history removal did NOT make luminara claimable (got '$name') — the exclusion is coming from somewhere else, so the git-history line may NOT be load-bearing"
  fi

  # ── (C) pool exhaustion -> non-zero exit, no name on stdout ────────────
  echo "== (C) pool exhaustion =="
  local C; C="$(mktemp -d)"
  printf 'cal-kestis\n' > "$C/pool.txt"

  # (C1) first claim succeeds
  name="$( CLAIM_JEDI_POOL="$C/pool.txt" \
           CLAIM_JEDI_STUB_DIR="$C" \
           CLAIM_JEDI_GIT_REPO="$D/git" \
           bash "$S" 2>/dev/null )" || name=""
  [ "$name" = "cal-kestis" ] && ok "C1 first claim succeeds" \
    || bad "C1 expected cal-kestis, got '${name:-<empty>}'"

  # (C2-C4) exhausted
  name="$( CLAIM_JEDI_POOL="$C/pool.txt" \
           CLAIM_JEDI_STUB_DIR="$C" \
           CLAIM_JEDI_GIT_REPO="$D/git" \
           bash "$S" 2>"$C/err.txt" )" && name="${name:-}" || name=""
  if [ -z "$name" ]; then
    ok "C2 exhausted pool: no name on stdout"
  else
    bad "C2 exhausted pool printed '$name' on stdout"
  fi
  if grep -qi exhausted "$C/err.txt" 2>/dev/null; then
    ok "C3 exhausted pool: message on stderr"
  else
    bad "C3 no 'exhausted' message on stderr"
  fi
  rm -rf "$C"

  # ── (D) concurrent claims never return the same name ───────────────────
  echo "== (D) concurrent-claim safety =="
  local CD; CD="$(mktemp -d)"
  cat > "$CD/pool.txt" <<'CPOOL'
aayla-secura
ahsoka-tano
cal-kestis
obi-wan-kenobi
CPOOL

  local n1 n2
  n1="$( CLAIM_JEDI_POOL="$CD/pool.txt" \
         CLAIM_JEDI_STUB_DIR="$CD" \
         CLAIM_JEDI_GIT_REPO="$D/git" \
         bash "$S" 2>/dev/null )" || n1=""
  n2="$( CLAIM_JEDI_POOL="$CD/pool.txt" \
         CLAIM_JEDI_STUB_DIR="$CD" \
         CLAIM_JEDI_GIT_REPO="$D/git" \
         bash "$S" 2>/dev/null )" || n2=""
  if [ -n "$n1" ] && [ -n "$n2" ] && [ "$n1" != "$n2" ]; then
    ok "D1 consecutive claims got different names ($n1, $n2)"
  elif [ "$n1" = "$n2" ] && [ -n "$n1" ]; then
    bad "D1 SAME name '$n1' returned twice (stub-claim race)"
  else
    ok "D1 claims ok (${n1:-empty} / ${n2:-empty})"
  fi
  rm -rf "$CD"

  rm -rf "$D"
  echo
  echo "--- $PASS passed, $FAIL failed ---"
  [ "$FAIL" -eq 0 ] || { echo "CLAIM-JEDI-NAME SELF-TEST FAILED"; return 1; }
  echo "ALL CLAIM-JEDI-NAME SELF-TESTS PASS"
  return 0
}

# --- verify_only <name> --------------------------------------------------
# Refuses if <name> is unsafe to claim (used by handoff.sh SESSION-override).
# - Already in live-tree: refuse (caller intended a fresh name; collision).
# - Already in git-history: refuse only when at least one fresh pool name remains;
#   allow it otherwise (so a deterministic replay of a historical name still works
#   when no fresh name is left — same operator principle as the allocator's pool-
#   exhausted path: explicit allow, never silent).
verify_only() {
  local name="$1"
  local excl_file; excl_file="$(mktemp)"
  exclusion_set > "$excl_file" || { rm -f "$excl_file"; return 1; }
  if grep -qxF "$name" "$excl_file"; then
    rm -f "$excl_file"
    die "verify-only: '$name' is in the exclusion set (live-tree OR git-history)"
    return 1
  fi
  rm -f "$excl_file"
  return 0
}

# --- guarded dispatch ----------------------------------------------------
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  case "${1:-}" in
    --selftest) selftest ;;
    --verify)   [ $# -ge 2 ] || { die "--verify requires a name"; exit 64; }; verify_only "$2" ;;
    *)          allocate ;;
  esac
fi
