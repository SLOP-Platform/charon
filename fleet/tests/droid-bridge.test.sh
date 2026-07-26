#!/usr/bin/env bash
# droid-bridge.test.sh — FAIL-ON-REVERT tests for DROID PUSH MODE
# (fleet/droid-bridge.sh + the push wiring in fleet/fleet-droid.sh).
#
# OPERATOR ASK: "a version of a droid which IDLES until the MANAGER/SUPERVISOR session
# sends them work." Droids PULL today; this proves they can also be PUSHED to.
#
# WHAT IS ACTUALLY EXERCISED (not simulated):
#   - a REAL session-bridge daemon (scratch socket + scratch DB under $WORK), driven
#     through the REAL proxy.py forwarder — the same transport production uses;
#   - the REAL fleet-droid.sh claim loop, the REAL claim.sh, the REAL work-lease,
#     parallelizability gate and leak-guard worktree setup;
#   - a REAL git repo (bare origin + clone) so worktree/branch creation is genuine.
# Only TWO things are substituted, both at documented swap seams, neither a gate:
#   1. CHARON_AGENT_CMD -> a recorder. fleet-droid.sh's own header declares this client
#      swappable ("one env var, zero other edits"); the recorder is what lets us assert
#      WHICH ticket actually ran.
#   2. repo_resolve() -> a throwaway repo. The registry hardcodes absolute repo paths, so
#      without this the test would create branches and worktrees in the REAL repos.
#      Every gate downstream of it still runs unmodified.
#
# THE FOUR CLAIMS, each red-proofed by execution:
#   A. A dispatch makes an idle droid run THAT EXACT ticket.
#   B. The pin is PER-ITERATION: a droid launched with `--only X` still runs a dispatched
#      Y first, then falls back to X. Launch-time-only pinning cannot produce that order.
#   C. NO DARK WORK: a dispatch names a ticket id and nothing else. A dispatch for a ticket
#      with no board file is REFUSED — no claim file, no branch, no worktree, no run.
#   D. BRIDGE DOWN is loud: hybrid degrades to pull with a marker; --push-only stands down
#      with exit 6 and a marker. Pull with no push flags is byte-identically unaffected.
#
# Run:  bash fleet/tests/droid-bridge.test.sh   (exit 0 = all pass)
set -uo pipefail

FLEET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROXY="$HOME/.config/opencode/session-bridge/proxy.py"
DAEMON="$HOME/.config/opencode/session-bridge/daemon.py"

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ case "$2" in *"$3"*) ok "$1" ;; *) bad "$1 (expected '$3')"; printf '%s\n' "$2" | tail -25 ;; esac; }
not_has(){ case "$2" in *"$3"*) bad "$1 (must NOT contain '$3')"; printf '%s\n' "$2" | tail -25 ;; *) ok "$1" ;; esac; }
eq(){ if [ "$2" = "$3" ]; then ok "$1 (=$3)"; else bad "$1 (got '$2', expected '$3')"; fi; }

if [ ! -r "$DAEMON" ] || [ ! -r "$PROXY" ]; then
  # NON-VACUOUS: a missing bridge is RED, never a silent skip. The whole point of this
  # suite is that push works against the real transport.
  echo "FAIL: session-bridge daemon/proxy not found ($DAEMON) — cannot verify push mode"
  exit 1
fi

WORK="$(mktemp -d)"
GW_PID=""; BRIDGE_PID=""
cleanup(){ [ -n "$BRIDGE_PID" ] && kill "$BRIDGE_PID" 2>/dev/null; [ -n "$GW_PID" ] && kill "$GW_PID" 2>/dev/null; rm -rf "$WORK"; }
trap cleanup EXIT

# ── throwaway git repo (bare origin + clone), so origin/master really resolves ───────────
git init -q --bare "$WORK/origin.git"
git clone -q "$WORK/origin.git" "$WORK/repo" 2>/dev/null
git -C "$WORK/repo" config user.email t@t; git -C "$WORK/repo" config user.name t
echo seed > "$WORK/repo/README.md"
git -C "$WORK/repo" add -A && git -C "$WORK/repo" commit -qm seed
git -C "$WORK/repo" branch -M master && git -C "$WORK/repo" push -q origin master

