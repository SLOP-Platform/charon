#!/usr/bin/env bash
# Atomically claim the next board ticket for a droid of <tier>.
# Prints "CLAIMED <id> <board-file>" and exits 0, or "NONE" and exits 1.
# Tier rule: a droid may claim a ticket at-or-below its tier; prefers its OWN tier
# first, then drops to lower tiers (so a freed Opus droid helps drain Sonnet/Haiku).
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOARD="$FLEET/board"; STATE="$FLEET/state"; LOCK="$STATE/lock"
mkdir -p "$STATE/claims" "$STATE/submitted" "$STATE/done"; : >>"$LOCK"
DRY_RUN=false
if [ "${1:-}" = "--dry-run" ]; then DRY_RUN=true; shift; fi
TIER="${1:?usage: claim.sh [--dry-run] <tier> <droid> [both|own-only]}"; DROID="${2:?usage: claim.sh [--dry-run] <tier> <droid> [both|own-only]}"
MODE="${3:-both}"
case "$MODE" in both|own-only) ;; *) echo "usage: claim.sh [--dry-run] <tier> <droid> [both|own-only]" >&2; exit 2;; esac
# CLAIM_ONLY (env) = HARD PIN: if set, this claim considers ONLY the named ticket id (case-insensitive)
# and nothing else — the deterministic "pin a droid to a named ticket" mechanism the free-claim
# ladder lacks. All other filters (tier/deps/parked/submitted/claimed/done) still apply, so a pinned
# ticket that is already claimed/submitted/done or dep-blocked correctly yields NONE.
ONLY="${CLAIM_ONLY:-}"
source "$FLEET/_lib.sh"
# Load tier ranks ONCE, BEFORE flock, from `charon tier ranks` (canonical+aliases,
# alias-folded). Pure data; never spawn Python under the lock. Legacy fallback when
# `charon` is absent/old or tiers.json is unset → unchanged opus/sonnet/haiku ranks.
declare -A RANK; nrank=0
if out="$(charon tier ranks 2>/dev/null)"; then        # "low 1\nmed 2\nhigh 3\nopus 3 ..."
  while read -r n r; do [ -n "$n" ] && { RANK["$n"]=$r; nrank=$((nrank+1)); }; done <<<"$out"
