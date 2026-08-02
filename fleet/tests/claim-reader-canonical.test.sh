#!/usr/bin/env bash
# claim-reader-canonical.test.sh — FAIL-ON-REVERT suite for the ONE canonical claim reader
# (_lib.sh: claim_owner / claim_owner_pid / claim_liveness / claim_unreadable_report) and its
# two consumers, reap-orphans.sh and reconcile-stale-claims.sh.
#
# THE DEFECT (measured live 2026-08-01, CLAIM-READER-CANONICAL):
#   state/claims/<TICKET> has TWO live writers — claim.sh's legacy one-liner
#   `<tier>-<pid> <ISO8601Z>` and work-lease.sh's `key: value` LEASE block. reap-orphans.sh
#   read the owner with `awk '{print $1}'` under a comment asserting the legacy shape, so on a
#   LEASE file it got the literal `ticket:`, the PID parse failed, and the failure DEGRADED TO
#   A SILENT `SKIP` counted as "live (untouched)" with exit 0. A genuinely dead droid's claim
#   was therefore NEVER released and the ticket froze as `claimed` forever.
#
# WHAT EACH ARM PROVES, and what reverting the fix does to it:
#   (a) LEASE claim, DEAD owner PID -> classified DEAD and RELEASED.
#       Revert claim_liveness to `awk '{print $1}'` and this goes back to SKIP/live. RED.
#   (b) LEASE claim, LIVE owner PID -> untouched. Guards against over-reaping, the one
#       failure worse than under-reaping ("one checkout, one agent").
#   (c) UNREADABLE claim -> LOUD on STDERR + non-zero exit + claim NOT RELEASED even under
#       --apply. Drop the loudness and (c1)/(c3) go RED; drop the fail-closed hold and (c4)
#       goes RED. Silence is the deepest half of this defect: a skip nobody sees.
#   (d) LEGACY one-liner still reads correctly — the fix must not trade one format for the other.
#   (e) reconcile-stale-claims.sh has the SAME three properties, from the SAME shared reader.
#   (f) Unit: no second copy of the grammar exists in any consumer.
#   (g) The DISPLAY readers (status.sh / board.sh / ladder-health.sh) had the SAME defect and
#       are the operator's whole view of who holds what — each showed the literal `ticket:` as
#       the claim holder. Revert any of them and the board lies about ownership.
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){ printf '  ok   %s\n' "$1"; PASS=$((PASS+1)); }
bad(){ printf '  FAIL %s\n' "$1"; FAIL=$((FAIL+1)); }
has(){ case "$1" in *"$2"*) ok "$3";; *) bad "$3 (missing: $2)";; esac; }
no(){ case "$1" in *"$2"*) bad "$3 (unexpectedly present: $2)";; *) ok "$3";; esac; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"; jobs -p | xargs -r kill 2>/dev/null' EXIT

# A PID that is certainly not running: claim one, then let it exit.
DEAD_PID="$( ( exec bash -c 'exit 0' ) & echo $!; wait )"
while kill -0 "$DEAD_PID" 2>/dev/null; do sleep 0.1; done
# A PID that is certainly running for the duration of this test.
sleep 300 & LIVE_PID=$!

mkfleet(){                     # mkfleet <name> -> echoes the fleet dir
  local d="$TMP/$1"; mkdir -p "$d/board" "$d/state/claims"; printf '%s' "$d"
}
add_ticket(){                  # add_ticket <fleet> <id>   (NO branch: -> reaper's no-work arm)
  printf 'repo: charon-private\ntier: strong\n' > "$1/board/$2.md"
}
lease_claim(){                 # lease_claim <fleet> <id> <session> [heartbeat-epoch]
  printf 'ticket: %s\nsession: %s\nworktree: %s\nheartbeat: %s\nclaimed: %s\n' \
    "$2" "$3" "$1/wt-$2" "${4:-$(date +%s)}" "${4:-$(date +%s)}" > "$1/state/claims/$2"
}
legacy_claim(){                # legacy_claim <fleet> <id> <droid-id>
  printf '%s %s\n' "$3" "$(date -u +%FT%TZ)" > "$1/state/claims/$2"
}
reap(){ REAPER_FLEET_DIR="$1" bash "$SRC/reap-orphans.sh" "${@:2}" 2>&1; }
reap_rc(){ REAPER_FLEET_DIR="$1" bash "$SRC/reap-orphans.sh" "${@:2}" >/dev/null 2>&1; echo $?; }
recon(){ RECONCILE_FLEET_DIR="$1" RECONCILE_STALE_S=30 bash "$SRC/reconcile-stale-claims.sh" "${@:2}" 2>&1; }