# ── isolated fleet copy: empty board + empty claim state ─────────────────────────────────
FC="$WORK/fleet"
cp -a "$FLEET_DIR" "$FC"
rm -rf "$FC/board" "$FC/state/claims" "$FC/state/loop-guard" "$FC/state/push-degraded" \
       "$FC/state/submitted" "$FC/state/needs-push"
mkdir -p "$FC/board" "$FC/state/claims"

# repo_resolve override (appended, so the later definition wins and repo_valid_id survives)
cat >> "$FC/repo-registry.sh" <<EOF
repo_resolve(){
  local key="\${1:-}" id="\${2:-}"
  [ -n "\$id" ] && ! repo_valid_id "\$id" && return 2
  RR_KEY=charon; RR_PATH="$WORK/repo"; RR_WT="$WORK/wt-\$id"; RR_BASE=master
  RR_GATE='true'
  [ -n "\$id" ] || RR_WT=""
  return 0
}
EOF

mk_ticket(){ # mk_ticket <id>
  cat > "$FC/board/$1.md" <<EOF
repo: charon
tier: strong
priority: 0
difficulty: 1
work_class: ci-infra
branch: feat/$(echo "$1" | tr 'A-Z' 'a-z')
owns: README.md
depends_on:
source: |
  hermetic push-mode test ticket
note: |
  hermetic push-mode test ticket
accept: |
  - recorder observes this ticket id
EOF
}
mk_ticket PUSH-TEST-ALPHA
mk_ticket PUSH-TEST-BETA

# ── recorder standing in for the work client (fleet-droid.sh's documented swap seam) ─────
REC="$WORK/ran.log"; : > "$REC"
cat > "$WORK/recorder.sh" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\${CHARON_JOB_REF:-NOREF}" >> "$REC"
cd "\$1" 2>/dev/null && { echo "work by \${CHARON_JOB_REF}" >> README.md; git add -A; git -c user.email=t@t -c user.name=t commit -qm "chore(\${CHARON_JOB_REF}): recorder"; }
exit 0
EOF
chmod +x "$WORK/recorder.sh"

# ── fake gateway so the (already-landed) pre-claim gateway preflight is satisfied ────────
cat > "$WORK/gw.py" <<'PY'
import http.server, json, sys
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        b = json.dumps({"pools": {}, "providers": {}}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers()
        self.wfile.write(b)
    def log_message(self, *a): pass
s = http.server.HTTPServer(("127.0.0.1", 0), H)
open(sys.argv[1], "w").write(str(s.server_port)); s.serve_forever()
PY
python3 "$WORK/gw.py" "$WORK/gwport" & GW_PID=$!
for _ in $(seq 1 50); do [ -s "$WORK/gwport" ] && break; sleep 0.1; done
GW_PORT="$(cat "$WORK/gwport")"
cat > "$WORK/opencode.json" <<'EOF'
{"provider": {"charon": {"options": {"apiKey": "test-token"}}}}
EOF

# ── scratch bridge daemon: real daemon.py, isolated socket + DB ──────────────────────────
BSOCK="$WORK/bridge.sock"; BDB="$WORK/bridge.db"; BLEDGER="$WORK/acted.db"
BRIDGE_SOCKET="$BSOCK" BRIDGE_DB="$BDB" python3 "$DAEMON" > "$WORK/daemon.log" 2>&1 & BRIDGE_PID=$!
for _ in $(seq 1 60); do [ -S "$BSOCK" ] && break; sleep 0.25; done
[ -S "$BSOCK" ] && ok "bridge daemon up on a scratch socket" || bad "bridge daemon failed to start"

bridge_env(){ echo "BRIDGE_SOCKET=$BSOCK BRIDGE_LEDGER=$BLEDGER"; }
dispatch(){ # dispatch <target-sid> <ticket>
  BRIDGE_SOCKET="$BSOCK" BRIDGE_LEDGER="$BLEDGER" \
    bash "$FC/droid-bridge.sh" dispatch manager "$1" "$2"
}
run_droid(){ # run_droid <sock> <extra args...>
  local sock="$1"; shift
  DROID_OUT="$(cd "$WORK" && BRIDGE_SOCKET="$sock" BRIDGE_LEDGER="$BLEDGER" \
    CHARON_GATEWAY_URL="http://127.0.0.1:$GW_PORT" CHARON_OPENCODE_CONFIG="$WORK/opencode.json" \
    CHARON_AGENT_CMD="$WORK/recorder.sh" CHARON_TIER_MODELS="$FC/tier-models.tsv" \
    CHARON_EXHAUST_LEDGER="$WORK/ledger.tsv" WORK_LEASE_BYPASS=1 \
    timeout 180 bash "$FC/fleet-droid.sh" strong "$@" 2>&1)"
  return $?
}
reset_state(){ : > "$REC"; rm -rf "$FC/state/claims" "$FC/state/submitted" "$FC/state/push-degraded" "$FC/state/loop-guard"; mkdir -p "$FC/state/claims"; rm -rf "$WORK"/wt-*; }

