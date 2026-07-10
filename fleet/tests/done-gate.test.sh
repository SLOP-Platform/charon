#!/usr/bin/env bash
# done-gate.test.sh — FAIL-ON-REVERT tests for the "a done marker can't lie" gate:
#   G1  done.sh          — REFUSE to mark done without merge proof; --merged-sha writes merged:<sha>;
#                          --override records the exception; the removed --no-verify is rejected.
#   G2  preflight        — done_merge_gate AUTO-REGISTERS a blocking 'done-unmerged-<id>' red for a
#                          done marker that is NOT merge-verified; it BLOCKS cmd_scan and SELF-CLOSES
#                          when the ticket lands; verified/override markers open no red.
#   G3c retire-done      — HOLDS (does not archive) a ticket whose done marker is NOT merge-verified.
#   verify_merged        — local sha-ancestry + owns-content proofs (offline).
# All hermetic: an ISOLATED product git repo for the sha paths, VERIFY_MERGED_FIXTURE for the gate
# integration. NEVER touches the live reds.tsv, fleet/state, or the real product repo.
#
# Run:  bash fleet/tests/done-gate.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

# ---- isolated product repo (origin/master ref so sha-ancestry resolves offline) ----
P="$(mktemp -d)"
git -C "$P" init -q
mkdir -p "$P/src"; echo x > "$P/src/present.py"
git -C "$P" add -A; git -C "$P" commit -q -m base
GOODSHA="$(git -C "$P" rev-parse HEAD)"
git -C "$P" update-ref refs/remotes/origin/master "$GOODSHA"
# a commit that is NOT on origin/master (dangling) -> non-ancestor sha
git -C "$P" checkout -q -b side
git -C "$P" commit -q --allow-empty -m off-master
BADSHA="$(git -C "$P" rev-parse HEAD)"
git -C "$P" checkout -q master 2>/dev/null || git -C "$P" checkout -q -

export DONE_CHARON_REPO="$P" VERIFY_MERGED_REPO="$P"

# ============================ G1: done.sh ============================
echo "== G1 done.sh =="
g1(){ local d; d="$(mktemp -d)"
  cp "$SRC/done.sh" "$SRC/retire-done.sh" "$SRC/leak-guard.sh" "$SRC/_lib.sh" "$SRC/verify-merged.sh" "$d/"
  mkdir -p "$d/board/archive" "$d/state/done" "$d/state/submitted" "$d/state/claims" "$d/state/needs-push"
  printf 'tier: economy\nbranch: feat/g\nowns: src/present.py\n' > "$d/board/TICK-G.md"
  echo "$d"; }

# g1a: no proof + offline (empty DONE_MERGED_SRC so no gh) -> REFUSED, no marker.
d="$(g1)"; touch "$d/empty"
rc=0; DONE_MERGED_SRC="$d/empty" bash "$d/done.sh" TICK-G >/dev/null 2>&1 || rc=$?
check "g1a refuse close without proof (exit 3)" "$rc" "3"
[ -e "$d/state/done/TICK-G" ] && bad "g1a no marker written on refuse" || ok "g1a no marker written on refuse"
rm -rf "$d"

# g1b: --merged-sha <ancestor> -> marker written carrying merged:<sha>.
d="$(g1)"
rc=0; bash "$d/done.sh" TICK-G --merged-sha "$GOODSHA" >/dev/null 2>&1 || rc=$?
check "g1b good sha accepted (exit 0)" "$rc" "0"
grep -q "merged:$GOODSHA" "$d/state/done/TICK-G" 2>/dev/null && ok "g1b marker carries merged:<sha>" \
                                                             || bad "g1b marker carries merged:<sha>"
rm -rf "$d"

# g1c: --merged-sha <non-ancestor> -> REFUSED, no marker.
d="$(g1)"
rc=0; bash "$d/done.sh" TICK-G --merged-sha "$BADSHA" >/dev/null 2>&1 || rc=$?
check "g1c non-ancestor sha refused (exit 3)" "$rc" "3"
[ -e "$d/state/done/TICK-G" ] && bad "g1c no marker on bad sha" || ok "g1c no marker on bad sha"
rm -rf "$d"

# g1d: --override "reason" -> marker written with override:reason.
d="$(g1)"
rc=0; bash "$d/done.sh" TICK-G --override "hotfix landed direct to master" >/dev/null 2>&1 || rc=$?
check "g1d override accepted (exit 0)" "$rc" "0"
grep -q "override:hotfix landed direct to master" "$d/state/done/TICK-G" 2>/dev/null \
  && ok "g1d marker records the override reason" || bad "g1d marker records the override reason"
rm -rf "$d"

# g1e: --override with NO reason -> error (exception must record WHY).
d="$(g1)"
rc=0; bash "$d/done.sh" TICK-G --override >/dev/null 2>&1 || rc=$?
check "g1e override requires a reason (exit 2)" "$rc" "2"
rm -rf "$d"

# g1f: legacy --no-verify is rejected outright.
d="$(g1)"
rc=0; bash "$d/done.sh" TICK-G --no-verify >/dev/null 2>&1 || rc=$?
check "g1f removed --no-verify rejected (exit 2)" "$rc" "2"
[ -e "$d/state/done/TICK-G" ] && bad "g1f no marker via --no-verify" || ok "g1f no marker via --no-verify"
rm -rf "$d"