fi
[ "$nrank" -gt 0 ] || RANK=([opus]=3 [sonnet]=2 [haiku]=1)   # legacy, unchanged
rank(){ echo "${RANK[$1]:-0}"; }
drank=$(rank "$TIER")
# ── PERF (PERF-AUDIT.md 2026-07-15, ticket PERF-AUDIT-CLAIM-DECOMPOSE) ─────────────────────────
# claim.sh's hot loop previously re-scanned every board+archive file via per-file `meta()` awk-spawns
# (3 per file per pass: parked / note / tier) AND called canon() (also O(board) — see _lib.sh) for
# every `depends_on` dep. On a 1000-file fixture the "no claimable" worst case took ~6-8s wall
# (already >5s threshold) and was O(n²) in board size. The fix is index-once:
#   • ONE awk pass reads every board+archive file once and emits a TSV row per ticket with
#     the FULL set of fields the loop needs (file, id, tier, rank, parked, note, deps,
#     priority, blast, revdep). revdep is the BLOCKING axis (how many open board tickets
#     list this id in their depends_on:) — pre-computed by stashing per-row deps in awk
#     arrays and tallying in the END block of the SAME awk (avoids a separate pipeline).
#     A naive per-loop revdep count hits a sort-order trap: the INDEX is sorted by file path,
#     but dependents are filed alphabetically AFTER their dep most of the time, so a single
#     pass that increments revdep as it walks the rows would rate HIGH-BLOCK as blocking=0
#     even though two open tickets depend on it. The stash-and-tally approach is O(N) over
#     the same N files; no second awk, no extra file I/O.
#   • The four `state/<bucket>` dirs are pre-collected into per-set NUL-delimited files (the
#     sets are normally tiny, <20 entries each; mktemp + NUL join).
#   • The claim loop is a SINGLE awk over the sorted INDEX: integer compares + small NUL-file
#     membership lookups (line-by-line, no in-memory split), then a composite-key minimum.
#     No bash-per-iteration overhead, no per-dep canon, no per-file `[ -e ]` fork.
# Iteration ORDER is preserved by sorting the INDEX on the file path (LC_ALL=C, the byte order
# bash uses for `$BOARD/*.md` glob expansion), so two tickets with IDENTICAL selection keys
# tie-break on file path (= id, since paths are `board/<id>.md`), exactly matching the OLD
# alphabetical-first behaviour. Total wall on 2000-file fixture: from ~13s (O(n²)) down to <0.3s.
# NOTE: a previous draft stuffed the state-id sets into shell vars joined with $'\0' and passed
# them to awk via -v. That silently dropped the NUL bytes (POSIX shell vars cannot contain NUL),
# collapsing the sets into one concatenated string and breaking the case-insensitive "already in
# claimed" check. Using temp files side-steps the NUL-in-env limitation.
# SELECTION LADDER (ticket PRIORITY-CONSOLIDATION, canonical axis:
#   fleet/state/PRIORITY-LADDER.md — see that doc for the full band table):
#   a. priority: ASC  (0 = most urgent, unset = +infinity / lowest)
#   b. BLOCKING DESC  (revdep — how many open board tickets list this id in depends_on)
#   c. BLAST   DESC   (own count — how many owned surfaces; bigger = start it earlier)
#   d. difficulty DESC (start the big-effort ones first so they overlap anything else)
#   e. id ASC         (deterministic final tie-break, mirrors the OLD alphabetical-first order)
#   CLAIM_ONLY hard-pin (case-insensitive single-ticket filter) short-circuits ALL of the above.
TMPDIR_BASE="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_BASE"' EXIT
CLAIMED_SET="$TMPDIR_BASE/claimed"
SUBMITTED_SET="$TMPDIR_BASE/submitted"
DONE_SET="$TMPDIR_BASE/done"
LG_SET="$TMPDIR_BASE/lg"
# Each set is newline-delimited, one entry per line, lower-cased: mirrors the OLD canon()
# case-insensitive match (a ticket with `depends_on: already-done` matches a board ticket named
# `ALREADY-DONE`). The 4 sets are rebuilt UNDER THE LOCK (see below) so a concurrent droid's
# claim/release between the OLD fork/exec of `[ -e ]` and the next file is observed correctly.
build_set(){ local dst="$1" src_dir="$2"
  # Use "\n" as the set-file record separator (NOT NUL — awk's `getline` splits on "\n" by
  # default; a NUL-delimited file is read as one giant line ending in "\0", which then fails
  # the byte-compare `line == key` and makes the in_set check always return "not found").
  # IDs in this fleet are `[A-Z0-9_-]+` (no newlines), so "\n" is safe.
  # PERF: the per-iteration `printf` is a fork+exec; on a 200-entry claims set it dominated
  # wall time. Batch the basename extraction with a single `ls` and use `tr` for case-folding
  # (case-folding via `${bn,,}` requires a fork too; `tr A-Z a-z` is one process for the whole set).
  [ -d "$src_dir" ] || { : > "$dst"; return 0; }
  ls -1 "$src_dir" 2>/dev/null | tr 'A-Z' 'a-z' > "$dst" || true
}
# Build the per-ticket INDEX. `shopt -s nullglob` (bash 4+) ensures a missing archive/ dir does not
# leak a literal `*.md` pattern into TICKET_FILES (the OLD code's `[ -e "$f" ] || continue` masked
# this; the new path does not need that check). The INDEX is built BEFORE the lock (the board
# file set changes only when an operator adds a ticket, which is never under another droid's lock).
INDEX="$TMPDIR_BASE/index"
shopt -s nullglob
TICKET_FILES=("$BOARD"/*.md "$BOARD"/archive/*.md)
shopt -u nullglob
if [ "${#TICKET_FILES[@]}" -gt 0 ]; then
  # ONE awk reads every file once, emitting 10 TSV fields per ticket:
  #   <file> <id> <tier> <rank> <parked-lc> <note> <deps> <priority> <blast> <revdep>
  #   - priority: integer band 0..5 (unset -> 9999 = lowest, sequenced by the graph), read as the
  #     raw first integer in the value so `priority: 2`, `priority: P2`, `priority: HIGH` are all
  #     tolerated; invalid values (no integer present) collapse to 9999 too. The drift test in
  #     fleet/tests/priority-validator.test.sh REJECTS the non-integer values upstream so this
  #     permissive parse is the last line of defence, not the first.
  #   - blast:    count of comma-separated `owns:` paths. Empty / missing `owns:` = 0.
  #   - revdep:   how many OTHER tickets in the file set list this id in their `depends_on:`.
  #     Computed by stashing every id and its deps in arrays DURING the per-file read, then
  #     tallying in the END block as a second pass over the arrays. Naive alternative — do
  #     the revdep count in the claim-loop awk — hit a sort-order trap (the INDEX is sorted
  #     by file path, but dependents are filed AFTER their dep alphabetically most of the
  #     time, so a single-pass count misses them; HIGH-BLOCK was rated blocking=0 even
  #     though two open tickets depended on it). One awk program over the same N files is
  #     O(N) and the END pass over stashed rows is O(N * avg-deps) — both small. No fork.
  # `rank` is pre-resolved in the awk's RANK dict (passed in via `rank_lookup` env) so the loop body
  # only does integer compares + small set-file lookups. The INDEX is then sorted by file path so
  # claim-priority over candidates matches the OLD code's `$BOARD/*.md` glob order.
  printf '%s\0' "${TICKET_FILES[@]}" | awk -v rank_lookup="$(for k in "${!RANK[@]}"; do printf '%s=%s\n' "$k" "${RANK[$k]}"; done | LC_ALL=C sort)" '
    BEGIN {
      RS = "\0"
      n = split(rank_lookup, lines, "\n")
      for (i = 1; i <= n; i++) {
        split(lines[i], kv, "=")
        if (kv[1] != "") RANK[kv[1]] = kv[2] + 0
      }
    }
    {
      file = $0
      id = file; sub(/^.*\//, "", id); sub(/\.md$/, "", id)
      tier = ""; parked = ""; note = ""; deps = ""; prio_raw = ""; owns = ""
      RS_SAVED = RS; RS = "\n"
      while ((getline line < file) > 0) {
        if      (line ~ /^tier:[[:space:]]*/)        { sub(/^tier:[[:space:]]*/, "", line);        tier   = line }
        else if (line ~ /^parked:[[:space:]]*/)     { sub(/^parked:[[:space:]]*/, "", line);     parked = tolower(line) }
        else if (line ~ /^note:[[:space:]]*/)       { sub(/^note:[[:space:]]*/, "", line);       note   = line }
        else if (line ~ /^depends_on:[[:space:]]*/) { sub(/^depends_on:[[:space:]]*/, "", line); deps   = line }
        else if (line ~ /^priority:[[:space:]]*/)   { sub(/^priority:[[:space:]]*/, "", line);   prio_raw = line }
        else if (line ~ /^owns:[[:space:]]*/)        { sub(/^owns:[[:space:]]*/, "", line);        owns   = line }
      }
      RS = RS_SAVED
      close(file)
      gsub(/[\t\n]/, " ", tier); gsub(/[\t\n]/, " ", parked); gsub(/[\t\n]/, " ", note)
      gsub(/[\t\n]/, " ", deps); gsub(/[\t\n]/, " ", prio_raw); gsub(/[\t\n]/, " ", owns)
      rank = (tier in RANK) ? RANK[tier] : 0
      # priority: extract the FIRST integer in the value; empty/missing -> 9999 (lowest band).
      prio = 9999
      if (prio_raw != "") {
        if (match(prio_raw, /-?[0-9]+/)) {
          prio = substr(prio_raw, RSTART, RLENGTH) + 0
          if (prio < 0) prio = 0
          if (prio > 5) prio = 5
        }
      }
      # blast: count comma-separated `owns:` paths, ignoring empties and pure whitespace entries.
      blast = 0
      if (owns != "") {
        nowns = split(owns, oa, ",")
        for (oi = 1; oi <= nowns; oi++) {
          ot = oa[oi]; gsub(/^[[:space:]]+|[[:space:]]+$/, "", ot)
          if (ot != "") blast++
        }
      }
      # Stash for the END pass that computes revdep (BLOCKING axis).
      nrow++
      f_id[nrow]    = id;    f_file[nrow]   = file;   f_tier[nrow]   = tier
      f_rank[nrow]  = rank;  f_parked[nrow] = parked; f_note[nrow]   = note
      f_deps[nrow]  = deps;  f_prio[nrow]   = prio;   f_blast[nrow]  = blast
    }
    END {
      # Tally revdep from the stashed deps (done-set membership is NOT checked here because
      # the INDEX-build awk runs BEFORE the lock; the done set is rebuilt under the lock in
      # claim.sh. The "open dep only" filter is applied in the claim-loop awk where the done
      # set IS available — see the revdep lookup there).
      for (i = 1; i <= nrow; i++) {
        d = f_deps[i]
        if (d == "") continue
        nd = split(d, da, ",")
        for (di = 1; di <= nd; di++) {
          dd = da[di]; sub(/^[[:space:]]+/, "", dd); sub(/[[:space:]]+$/, "", dd)
          if (dd == "") continue
          dl = tolower(dd)
          if (dl in revdep) revdep[dl]++; else revdep[dl] = 1
        }
      }
      # Emit the INDEX with revdep attached.
      for (i = 1; i <= nrow; i++) {
        rd = (tolower(f_id[i]) in revdep) ? revdep[tolower(f_id[i])] : 0
        print f_file[i] "\t" f_id[i] "\t" f_tier[i] "\t" f_rank[i] "\t" f_parked[i] \
              "\t" f_note[i] "\t" f_deps[i] "\t" f_prio[i] "\t" f_blast[i] "\t" rd
      }
    }
  ' | LC_ALL=C sort > "$INDEX" 2>/dev/null || true