echo
echo "=== A. UNIT: droid-bridge.sh exit-code contract + idempotency ==="
BRIDGE_SOCKET="$BSOCK" BRIDGE_LEDGER="$BLEDGER" bash "$FC/droid-bridge.sh" register unit-droid unit-droid charon pending > "$WORK/lease.txt"
eq "A1 register succeeds"                    "$?" "0"
[ -s "$WORK/lease.txt" ] && ok "A2 register returns a lease token" || bad "A2 register returns a lease token"
BRIDGE_SOCKET="$BSOCK" BRIDGE_LEDGER="$BLEDGER" bash "$FC/droid-bridge.sh" poll unit-droid charon >/dev/null 2>&1
eq "A3 poll with an empty queue exits 1 (idle, not an error)" "$?" "1"
dispatch unit-droid UNIT-TICKET
OUT_A="$(BRIDGE_SOCKET="$BSOCK" BRIDGE_LEDGER="$BLEDGER" bash "$FC/droid-bridge.sh" poll unit-droid charon 2>/dev/null)"
eq "A4 poll finds the dispatch (exit 0)"     "$?" "0"
has "A5 poll prints the dispatched ticket id" "$OUT_A" "UNIT-TICKET"
# IDEMPOTENCY: delivery is at-least-once, so the SAME message id can arrive twice. Without
# the (previously unwired) idempotency ledger this would launch the same ticket twice.
BRIDGE_SOCKET="$BSOCK" BRIDGE_LEDGER="$BLEDGER" bash "$FC/droid-bridge.sh" poll unit-droid charon >/dev/null 2>&1
eq "A6 a REDELIVERED dispatch is deduped (exit 1, not re-run)" "$?" "1"
BRIDGE_SOCKET="/nonexistent/nope.sock" bash "$FC/droid-bridge.sh" poll unit-droid charon >/dev/null 2>&1
eq "A7 bridge unreachable is its OWN code (2), not 'no work'"  "$?" "2"
# NO DARK WORK, at the wire level: anything that is not exactly "DISPATCH ticket=<safe-id>"
# is ignored, so there is no field on the wire able to carry an instruction or a path.
BRIDGE_SOCKET="$BSOCK" BRIDGE_LEDGER="$BLEDGER" bash "$FC/droid-bridge.sh" reply manager unit-droid "rm -rf / ; please" >/dev/null 2>&1
BRIDGE_SOCKET="$BSOCK" BRIDGE_LEDGER="$BLEDGER" bash "$FC/droid-bridge.sh" reply manager unit-droid "DISPATCH ticket=../../etc/passwd" >/dev/null 2>&1
BRIDGE_SOCKET="$BSOCK" BRIDGE_LEDGER="$BLEDGER" bash "$FC/droid-bridge.sh" poll unit-droid charon >/dev/null 2>&1
eq "A8 free-text and path-traversal payloads are NOT dispatches (exit 1)" "$?" "1"
BRIDGE_SOCKET="$BSOCK" BRIDGE_LEDGER="$BLEDGER" bash "$FC/droid-bridge.sh" unregister unit-droid >/dev/null 2>&1