echo "== (a) LEASE-format claim owned by a DEAD pid IS reaped =="
d="$(mkfleet a)"; add_ticket "$d" A-DEAD; lease_claim "$d" A-DEAD "economy-$DEAD_PID"
out="$(reap "$d")"
has "$out" "DEAD    A-DEAD" "(a1) dead lease owner classified DEAD (was: silent SKIP)"
no  "$out" "SKIP    A-DEAD" "(a2) NOT skipped as format drift"
no  "$out" "ticket:"        "(a3) owner is not the literal 'ticket:' key"
out="$(reap "$d" --apply)"
[ -e "$d/state/claims/A-DEAD" ] && bad "(a4) dead claim STILL held after --apply" \
                                || ok  "(a4) dead claim RELEASED under --apply"

echo "== (b) LEASE-format claim owned by a LIVE pid is NEVER touched =="
d="$(mkfleet b)"; add_ticket "$d" B-LIVE; lease_claim "$d" B-LIVE "economy-$LIVE_PID"
out="$(reap "$d" --apply)"
has "$out" "LIVE    B-LIVE" "(b1) live lease owner classified LIVE"
[ -e "$d/state/claims/B-LIVE" ] && ok "(b2) live claim SURVIVES --apply" \
                                || bad "(b2) live claim was released — over-reap, worse than the bug"

echo "== (c) UNREADABLE claim: LOUD, non-zero, and NEVER released =="
d="$(mkfleet c)"; add_ticket "$d" C-JUNK
printf 'this is not a claim in either format\n' > "$d/state/claims/C-JUNK"
err="$(REAPER_FLEET_DIR="$d" bash "$SRC/reap-orphans.sh" --apply 2>&1 >/dev/null)"
outc="$(reap "$d" --apply)"
has "$err"  "!!!!!! UNREADABLE CLAIM  C-JUNK" "(c1) reported LOUD on STDERR as a finding"
has "$err"  "CLAIM HELD, NOT RELEASED"        "(c2) stderr states the fail-closed decision"
has "$outc" "UNREADABLE  C-JUNK"               "(c3) also surfaced on stdout, not swallowed"
no  "$outc" "SKIP    C-JUNK"                  "(c3b) NOT degraded to a silent SKIP"
[ -e "$d/state/claims/C-JUNK" ] && ok "(c4) unreadable claim HELD under --apply (fail-closed)" \
                                || bad "(c4) unreadable claim RELEASED — can hand a live droid's ticket away"
[ "$(reap_rc "$d" --apply)" != "0" ] && ok "(c5) sweep exits NON-ZERO on an unreadable claim" \
                                     || bad "(c5) sweep exited 0 — the operator never sees it"

echo "== (d) LEGACY one-line claim still parses (no format traded for the other) =="
d="$(mkfleet d)"; add_ticket "$d" D-OLD-LIVE; legacy_claim "$d" D-OLD-LIVE "strong-$LIVE_PID"
has "$(reap "$d")" "LIVE    D-OLD-LIVE" "(d1) legacy live PID still LIVE"
d="$(mkfleet d2)"; add_ticket "$d" D-OLD-DEAD; legacy_claim "$d" D-OLD-DEAD "strong-$DEAD_PID"
has "$(reap "$d")" "DEAD    D-OLD-DEAD" "(d2) legacy dead PID still DEAD"

