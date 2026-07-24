#!/usr/bin/env bash
# test-faktory.sh — real (non-mocked) proof that the Faktory substrate honors the lease + durability
# contract. Requires a LIVE Faktory server (4-LOM) and FAKTORY_PASSWORD in the env.
#
#   T1 lease-exclusivity : a reserved job is invisible to a second reserve.
#   T2 durability        : an ACKed job is GONE and NOT re-fetchable AFTER real container recreation
#                          (docker rm + docker run against the RDB volume — a real restart, not mocked).
#   T3 fail-requeue      : a FAILed job requeues (returns to the retries set, then becomes re-fetchable).
#   T4 worker e2e        : faktory-worker.sh reserves, runs a charon-run-shaped payload (real side
#                          effect), and ACKs; the job is then absent.
#
# The container recreation in T2 is driven over SSH to 4-LOM (the durability host). If SSH to 4-LOM
# is unavailable, T2 SKIPs loudly rather than passing on a mock (money/infra-critical → real green).
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI="$SCRIPT_DIR/faktory-client.sh"
WORKER="$SCRIPT_DIR/faktory-worker.sh"
FAKTORY_HOST="${FAKTORY_HOST:-10.0.1.60}"
SSH4LOM=(ssh -i "$HOME/.ssh/4lom" -o StrictHostKeyChecking=no -o ConnectTimeout=10 stack@"$FAKTORY_HOST")
export FAKTORY_HOST

pass=0; fail=0; skip=0
ok()   { echo "PASS: $*"; pass=$((pass+1)); }
bad()  { echo "FAIL: $*"; fail=$((fail+1)); }
warn() { echo "SKIP: $*"; skip=$((skip+1)); }
Q="test-$$"
uid() { echo "TST-$$-$RANDOM-$(date +%N)"; }

[ -n "${FAKTORY_PASSWORD:-}" ] || { echo "FAKTORY_PASSWORD not set — cannot run real tests" >&2; exit 2; }

echo "### T1: reserved job invisible to a second reserve"
J1="$(uid)"
"$CLI" push --queue "$Q" --jobtype charon-run --jid "$J1" --arg '"true"' >/dev/null
r1="$("$CLI" reserve --queue "$Q")"; rc1=$?
r2="$("$CLI" reserve --queue "$Q")"; rc2=$?
if [ $rc1 -eq 0 ] && printf '%s' "$r1" | grep -qF "$J1" && [ $rc2 -ne 0 ] && [ -z "$r2" ]; then
  ok "T1 reserved job ($J1) held; 2nd reserve empty rc=$rc2"
else
  bad "T1 rc1=$rc1 r1=[$r1] rc2=$rc2 r2=[$r2]"
fi

echo "### T2: ACKed job durably GONE across REAL container recreation"
J2="$(uid)"
"$CLI" push --queue "$Q" --jobtype charon-run --jid "$J2" --arg '"true"' >/dev/null
# also push a still-enqueued control job that must SURVIVE the restart (proves RDB persistence,
# not just that the acked one is gone because the queue was wiped)
JC="$(uid)"
"$CLI" push --queue "$Q" --jobtype charon-run --jid "$JC" --arg '"true"' >/dev/null
rj="$("$CLI" reserve --queue "$Q")"
# reserve returns either J2 or JC (FIFO → J2 first); ack whichever is J2. Ensure we hold+ack J2.
if ! printf '%s' "$rj" | grep -qF "$J2"; then
  # got JC first; ack it back path: fail JC to requeue, reserve again for J2
  "$CLI" reserve --queue "$Q" >/dev/null || true
fi
"$CLI" ack --jid "$J2" >/dev/null && echo "  acked $J2"
if "${SSH4LOM[@]}" 'docker inspect faktory >/dev/null 2>&1'; then
  echo "  recreating faktory container on $FAKTORY_HOST (real restart, graceful SIGTERM)..."
  # GRACEFUL stop (SIGTERM) so Faktory flushes its RDB snapshot before the container is destroyed —
  # this mirrors a normal container recreation / host reboot. NOTE: `docker rm -f` (SIGKILL) would
  # lose the last snapshot window (embedded Redis uses periodic RDB, not per-write fsync); that is a
  # crash, not a recreation. See fleet/state/FAKTORY-ADOPT.md "Durability caveat".
  "${SSH4LOM[@]}" 'bash -s' <<'REMOTE'
PW="$(cat ~/.faktory/password)"
docker stop faktory >/dev/null 2>&1
docker rm faktory >/dev/null 2>&1
docker run -d --name faktory --restart unless-stopped \
  -v faktory-data:/root/.faktory -e FAKTORY_PASSWORD="$PW" \
  -p 0.0.0.0:7419:7419 -p 0.0.0.0:7420:7420 \
  contribsys/faktory:latest /faktory -b :7419 -w :7420 >/dev/null
REMOTE
  sleep 3
  # ACKed job must NOT be re-fetchable and must be absent from all sets
  if "$CLI" info --jid "$J2" >/dev/null; then
    bad "T2 ACKed job $J2 still present after recreation (durability BREACH)"
  else
    # control job must still be enqueued (RDB actually persisted, queue not merely empty)
    if "$CLI" info --jid "$JC" | grep -q enqueued; then
      ok "T2 ACKed job $J2 GONE after real recreation; control job $JC survived (RDB persisted)"
    else
      bad "T2 control job $JC missing after recreation — volume not persisting"
    fi
  fi
  # drain the surviving control job so we leave the queue clean
  "$CLI" reserve --queue "$Q" >/dev/null 2>&1 && "$CLI" ack --jid "$JC" >/dev/null 2>&1 || true
else
  warn "T2 4-LOM docker unreachable — durability proof requires a real restart, not mocked"
fi

echo "### T3: FAILed job requeues (returns to retries set, becomes re-fetchable)"
J3="$(uid)"
"$CLI" push --queue "$Q" --jobtype charon-run --jid "$J3" --arg '"false"' --reserve-for 60 >/dev/null
"$CLI" reserve --queue "$Q" >/dev/null
"$CLI" fail --jid "$J3" --msg "deliberate" >/dev/null
st="$("$CLI" info --jid "$J3" || true)"
if printf '%s' "$st" | grep -qE 'retries|scheduled|enqueued'; then
  ok "T3 FAILed job $J3 requeued (state=$st) — not lost, not dead"
else
  bad "T3 FAILed job $J3 state=[$st] (expected retries/scheduled)"
fi

echo "### T4: worker e2e — reserve, run charon-run-shaped payload, ACK"
J4="$(uid)"
MARK="$(mktemp -u /tmp/faktory-e2e-XXXXXX)"
"$CLI" push --queue "$Q" --jobtype charon-run --jid "$J4" \
  --arg "\"touch $MARK\"" >/dev/null
"$WORKER" --queue "$Q" --once; wrc=$?
if [ -f "$MARK" ] && [ $wrc -eq 0 ] && ! "$CLI" info --jid "$J4" >/dev/null; then
  ok "T4 worker ran payload (side effect $MARK created) and ACKed; job absent"
  rm -f "$MARK"
else
  bad "T4 wrc=$wrc mark_exists=$([ -f "$MARK" ] && echo y || echo n) info-present=$("$CLI" info --jid "$J4" 2>/dev/null || echo absent)"
fi

# cleanup: fail/drain J3's retry so the test queue is left empty-ish (best effort)
echo
echo "==== RESULTS: $pass passed, $fail failed, $skip skipped ===="
[ $fail -eq 0 ]