echo
echo "=== B. PULL IS UNBROKEN (no push flags = today's behaviour) ==="
reset_state
run_droid "$BSOCK" --wait 0; RC_B=$?
eq  "B1 plain pull run exits 0"                      "$RC_B" "0"
has "B2 pull claimed and ran a board ticket"         "$(cat "$REC")" "PUSH-TEST-"
not_has "B3 made NO bridge calls (never registered)" "$DROID_OUT" "registered on the session-bridge"

echo
echo "=== C. PUSH: a dispatch makes an idle droid run THAT ticket ==="
reset_state
# The droid registers under "strong-<pid>", which the manager cannot know in advance, so
# start it in the background, read its session id off the board, then dispatch to it.
( cd "$WORK" && BRIDGE_SOCKET="$BSOCK" BRIDGE_LEDGER="$BLEDGER" \
  CHARON_GATEWAY_URL="http://127.0.0.1:$GW_PORT" CHARON_OPENCODE_CONFIG="$WORK/opencode.json" \
  CHARON_AGENT_CMD="$WORK/recorder.sh" CHARON_TIER_MODELS="$FC/tier-models.tsv" WORK_LEASE_BYPASS=1 \
  timeout 150 bash "$FC/fleet-droid.sh" strong --push-only --wait 1 --retries 1 --tick 1 \
  > "$WORK/c.out" 2>&1 ) & DROID_BG=$!
SID=""
for _ in $(seq 1 60); do
  SID="$(grep -oE 'strong-[0-9]+' "$WORK/c.out" 2>/dev/null | head -1)"
  [ -n "$SID" ] && break; sleep 0.5
done
if [ -z "$SID" ]; then bad "C0 push-only droid never registered"; else
  ok "C0 push-only droid registered as '$SID' and is idling (not claiming)"
  # PROOF IT IS IDLE, NOT WORKING: it has been up and has claimed nothing.
  eq "C1 idle droid free-claims NOTHING while waiting" "$(cat "$REC" | wc -l | tr -d ' ')" "0"
  dispatch "$SID" PUSH-TEST-ALPHA
  for _ in $(seq 1 60); do grep -q PUSH-TEST-ALPHA "$REC" 2>/dev/null && break; sleep 0.5; done
  wait "$DROID_BG"; RC_C=$?
  DROID_OUT="$(cat "$WORK/c.out")"
  has "C2 the dispatch was received"            "$DROID_OUT" "DISPATCH received: ticket=PUSH-TEST-ALPHA"
  has "C3 the droid ran THAT EXACT ticket"      "$(cat "$REC")" "PUSH-TEST-ALPHA"
  eq  "C4 it ran exactly ONE ticket (no free-claim of the other)" "$(sort -u "$REC" | wc -l | tr -d ' ')" "1"
  has "C5 idle is a BOARD FIELD, not an inference (registered pending)" "$DROID_OUT" "push mode 'only': registered"
  echo "--- push-only run exit code: $RC_C"
fi

echo
echo "=== D. THE PIN IS PER-ITERATION, not launch-time ==="
# Launch pinned to a ticket that DOES NOT EXIST, then dispatch a real one. This is the
# decisive shape: CLAIM_ONLY used to be exported ONCE at launch, so the pin would stay
# "NO-SUCH-LAUNCH-PIN" forever and the dispatch could NEVER run — the droid would idle to
# stand-down having done nothing. Observing ALPHA actually run therefore proves the pin was
# re-exported for that iteration, and nothing else can explain it.
# (Deliberately NOT "pin BETA, dispatch ALPHA, assert ALPHA first": that races the droid's
# own first free-claim of BETA, which fires before a manager can even read its session id.)
reset_state
( cd "$WORK" && BRIDGE_SOCKET="$BSOCK" BRIDGE_LEDGER="$BLEDGER" \
  CHARON_GATEWAY_URL="http://127.0.0.1:$GW_PORT" CHARON_OPENCODE_CONFIG="$WORK/opencode.json" \
  CHARON_AGENT_CMD="$WORK/recorder.sh" CHARON_TIER_MODELS="$FC/tier-models.tsv" WORK_LEASE_BYPASS=1 \
  timeout 150 bash "$FC/fleet-droid.sh" strong --push --only NO-SUCH-LAUNCH-PIN --wait 1 --retries 1 --tick 1 \
  > "$WORK/d.out" 2>&1 ) & DROID_BG=$!