# ============================ verify_merged ============================
echo "== verify_merged =="
vd="$(mktemp -d)"; export FLEET="$vd"; mkdir -p "$vd/board/archive" "$vd/state/done"
# shellcheck source=/dev/null
source "$SRC/_lib.sh"
# sha proof
printf 'tier: economy\nbranch: feat/v\nowns: nonexistent/x.py\n' > "$vd/board/VS.md"
printf '2026-01-01T00:00:00Z\tmerged:%s\tbranch:feat/v\n' "$GOODSHA" > "$vd/state/done/VS"
verify_merged VS && ok "vm sha-proof marker verifies" || bad "vm sha-proof marker verifies"
printf '2026-01-01T00:00:00Z\tmerged:%s\tbranch:feat/v\n' "$BADSHA" > "$vd/state/done/VS"
verify_merged VS && bad "vm non-ancestor sha does NOT verify" || ok "vm non-ancestor sha does NOT verify"
# owns-content proof (no sha in marker; owns file present in origin/master)
printf 'tier: economy\nbranch: feat/o\nowns: src/present.py\n' > "$vd/board/VO.md"
: > "$vd/state/done/VO"
verify_merged VO && ok "vm owns-present verifies (content fallback)" || bad "vm owns-present verifies"
printf 'tier: economy\nbranch: feat/o\nowns: src/absent.py\n' > "$vd/board/VO.md"
verify_merged VO && bad "vm missing owns file does NOT verify" || ok "vm missing owns file does NOT verify"
unset FLEET
rm -rf "$vd"

# ============================ G2: preflight done_merge_gate ============================
echo "== G2 done_merge_gate =="
pd="$(mktemp -d)"
cp "$SRC/preflight.sh" "$SRC/_lib.sh" "$SRC/verify-merged.sh" "$pd/"
printf '# id\topened\tsev\tarea\tdesc\tcheck\tstatus\tclosed_by\n' > "$pd/reds.tsv"
mkdir -p "$pd/state/done" "$pd/state/needs-push" "$pd/board/archive"
printf 'TICK-V\n' > "$pd/verified.txt"; export VERIFY_MERGED_FIXTURE="$pd/verified.txt"
red_status(){ awk -F'\t' -v id="$1" '$1==id{print $7; exit}' "$pd/reds.tsv"; }
# shellcheck source=/dev/null
source "$pd/preflight.sh"

: > "$pd/state/done/TICK-U"                       # unverified done marker (not in fixture)
: > "$pd/state/done/TICK-V"                       # verified done marker (in fixture)
printf '2026-01-01T00:00:00Z\toverride:manual close\n' > "$pd/state/done/TICK-W"  # override
done_merge_gate >/dev/null 2>&1
check "g2a unverified done -> blocking red open"  "$(red_status done-unmerged-tick-u)" "open"
case "$(red_status done-unmerged-tick-v)" in "") ok "g2b verified done -> no red";; *) bad "g2b verified done -> no red (got '$(red_status done-unmerged-tick-v)')";; esac
case "$(red_status done-unmerged-tick-w)" in "") ok "g2c override done -> no red";; *) bad "g2c override done -> no red";; esac
rc=0; cmd_scan >/dev/null 2>&1 || rc=$?
check "g2d gate BLOCKS on unverified done marker" "$rc" "1"
# self-close: TICK-U now lands (add to fixture) -> gate closes the red, cmd_scan green.
printf 'TICK-U\n' >> "$pd/verified.txt"
done_merge_gate >/dev/null 2>&1
check "g2e red self-closes once ticket lands" "$(red_status done-unmerged-tick-u)" "closed"
rc=0; cmd_scan >/dev/null 2>&1 || rc=$?
check "g2f gate green after landing" "$rc" "0"
unset VERIFY_MERGED_FIXTURE
rm -rf "$pd"

# ============================ G3c: retire-done HOLD guard ============================
echo "== G3c retire-done =="
rdd="$(mktemp -d)"
cp "$SRC/retire-done.sh" "$SRC/leak-guard.sh" "$SRC/_lib.sh" "$SRC/verify-merged.sh" "$rdd/"
mkdir -p "$rdd/board/archive" "$rdd/state/done" "$rdd/state/needs-push"
printf 'tier: economy\nbranch: feat/u\n' > "$rdd/board/TICK-U.md"      # unverified -> HELD
printf 'tier: economy\nbranch: feat/v\n' > "$rdd/board/TICK-V.md"      # verified   -> archived
printf 'tier: economy\nbranch: feat/w\n' > "$rdd/board/TICK-W.md"      # override   -> archived
: > "$rdd/state/done/TICK-U"
: > "$rdd/state/done/TICK-V"
printf '2026-01-01T00:00:00Z\toverride:manual\n' > "$rdd/state/done/TICK-W"
printf 'TICK-V\n' > "$rdd/verified.txt"; export VERIFY_MERGED_FIXTURE="$rdd/verified.txt"
bash "$rdd/retire-done.sh" >/dev/null 2>&1
[ -e "$rdd/board/TICK-U.md" ] && ok "g3c1 unverified done HELD on active board" \
                              || bad "g3c1 unverified done HELD on active board"
[ -e "$rdd/board/archive/TICK-V.md" ] && ok "g3c2 verified done archived" || bad "g3c2 verified done archived"
[ -e "$rdd/board/archive/TICK-W.md" ] && ok "g3c3 override done archived" || bad "g3c3 override done archived"
unset VERIFY_MERGED_FIXTURE
rm -rf "$rdd"

rm -rf "$P"
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL DONE-GATE TESTS PASS"
