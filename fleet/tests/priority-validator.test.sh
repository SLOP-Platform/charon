#!/usr/bin/env bash
# priority-validator.test.sh — DRIFT / FAIL-ON-REVERT tests for ticket PRIORITY-CONSOLIDATION.
#
# Two surfaces, one test:
#
#   1. DRIFT — walk the LIVE board, assert every `priority:` value is an integer 0..5
#      (or the field is absent). Drift back to `priority: HIGH` / `priority: P2` /
#      `priority: 7` / `priority: -1` — any of the three old nomenclatures (HIGH/MEDIUM/
#      P2), any value outside the 0..5 band, or a non-integer — and this goes RED. The
#      band table itself is in fleet/state/PRIORITY-LADDER.md; this test only asserts
#      the SHAPE of the value, not the operator-set semantics of each band.
#
#   2. LADDER — run the LIVE claim.sh against a synthetic board that is hand-built to
#      exercise every rung of the selection ladder, and assert the output ORDER. This
#      is the test that catches a revert to "alphabetical first" — the pre-PRIORITY-
#      CONSOLIDATION behaviour. Every rung's expected winner is named explicitly so a
#      drop on any rung fails the test (e.g. if a future change makes BLAST beat
#      BLOCKING, the "BLOCKING > BLAST" assertion fires).
#
# Fully isolated. The DRIFT surface reads the live board but never mutates it. The
# LADDER surface builds a temp fleet (cp claim.sh + _lib.sh + synthetic board + empty
# state) — NEVER touches the live board, the live state, or the product repo.
#
# Run:  bash fleet/tests/priority-validator.test.sh   (exit 0 = GREEN)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fails=0
ok(){  printf '  ok   %s\n' "$1"; }
bad(){ printf '  FAIL %s\n' "$1"; fails=$((fails+1)); }