SID=""
for _ in $(seq 1 60); do
  SID="$(grep -oE 'strong-[0-9]+' "$WORK/d.out" 2>/dev/null | head -1)"
  [ -n "$SID" ] && break; sleep 0.5
done
if [ -z "$SID" ]; then bad "D0 hybrid droid never registered"; else
  ok "D0 hybrid droid registered as '$SID', pinned to a nonexistent ticket"
  dispatch "$SID" PUSH-TEST-ALPHA
  for _ in $(seq 1 120); do grep -q PUSH-TEST-ALPHA "$REC" 2>/dev/null && break; sleep 0.5; done
  wait "$DROID_BG" 2>/dev/null; RC_D=$?
  eq  "D1 the DISPATCHED ticket ran despite an unrelated launch pin" "$(head -1 "$REC")" "PUSH-TEST-ALPHA"
  eq  "D2 the launch pin is RESTORED after (nothing else free-claimed)" "$(sort -u "$REC" | wc -l | tr -d ' ')" "1"
  has "D3 the dispatch was what unpinned it"          "$(cat "$WORK/d.out")" "DISPATCH received: ticket=PUSH-TEST-ALPHA"
  echo "--- hybrid run exit code: $RC_D"
fi

echo
echo "=== E. NO DARK WORK: a dispatch for a ticket that does not exist ==="
reset_state
( cd "$WORK" && BRIDGE_SOCKET="$BSOCK" BRIDGE_LEDGER="$BLEDGER" \
  CHARON_GATEWAY_URL="http://127.0.0.1:$GW_PORT" CHARON_OPENCODE_CONFIG="$WORK/opencode.json" \
  CHARON_AGENT_CMD="$WORK/recorder.sh" CHARON_TIER_MODELS="$FC/tier-models.tsv" WORK_LEASE_BYPASS=1 \
  timeout 120 bash "$FC/fleet-droid.sh" strong --push-only --wait 1 --retries 1 --tick 1 \
  > "$WORK/e.out" 2>&1 ) & DROID_BG=$!
SID=""
for _ in $(seq 1 60); do
  SID="$(grep -oE 'strong-[0-9]+' "$WORK/e.out" 2>/dev/null | head -1)"
  [ -n "$SID" ] && break; sleep 0.5
done
if [ -z "$SID" ]; then bad "E0 droid never registered"; else
  dispatch "$SID" NO-SUCH-TICKET-ANYWHERE
  for _ in $(seq 1 60); do grep -q "DISPATCH REFUSED" "$WORK/e.out" 2>/dev/null && break; sleep 0.5; done
  wait "$DROID_BG" 2>/dev/null; RC_E=$?
  DROID_OUT="$(cat "$WORK/e.out")"
  has "E1 the dispatch is REFUSED, loudly"    "$DROID_OUT" "DISPATCH REFUSED: 'NO-SUCH-TICKET-ANYWHERE'"
  eq  "E2 NOTHING ran"                        "$(cat "$REC" | wc -l | tr -d ' ')" "0"
  eq  "E3 no claim file was created"          "$(find "$FC/state/claims" -type f 2>/dev/null | wc -l | tr -d ' ')" "0"
  eq  "E4 no worktree was created"            "$(ls -d "$WORK"/wt-* 2>/dev/null | wc -l | tr -d ' ')" "0"
  eq  "E5 no branch was created"              "$(git -C "$WORK/repo" branch --list '*no-such*' | wc -l | tr -d ' ')" "0"
  echo "--- dark-work run exit code: $RC_E"