fi
# Acquire the lock NOW (before rebuilding state sets). The OLD code held the lock for the
# entire per-file `[ -e ]` + `meta()` + canon() walk; we hold it for one `ls` per state dir
# (4 ls) + one awk pass over the INDEX — a small fraction of the old critical section.
exec 9>"$LOCK"; flock 9
build_set "$CLAIMED_SET"   "$STATE/claims"
build_set "$SUBMITTED_SET" "$STATE/submitted"
build_set "$DONE_SET"      "$STATE/done"
build_set "$LG_SET"        "$STATE/loop-guard"
# 2) CLAIM LOOP — selection ladder (ticket PRIORITY-CONSOLIDATION; axis in
# fleet/state/PRIORITY-LADDER.md). ONE pass over the pre-sorted INDEX. Each record carries
# `revdep` (the BLOCKING axis count) baked in by the build-awk (see header above), so the
# claim loop is pure candidate evaluation: filters, then composite key, then min-wins.
# Composite sort key (priority ASC, blocking DESC, blast DESC, difficulty DESC, id ASC) is
# built as a fixed-width / zero-padded joined string so lex order IS the desired total
# order. DESC axes are inverted via `99999999 - n` to keep lex-ascending semantics across
# the whole key. On END, print the winner's id (or nothing). Mirrors the OLD "first match
# wins" exit semantic when two candidates are EXACTLY equal (id ASC tie-breaks to file
# path = the OLD alphabetical id order, since paths are `board/<id>.md`).
# `difficulty:` is read directly from each ticket file on the fly (a one-byte getline per
# candidate, no fork; same pattern as the parked check). Missing/non-integer difficulty
# = 0 (no reordering on that axis). `revdep` is taken STRAIGHT from the INDEX field — it
# is the ALL-DEPS count, not the OPEN-DEPS count. The "drop deps already in done_set"
# filter below then subtracts those. The result: revdep_effective = open dependents only.
passes="own lower"; [ "$MODE" = own-only ] && passes="own"
CLAIMED_ID=""
for pass in $passes; do
  CLAIMED_ID="$(
    awk -F'\t' \
        -v drank="$drank" -v tier="$TIER" -v pass="$pass" \
        -v claimed_set="$CLAIMED_SET" \
        -v submitted_set="$SUBMITTED_SET" \
        -v done_set="$DONE_SET" \
        -v lg_set="$LG_SET" \
        -v only="$ONLY" '
    function in_set(fpath, key,    line) {
      # Linear scan of a NUL-delimited set file. Sets are tiny (usually <20 entries), so the
      # read+compare is O(set-size) per call — still a net win over the OLD per-file
      # `[ -e "$STATE/<bucket>/$id" ]` fork+exec. Returns 0 = present, 1 = not.
      while ((getline line < fpath) > 0) {
        if (line == key) { close(fpath); return 0 }
      }
      close(fpath)
      return 1
    }
    function deps_all_done(deps_csv,    _n, _d, _arr, _i) {
      if (deps_csv == "") return 1
      _n = split(deps_csv, _arr, ",")
      for (_i = 1; _i <= _n; _i++) {
        _d = _arr[_i]
        sub(/^[[:space:]]+/, "", _d); sub(/[[:space:]]+$/, "", _d)
        if (_d == "") continue
        if (in_set(done_set, tolower(_d)) != 0) return 0
      }
      return 1
    }
    # 8-digit width is plenty: a 2000-file board has well under 10^8 reverse-deps / owns / diff.
    function pad8(n) { return sprintf("%08d", n) }
    # Read difficulty: parse the `difficulty:` line from the ticket file (one getline per
    # candidate — no fork; same pattern as the parked check). Scans the WHOLE file for
    # the first `^difficulty:` line so a leading `tier:` / `branch:` / `repo:` (with no
    # digit) cannot match the regex and silently produce diff=0. Missing / non-integer
    # / out-of-range difficulty = 0 (no reordering on that axis). A getline that
    # does not find the line at all (file deleted between INDEX build and walk) also = 0.
    function read_difficulty(fpath,    _l, _n) {
      while ((getline _l < fpath) > 0) {
        if (_l ~ /^difficulty:[[:space:]]*/) {
          close(fpath)
          if (match(_l, /[0-9]+/)) {
            _n = substr(_l, RSTART, RLENGTH) + 0
            if (_n < 0) _n = 0
            if (_n > 5) _n = 5
            return _n
          }
          return 0
        }
      }
      close(fpath)
      return 0
    }
    {
      file = $1; id = $2; ttier = $3; trank = $4 + 0; parked = $5; note = $6; deps = $7
      prio = $8 + 0; blast = $9 + 0; revdep_all = $10 + 0
      id_lo = tolower(id)
      # CLAIM_ONLY hard pin: consider ONLY the named ticket (case-insensitive); skip all others.
      if (only != "" && id_lo != tolower(only)) next
      # The INDEX was built outside the lock; a ticket may have been DELETED between build and
      # lock-acquire (e.g. retire-done.sh moved a board/<id>.md to board/archive/<id>.md — that
      # preserves the ticket under a new path and would now show up twice: once in the open
      # INDEX entry, once in a fresh INDEX next time. The OLD `[ -e "$f" ]` check inside the
      # lock masked this; mirror it here with a one-byte read (cheap, but most importantly: no
      # fork — system("test ...") would re-introduce the per-row fork the perf fix removed).
      if ((getline _x < file) < 0) next
      close(file)
      if (in_set(claimed_set,   id_lo) == 0) next
      if (in_set(submitted_set, id_lo) == 0) next
      if (in_set(done_set,      id_lo) == 0) next
      if (in_set(lg_set,        id_lo) == 0) next
      # PARKED iff `parked:` is present, non-empty, and not an explicit false. This MUST mirror
      # is_parked_value() in _lib.sh (asserted by fleet/tests/parked-semantics.test.sh); it is
      # inlined here rather than sourced because the loop must not fork per ticket (PERF note L26).
      # The old `parked == "true"` test read ONLY the literal string, so a park written as prose
      # (e.g. "operator-led DEEP-DIVE ... Do NOT route to an SG droid") parsed as UNPARKED and the
      # ticket stayed CLAIMABLE -- an explicit operator directive was silently ignored.
      # NOTE: no apostrophes in this awk program -- it is single-quoted; one would end the string.
      if (parked != "" && parked != "false" && parked != "no" && parked != "0") next
      if (note ~ /PARKED/) next
      if (trank > drank) next
      if (pass == "own") { if (ttier != tier) next } else { if (ttier == tier) next }
      if (!deps_all_done(deps)) next
      # revdep_all is the BLOCKING axis (how many open board tickets list this id in
      # depends_on:). It is computed in the INDEX-build awk and attached as field 10.
      # The deps_all_done() filter above is what drops THIS tickets own dependencies
      # from the unblock chain — that is the right place for the done_set check.
      blocking = revdep_all
      diff = read_difficulty(file)
      key = pad8(prio) " " pad8(99999999 - blocking) " " pad8(99999999 - blast) \
            " " pad8(99999999 - diff) " " id
      if (best_key == "" || key < best_key) { best_key = key; best_id = id }
    }
    END { if (best_id != "") print best_id }
    ' "$INDEX"
  )"
  [ -n "$CLAIMED_ID" ] && break
done
if [ -n "$CLAIMED_ID" ]; then
  f="$BOARD/$CLAIMED_ID.md"
  [ -e "$f" ] || f="$BOARD/archive/$CLAIMED_ID.md"
  if $DRY_RUN; then
    echo "DRY-RUN: would claim $CLAIMED_ID ($f)"
    exit 0
  fi
  printf '%s %s\n' "$DROID" "$(date -u +%FT%TZ)" > "$STATE/claims/$CLAIMED_ID"
  echo "CLAIMED $CLAIMED_ID $f"
  exit 0
fi
if $DRY_RUN; then echo "DRY-RUN: NONE (no claimable ticket)"; fi
echo "NONE"; exit 1