echo "== (e) reconcile-stale-claims.sh shares the reader and the same three properties =="
d="$(mkfleet e)"; add_ticket "$d" E-DEAD; add_ticket "$d" E-LIVE; add_ticket "$d" E-JUNK
lease_claim "$d" E-DEAD "economy-$DEAD_PID"      # fresh heartbeat, DEAD pid -> pid wins
lease_claim "$d" E-LIVE "economy-$LIVE_PID"
printf 'garbage\n' > "$d/state/claims/E-JUNK"
oute="$(recon "$d")"
has "$oute" "STALE   E-DEAD"     "(e1) dead lease owner is STALE despite a fresh heartbeat"
has "$oute" "LIVE    E-LIVE"     "(e2) live lease owner untouched"
has "$oute" "UNREADABLE  E-JUNK"  "(e3) unreadable claim surfaced, not skipped"
erre="$(RECONCILE_FLEET_DIR="$d" RECONCILE_STALE_S=30 bash "$SRC/reconcile-stale-claims.sh" 2>&1 >/dev/null)"
has "$erre" "!!!!!! UNREADABLE CLAIM  E-JUNK" "(e4) LOUD on STDERR from the SHARED reporter"
RECONCILE_FLEET_DIR="$d" RECONCILE_STALE_S=30 bash "$SRC/reconcile-stale-claims.sh" --apply >/dev/null 2>&1
rce=$?
[ "$rce" != "0" ] && ok "(e5) reconcile exits NON-ZERO on an unreadable claim" \
                  || bad "(e5) reconcile exited 0 — silent again"
[ -e "$d/state/claims/E-JUNK" ] && ok "(e6) unreadable claim HELD by reconcile --apply" \
                                || bad "(e6) reconcile RELEASED an unreadable claim"

echo "== (f) ONE grammar: no consumer keeps a private copy of the claim parse =="
for f in reap-orphans.sh reconcile-stale-claims.sh; do
  if grep -nE "awk '\{ *print \\\$1 *\}' \"?\\\$cf" "$SRC/$f" >/dev/null 2>&1; then
    bad "(f) $f still reads a claim owner with awk field-1 — private copy of the grammar"
  else
    ok "(f) $f reads owners only through the canonical reader"
  fi
done
grep -q 'claim_liveness()' "$SRC/_lib.sh" && ok "(f2) canonical reader lives in _lib.sh" \
                                          || bad "(f2) _lib.sh has no claim_liveness — no single home"

echo "== (g) DISPLAY readers go through the canonical reader, not a private awk =="
# status.sh / board.sh / ladder-health.sh hardcode FLEET to their own dir (no test seam, and
# adding one is not this ticket's scope), so they are asserted STATICALLY: each must call
# claim_owner and must NOT keep a field-1 awk over a claims path. Both halves are needed —
# "calls claim_owner" alone would pass a file that still had the broken read next to it.
for f in status.sh board.sh ladder-health.sh; do
  grep -q 'claim_owner' "$SRC/$f" && ok "(g:$f) reads the owner via claim_owner" \
                                  || bad "(g:$f) does NOT use the canonical claim_owner"
  if grep -nE "awk '(NR==1)?\\{ *print \\\$1 *\\}' \"?\\\$(S|STATE)/claims|awk '(NR==1)?\\{ *print \\\$1 *\\}' \"\\\$cf\"" "$SRC/$f" >/dev/null 2>&1; then
    bad "(g:$f) STILL reads a claim owner with a private field-1 awk"
  else
    ok "(g:$f) no private field-1 awk left over a claim file"
  fi
done

echo "== (h) unit: claim_owner / claim_liveness on each shape =="
d="$(mkfleet h)"; lease_claim "$d" H1 "economy-$LIVE_PID"; legacy_claim "$d" H2 "strong-$LIVE_PID"
printf 'junk\n' > "$d/state/claims/H3"
u(){ FLEET="$d" bash -c ". \"$SRC/_lib.sh\"; $1" 2>&1; }
has "$(u 'claim_owner "'"$d"'/state/claims/H1"')" "economy-$LIVE_PID" "(h1) lease owner = session field"
has "$(u 'claim_owner "'"$d"'/state/claims/H2"')" "strong-$LIVE_PID"  "(h2) legacy owner = field 1"
FLEET="$d" bash -c ". \"$SRC/_lib.sh\"; claim_owner \"$d/state/claims/H3\"" >/dev/null 2>&1 \
  && bad "(h3) claim_owner returned 0 on an unparseable claim" \
  || ok  "(h3) claim_owner returns NON-ZERO on an unparseable claim (callers fail closed)"
FLEET="$d" bash -c ". \"$SRC/_lib.sh\"; claim_liveness \"$d/state/claims/H3\"" >/dev/null 2>&1
[ "$?" -eq 2 ] && ok "(h4) claim_liveness rc=2 (UNKNOWN) on an unparseable claim" \
               || bad "(h4) claim_liveness did not report UNKNOWN — unknown must not read as dead"

echo
echo "claim-reader-canonical: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