fi

echo
echo "=== F. BRIDGE DOWN is LOUD in both directions ==="
reset_state
run_droid "/nonexistent/nope.sock" --push --wait 0; RC_F=$?
DEG_H="$DROID_OUT"
has "F1 hybrid says BRIDGE-DOWN"                  "$DEG_H" "BRIDGE-DOWN"
has "F2 hybrid says it is DEGRADING TO PULL"      "$DEG_H" "DEGRADING TO PULL"
eq  "F3 hybrid writes a degraded marker"          "$(find "$FC/state/push-degraded" -type f 2>/dev/null | wc -l | tr -d ' ')" "1"
has "F4 hybrid STILL DID THE WORK via pull"       "$(cat "$REC")" "PUSH-TEST-"
eq  "F5 hybrid exits 0 (degraded, not broken)"    "$RC_F" "0"

reset_state
run_droid "/nonexistent/nope.sock" --push-only --wait 0; RC_F2=$?
eq  "F6 push-only stands down with its OWN code"  "$RC_F2" "6"
has "F7 push-only explains it has no pull fallback" "$DROID_OUT" "no pull fallback"
eq  "F8 push-only writes a marker"                "$(find "$FC/state/push-degraded" -type f 2>/dev/null | wc -l | tr -d ' ')" "1"
eq  "F9 push-only did NOT silently free-claim"    "$(cat "$REC" | wc -l | tr -d ' ')" "0"

echo
echo "=== G. F4 MONEY GUARDRAIL in the CLAIM LOOP (no work_class -> fail closed) ==="
# The claim-loop half of the same fail-open the `resolve` hook had (whose half is pinned in
# assign-dispatch.test.sh (f), its proper home). It lives HERE because this is the only
# harness with a real end-to-end droid: a real board, a real claim.sh, a real work-lease and
# a real repo. Asserting "it was RELEASED and QUARANTINED and did NOT run" needs all of that.
# Before the fix this printed a WARNING and then ran the FULL UNFILTERED CHAIN — every money
# guardrail (detention, gateway capped-exclusion, cost cap) scopes by work_class, so a ticket
# that merely omits the field skipped all three.
reset_state
cat > "$FC/board/NO-WORKCLASS-TICKET.md" <<'EOF'
repo: charon
tier: strong
priority: 0
difficulty: 1
branch: feat/no-workclass-ticket
owns: README.md
depends_on:
source: |
  hermetic F4 fixture — deliberately has NO work_class field
note: |
  hermetic F4 fixture
accept: |
  - the droid must REFUSE this rather than run an unfiltered chain
EOF
# Pin the claim to this ticket so the assertion is about IT, not whichever the ladder picks.
run_droid "$BSOCK" --only NO-WORKCLASS-TICKET --wait 0; RC_G=$?
has "G1 the ticket is SKIPPED, loudly, naming the cause" "$DROID_OUT" "WORK-CLASS-MISSING"
has "G2 it says it refused the unfiltered chain"         "$DROID_OUT" "NOT running the full unfiltered chain"
eq  "G3 the work NEVER ran"                              "$(cat "$REC" | wc -l | tr -d ' ')" "0"
eq  "G4 the claim was RELEASED (not silently held)"      "$(find "$FC/state/claims" -type f 2>/dev/null | wc -l | tr -d ' ')" "0"
has "G5 the refusal is recorded in the exhaustion ledger" "$(cat "$WORK/ledger.tsv" 2>/dev/null)" "work-class-missing"
echo "--- no-work_class claim-loop exit code: $RC_G"
# NON-VACUITY CONTROL: the same pinned-claim shape WITH a work_class must still run, so G1-G5
# cannot pass merely because pinned claims are broken.
reset_state
run_droid "$BSOCK" --only PUSH-TEST-ALPHA --wait 0; RC_G2=$?
has "G6 CONTROL: a ticket WITH work_class still runs"    "$(cat "$REC")" "PUSH-TEST-ALPHA"
rm -f "$FC/board/NO-WORKCLASS-TICKET.md"

echo
echo "=========================================="
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