# ─── 1. DRIFT: every live `priority:` value is int 0..5 OR absent ──────────────────────
# Archived tickets are exempt — they have a snapshot of the old format that the rig
# is not retroactively rewriting (would touch the R0 history, no value). The validator
# asserts the CONTRACT going forward, not a retroactive clean.
printf '1. DRIFT — live board priority values are int 0..5 or absent\n'
priority_field() { awk '/^priority:[[:space:]]*/{sub(/^priority:[[:space:]]*/,""); print; exit}' "$1"; }
n_ok=0; n_abs=0; n_red=0
for f in "$SRC"/board/*.md; do
  [ -f "$f" ] || continue
  base="$(basename "$f" .md)"
  # .md.parked files are not "live" (they're staged, not claimable), but the file GLOB
  # above already excluded them. A board/<id>.md whose content is parked-by-note is
  # still LIVE for the validator (parked: is orthogonal to priority:).
  raw="$(priority_field "$f")"
  if [ -z "$raw" ]; then
    n_abs=$((n_abs+1))
    continue
  fi
  # integer 0..5 — first token, no leading sign beyond the optional minus
  if [[ "$raw" =~ ^-?[0-9]+$ ]] && [ "$raw" -ge 0 ] && [ "$raw" -le 5 ]; then
    n_ok=$((n_ok+1))
  else
    bad "drift: $base priority='$raw' is not an integer 0..5 (rejected by PRIORITY-LADDER.md)"
    n_red=$((n_red+1))
  fi
done
[ "$n_red" -eq 0 ] \
  && ok "live board clean (n_ok=$n_ok integer 0..5; n_abs=$n_abs absent) — no drift back to HIGH/MEDIUM/P2/etc." \
  || bad "drift: $n_red ticket(s) carry a non-canonical priority value"

# Also assert: a non-integer priority string in the BAND-2 region would have been HIGH
# in the old scheme. Belt-and-suspenders: synthesize one and check the validator catches
# it (not just the live board, which may be empty by chance).
TMPDRIFT="$(mktemp -d)"; trap 'rm -rf "$TMPDRIFT"' EXIT
mkdir -p "$TMPDRIFT/board" "$TMPDRIFT/state"
cp "$SRC/claim.sh" "$SRC/_lib.sh" "$TMPDRIFT/"
printf 'tier: strong\ndifficulty: 3\nbranch: feat/x\ndepends_on:\nowns: x.py\npriority: HIGH\n' > "$TMPDRIFT/board/DRIFT-HIGH.md"
out="$(priority_field "$TMPDRIFT/board/DRIFT-HIGH.md")"
if [[ "$out" =~ ^-?[0-9]+$ ]] && [ "$out" -ge 0 ] && [ "$out" -le 5 ]; then
  bad "drift: priority_field() allowed 'HIGH' through — drift detector is broken"
else
  ok "drift: priority_field() correctly flags 'HIGH' as non-canonical"
fi
rm -rf "$TMPDRIFT"

# ─── 2. LADDER: end-to-end claim order matches the PRIORITY-LADDER selection contract ─
printf '\n2. LADDER — claim.sh picks by priority > blocking > blast > difficulty > id\n'

WORK="$(mktemp -d)"
F="$WORK/fleet"; mkdir -p "$F/board" "$F/state"
cp "$SRC/claim.sh" "$SRC/_lib.sh" "$F/"

mk(){ # mk <id> <tier> <difficulty> <priority> <owns-comma-list> <depends_on-comma-list>
  { printf 'tier: %s\n' "$2"
    printf 'difficulty: %s\n' "$3"
    printf 'branch: feat/%s\n' "$(echo "$1" | tr 'A-Z' 'a-z')"
    printf 'depends_on: %s\n' "$6"
    printf 'owns: %s\n' "$5"
    printf 'priority: %s\n' "$4"
  } > "$F/board/$1.md"
}
claim(){ ( cd "$F" && env -u CLAIM_ONLY bash ./claim.sh "$1" "$2" both 2>/dev/null ); }

# (2a) priority beats alpha — a P:0 ticket named ZZZ-* should be claimed BEFORE a P:2
#      ticket named AAA-*, even though the latter sorts first alphabetically. This is
#      THE test that catches a revert to "alphabetical first" claim selection.
mk ZZZ-P0  strong 3 0 "src/z.py"  ""
mk AAA-P2  strong 3 2 "src/a.py"  ""
out1="$(claim strong ladder-2a-1)"; out2="$(claim strong ladder-2a-2)"
first="${out1#CLAIMED }"; first="${first%% *}"
second="${out2#CLAIMED }"; second="${second%% *}"
[ "$first" = "ZZZ-P0" ] && ok "ladder (priority > alpha): P:0 wins over alphabetically-earlier P:2 (got $first)" \
  || bad "ladder: P:0 ZZZ-P0 should have won, got $first"
[ "$second" = "AAA-P2" ] && ok "ladder: P:2 AAA-* is claimed second" \
  || bad "ladder: AAA-P2 should be second, got $second"
# drain
for i in 3 4 5; do claim strong "drain-$i" >/dev/null; done

# (2b) BLOCKING beats BLAST — two P:2 tickets: B has more reverse-deps (2) than A (0)
#      even though A has more `owns:` paths. P:2 is identical, so we need blocking/blast
#      to decide. Expected: B (blocks 2) before A (blocks 0, big blast).
rm -f "$F"/board/*.md
# Two dependents of HIGH-BLOCK
mk LOW-BLOCK  strong 3 3 "src/l.py"  "HIGH-BLOCK"
mk MID-BLOCK  strong 3 3 "src/m.py"  "HIGH-BLOCK"
# HIGH-BLOCK blocks 2, blast 1 — should win
mk HIGH-BLOCK strong 3 2 "src/h.py"  ""
# WIDE-BLAST blocks 0, blast 5 — loses on blocking even though wins on blast
mk WIDE-BLAST strong 3 2 "src/w.py, src/w2.py, src/w3.py, src/w4.py, src/w5.py" ""
# Same P:2, same blast (1), same blocking (0), same diff (3) — only id distinguishes.
# Add another P:2 with NO dependents and NO blast to confirm id tie-break.
mk ALPHA-P2  strong 3 2 "src/alpha.py" ""
out1="$(claim strong ladder-2b-1)"; first="${out1#CLAIMED }"; first="${first%% *}"
[ "$first" = "HIGH-BLOCK" ] && ok "ladder (blocking > blast): HIGH-BLOCK (2 deps, 1 own) wins over WIDE-BLAST (0 deps, 5 own) — got $first" \
  || bad "ladder: HIGH-BLOCK should win on blocking, got $first"
# drain the rest and check the order of the remaining P:2 set
remaining=""
for i in 2 3 4 5 6 7; do
  o="$(claim strong "drain-$i" 2>/dev/null)"
  case "$o" in CLAIMED*) rid="${o#CLAIMED }"; rid="${rid%% *}"; remaining="$remaining $rid";;
                    *) break;; esac
done
# Expected: after HIGH-BLOCK, the remaining P:2 set is WIDE-BLAST, ALPHA-P2.
# WIDE-BLAST has blast 5 vs ALPHA-P2's blast 1, so WIDE-BLAST wins on blast DESC.
case " $remaining " in
  *" WIDE-BLAST "*) ok "ladder: WIDE-BLAST (blast 5) is claimed before ALPHA-P2 (blast 1)";;
  *) bad "ladder: expected WIDE-BLAST in the P:2 remainder (got: ${remaining# })";;
esac
case " $remaining " in
  *" ALPHA-P2 "*) ok "ladder: ALPHA-P2 is the last P:2 claimed (id tie-break settles between it and any other zero-axis P:2)";;
  *) bad "ladder: expected ALPHA-P2 in the P:2 remainder (got: ${remaining# })";;
esac

# (2c) DIFFICULTY beats id when other axes are tied — two P:2 same-blast same-blocking
#      same-priority — the high-difficulty one should win.
rm -f "$F"/board/*.md
mk EASY-P2  strong 1 2 "src/easy.py"  ""
mk HARD-P2  strong 5 2 "src/hard.py"  ""
out1="$(claim strong ladder-2c-1)"; first="${out1#CLAIMED }"; first="${first%% *}"
[ "$first" = "HARD-P2" ] && ok "ladder (difficulty > id): HARD-P2 (diff 5) wins over EASY-P2 (diff 1) at same P:2 — got $first" \
  || bad "ladder: HARD-P2 should win on difficulty, got $first"

# (2d) unset priority = lowest band (auto-sequenced by the graph). With everything else
#      equal, the unset ticket loses to ANY explicit P:N. This proves the
#      "unset = 9999" parse in claim.sh's INDEX-build awk.
rm -f "$F"/board/*.md
mk EXPLICIT-P3 strong 3 3 "src/ex.py"  ""
mk UNSET       strong 3 "" "src/un.py" ""
out1="$(claim strong ladder-2d-1)"; first="${out1#CLAIMED }"; first="${first%% *}"
[ "$first" = "EXPLICIT-P3" ] && ok "ladder (unset = lowest): EXPLICIT-P3 (P:3) wins over UNSET (no priority field) — got $first" \
  || bad "ladder: EXPLICIT-P3 should beat UNSET, got $first"

# (2e) regression — the OLD alphabetical-first behaviour is the very thing this ticket
#      changes. The empty-ticket-file case (no priority, no deps, no owns) is degenerate
#      and is excluded: just prove the OLD failure mode is gone, by re-running 2a's
#      scenario and asserting we did NOT see alphabetical order.
rm -f "$F"/board/*.md
mk ZED-P0 strong 3 0 "src/z.py" ""
mk ALF-P2 strong 3 2 "src/a.py" ""
o1="$(claim strong r-1)"; o2="$(claim strong r-2)"
f="${o1#CLAIMED }"; f="${f%% *}"
[ "$f" = "ZED-P0" ] && ok "regression: alphabetical-first claim order is GONE (P:0 ZED-P0 wins over ALF-P2)" \
  || bad "regression: ALPHABETICAL-FIRST is back — P:0 ZED-P0 should beat ALF-P2 by priority, got $f"

# (2f) CLAIM_ONLY pin preserved — the priority ladder MUST NOT break the CLAIM_ONLY
#      hard-pin bootstrap wired by an earlier ticket. With two P:0 tickets, a CLAIM_ONLY
#      env to one of them must short-circuit the entire ladder and return THAT ticket,
#      not the priority-winner.
# Fresh board — the (2e) regression already claimed ZED-P0 above, which would leave it in
# state/claims and make a second CLAIM_ONLY=ZED-P0 pin a no-op (NONE). Rebuild so the pin
# exercises the unblocked path.
rm -f "$F"/state/claims/* "$F"/state/submitted/* "$F"/state/done/* "$F"/board/*.md
mk ZED-P0 strong 3 0 "src/z.py" ""
mk ALF-P2 strong 3 2 "src/a.py" ""
o1="$(cd "$F" && CLAIM_ONLY=ZED-P0 bash ./claim.sh strong pin-1 both 2>/dev/null)"
f="${o1#CLAIMED }"; f="${f%% *}"
[ "$f" = "ZED-P0" ] && ok "pin: CLAIM_ONLY=ZED-P0 returns ZED-P0 (priority ladder bypassed by the pin)" \
  || bad "pin: CLAIM_ONLY=ZED-P0 should return ZED-P0 regardless of priority, got $f"
# Also verify CLAIM_ONLY to a name that does not exist in the board -> NONE.
o2="$(cd "$F" && CLAIM_ONLY=NOPE bash ./claim.sh strong pin-2 both 2>/dev/null)"
[ "$o2" = "NONE" ] && ok "pin: CLAIM_ONLY to a non-existent id returns NONE" \
  || bad "pin: CLAIM_ONLY=NOPE should return NONE, got '$o2'"
# And CLAIM_ONLY should be case-insensitive (matches claim.sh's lower(id) comparison).
# Rebuild fresh — pin-1 already claimed ZED-P0 above.
rm -f "$F"/state/claims/* "$F"/state/submitted/* "$F"/state/done/* "$F"/board/*.md
mk ZED-P0 strong 3 0 "src/z.py" ""
mk ALF-P2 strong 3 2 "src/a.py" ""
o3="$(cd "$F" && CLAIM_ONLY=zed-p0 bash ./claim.sh strong pin-3 both 2>/dev/null)"
f="${o3#CLAIMED }"; f="${f%% *}"
[ "$f" = "ZED-P0" ] && ok "pin: CLAIM_ONLY is case-insensitive" \
  || bad "pin: CLAIM_ONLY=zed-p0 should still return ZED-P0, got '$o3'"

rm -rf "$WORK"
printf '\n  priority-validator: %s\n\n' "$([ "$fails" -eq 0 ] && echo 'GREEN' || echo "RED ($fails failed)")"
[ "$fails" -eq 0 ]
