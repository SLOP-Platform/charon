#!/usr/bin/env bash
# pending-labels.test.sh — FAIL-ON-REVERT self-test for fleet/pending.sh label integrity.
#
# Operates on a THROWAWAY fleet under mktemp -d (a copy of pending.sh with its own
# state/). Never touches the live operator-action list. Hermetic, offline, ~1s.
#
# WHY THIS EXISTS
#   pending.sh promises "a label is NEVER REUSED — once handed out it is retired
#   forever". That promise rested entirely on fleet/state/.operator-actions.hw,
#   which is GITIGNORED, while fleet/state/OPERATOR-ACTIONS.md is TRACKED. Losing
#   the counter while keeping the items restarted label allocation straight into
#   labels still on the board. It really happened: "#12" was issued TWICE, and
#   because cmd_done deletes with `awk '$1!=t'`, `done #12` would have wiped BOTH
#   rows — silently destroying an unrelated operator action.
#
# GREEN-IS-NOT-PROOF: exit 0 does not prove label allocation is correct in general.
# Each case below names the exact revert that must turn it RED.
#
# Covers:
#   (a) HW MISSING + live labels in LIST: `add` must not re-issue a live label.
#       Reverting hw_effective() to a bare `cat "$HW"` makes this RED.
#   (b) HW STALE (below the max label present): same guarantee.
#       Same revert makes this RED.
#   (c) DUPLICATE-LABEL FAIL-CLOSED: `done <dup>` refuses, exits non-zero, and
#       deletes NOTHING. Removing the n>1 guard in cmd_done makes this RED by
#       deleting both rows.
#   (d) ANTI-OVER-BLOCK: `done <unique-label>` still works and removes exactly one
#       row. A guard that refuses everything is as useless as no guard.
#   (e) allocation stays monotonic on a clean list (A, B, C ...) — the fix must not
#       change normal behaviour.
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/pending.sh"
[ -f "$SRC" ] || { echo "FAIL: cannot find pending.sh at $SRC"; exit 1; }

fails=0
ok(){ echo "  ok   — $1"; }
bad(){ echo "  FAIL — $1"; fails=$((fails+1)); }

# Build an isolated fleet: <tmp>/pending.sh + <tmp>/state/
newfleet(){
  local d; d="$(mktemp -d)"
  cp "$SRC" "$d/pending.sh"; mkdir -p "$d/state"; echo "$d"
}

# NOTE ON FIXTURE DESIGN: losing $HW restarts allocation at index 0 ("A"), so the
# collision only appears when the restarted counter lands on a label that is STILL
# LIVE. A fixture holding only a HIGH label (e.g. "#12" = index 37) therefore does
# NOT reproduce the bug — the next add is "A" and no duplicate occurs. The live
# label must sit AT the index the broken allocator is about to hand out.
echo "== (a) HW missing, live LOW label present -> no reuse =="
d=$(newfleet)
printf 'A\tlive item A\n#12\tlive twelve\n' > "$d/state/OPERATOR-ACTIONS.md"  # A = index 0
rm -f "$d/state/.operator-actions.hw"                                         # counter LOST
bash "$d/pending.sh" add "brand new item" >/dev/null 2>&1
dups=$(cut -f1 "$d/state/OPERATOR-ACTIONS.md" | sort | uniq -d)
if [ -z "$dups" ]; then ok "no duplicate label after add with missing HW"
else bad "add re-issued a live label: $dups"; fi
rm -rf "$d"

echo "== (b) HW stale (points at a live label) -> no reuse =="
d=$(newfleet)
printf 'E\tlive item E\n' > "$d/state/OPERATOR-ACTIONS.md"   # E = index 4
echo 3 > "$d/state/.operator-actions.hw"                     # stale: next would be index 4 = "E"
bash "$d/pending.sh" add "another item" >/dev/null 2>&1
dups=$(cut -f1 "$d/state/OPERATOR-ACTIONS.md" | sort | uniq -d)
if [ -z "$dups" ]; then ok "no duplicate label after add with stale HW"
else bad "add re-issued a live label: $dups"; fi
rm -rf "$d"

echo "== (c) duplicate label -> done REFUSES and deletes nothing =="
d=$(newfleet)
printf '#12\tfirst item\n#12\tsecond unrelated item\nA\tother\n' > "$d/state/OPERATOR-ACTIONS.md"
before=$(wc -l < "$d/state/OPERATOR-ACTIONS.md")
bash "$d/pending.sh" done '#12' >/dev/null 2>&1; rc=$?
after=$(wc -l < "$d/state/OPERATOR-ACTIONS.md")
if [ "$rc" -ne 0 ] && [ "$before" = "$after" ]; then ok "refused (rc=$rc), $after rows intact"
else bad "expected refusal with no deletion; rc=$rc rows $before -> $after"; fi
rm -rf "$d"

echo "== (d) anti-over-block: unique label still clears (exactly one row) =="
d=$(newfleet)
printf 'A\tkeep me\nB\tclear me\nC\tkeep me too\n' > "$d/state/OPERATOR-ACTIONS.md"
bash "$d/pending.sh" done B >/dev/null 2>&1; rc=$?
rows=$(wc -l < "$d/state/OPERATOR-ACTIONS.md")
left=$(cut -f1 "$d/state/OPERATOR-ACTIONS.md" | tr '\n' ' ')
if [ "$rc" -eq 0 ] && [ "$rows" -eq 2 ] && [ "$left" = "A C " ]; then ok "cleared B only (left: $left)"
else bad "expected rc=0, 2 rows 'A C '; got rc=$rc rows=$rows left='$left'"; fi
rm -rf "$d"

echo "== (e) clean list still allocates monotonically =="
d=$(newfleet)
: > "$d/state/OPERATOR-ACTIONS.md"
for t in one two three; do bash "$d/pending.sh" add "$t" >/dev/null 2>&1; done
got=$(cut -f1 "$d/state/OPERATOR-ACTIONS.md" | tr '\n' ' ')
if [ "$got" = "A B C " ]; then ok "A B C"
else bad "expected 'A B C '; got '$got'"; fi
rm -rf "$d"

echo
if [ "$fails" -eq 0 ]; then echo "pending-labels: GREEN (5/5)"; exit 0; fi
echo "pending-labels: RED ($fails failing)"; exit 1
