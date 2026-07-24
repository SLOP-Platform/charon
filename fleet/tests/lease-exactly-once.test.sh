#!/usr/bin/env bash
# lease-exactly-once.test.sh — FAIL-ON-REVERT proof for CLAIM-LEASE-EXACTLY-ONCE.
#
# Proves the exactly-once claim-lease wiring in fleet/lease-enqueue.sh, composed with
# WORK-LEASE-GATE (fleet/work-lease.sh) and FAKTORY-ADOPT (fleet/faktory/faktory-client.sh):
#
#   (a) two sessions cannot both hold the same ticket's reservation      [needs work-lease]
#   (b) a manager-sub commit for an un-reserved ticket is REFUSED        [needs work-lease]
#   (c) an ACKed ticket cannot be re-fetched after a Faktory restart     [needs REAL Faktory]
#   (d) a double-enqueue of the same ticket-id creates exactly ONE job   [needs REAL Faktory]
#
# Each case is fail-on-revert: with the wrapper/gate ACTIVE the protection holds; REVERT it
# (neutered copy / WORK_LEASE_BYPASS) and the case regresses to RED — asserted here.
#
# Every case runs in an ISOLATED temp sandbox (copied scripts + temp state + temp git repos).
# It NEVER touches the live fleet/state or any sibling worktree's state — safe under droids.
#
# (c)/(d) require the REAL Faktory from FAKTORY-ADOPT and are NEVER mocked (money/infra-critical
# → real green). If fleet/faktory/faktory-client.sh is not resolvable they report PENDING-FAKTORY.
#
# Run:  bash fleet/tests/lease-exactly-once.test.sh   (exit 0 = all runnable cases pass)
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"     # the real fleet/ dir (this branch)
PASS=0; FAIL=0; PEND=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
pend(){ PEND=$((PEND+1)); echo "PENDING-FAKTORY: $1"; }

# ── resolve composed dependencies (this branch's fleet/, else the sibling parallel worktrees) ──
resolve(){ local v; for v in "$@"; do [ -f "$v" ] && { echo "$v"; return 0; }; done; return 1; }
WORK_LEASE="$(resolve \
  "${WORK_LEASE_SRC:-}" \
  "$SRC/work-lease.sh" \
  "/home/stack/charon-private-wt/WORK-LEASE-GATE/fleet/work-lease.sh" || true)"
FAKTORY="$(resolve \
  "${FAKTORY_SRC:-}" \
  "$SRC/faktory/faktory-client.sh" \
  "/home/stack/charon-private-wt/FAKTORY-ADOPT/fleet/faktory/faktory-client.sh" || true)"

# the Faktory PROTOCOL credential (push/reserve/ack need it; the web-UI `info` read does not).
# Same source as FAKTORY-ADOPT's own test: env, else ~/.faktory/password. Exported so sandbox
# child invocations inherit it. Absent → (c)/(d) report PENDING-FAKTORY (never a false FAIL).
export FAKTORY_PASSWORD="${FAKTORY_PASSWORD:-$(cat "$HOME/.faktory/password" 2>/dev/null || true)}"

# real Faktory reachable AND authenticated for push/reserve? (never mocked). We probe with an
# AUTHENTICATED reserve — `info` alone uses the unauthenticated web UI and would pass even when the
# protocol password is missing, so we must exercise the credentialed path (c)/(d) actually need.
faktory_live(){
  [ -n "$FAKTORY" ] || return 1
  [ -n "${FAKTORY_PASSWORD:-}" ] || return 1
  local out rc
  out="$(bash "$FAKTORY" reserve --queue "__probe_$$_$RANDOM" --timeout 1 2>&1)"; rc=$?
  case "$out" in *password*) return 1;; esac   # "server requires a password" => not authenticated
  [ "$rc" -le 1 ] && return 0                   # rc0 (a job) or rc1 (empty queue) => server+auth OK
  return 1
}

# build an isolated sandbox fleet holding the wrapper + resolved deps + temp state.
mk_sandbox(){
  local d; d="$(mktemp -d)"
  mkdir -p "$d/fleet/state/enqueued" "$d/fleet/state/leases" "$d/fleet/board" \
           "$d/fleet/hooks" "$d/fleet/faktory"
  cp "$SRC/lease-enqueue.sh" "$d/fleet/lease-enqueue.sh"
  [ -n "$WORK_LEASE" ] && cp "$WORK_LEASE" "$d/fleet/work-lease.sh"
  # hooks shim: resolve FLEET from own location, exec the sandbox work-lease.sh
  cat > "$d/fleet/hooks/pre-commit" <<'EOH'
#!/usr/bin/env bash
set -euo pipefail
FLEET="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
exec bash "$FLEET/work-lease.sh" pre-commit
EOH
  cat > "$d/fleet/hooks/commit-msg" <<'EOH'
#!/usr/bin/env bash
set -euo pipefail
FLEET="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
exec bash "$FLEET/work-lease.sh" commit-msg "$@"
EOH
  [ -n "$FAKTORY" ] && cp "$FAKTORY" "$d/fleet/faktory/faktory-client.sh"
  chmod +x "$d/fleet/"*.sh "$d/fleet/hooks/"* "$d/fleet/faktory/"*.sh 2>/dev/null || true
  echo "$d"
}
# a lease-enqueue copy with reserve_lease() NEUTERED (the (a) revert: ignore the work-lease conflict).
revert_reserve(){ sed 's/^reserve_lease(){$/reserve_lease(){ return 0;/' "$SRC/lease-enqueue.sh"; }
# a lease-enqueue copy with the DUP marker/faktory guard NEUTERED (the (d) revert: double-push).
revert_dedup(){ sed 's/^if \[ -e "\$ENQ\/\$TICKET" \] || live_faktory_job; then$/if false; then/' "$SRC/lease-enqueue.sh"; }

# =============================================================================================
echo "== (a) two sessions cannot both hold the same ticket's reservation =="
if [ -z "$WORK_LEASE" ]; then
  echo "PENDING-WORK-LEASE: (a) needs fleet/work-lease.sh (WORK-LEASE-GATE not landed)"; PEND=$((PEND+1))
else
  d="$(mk_sandbox)"; F="$d/fleet"; T="TKT-A"
  printf 'tier: sonnet\n' > "$F/board/$T.md"
  w1="$d/w1"; w2="$d/w2"; mkdir -p "$w1" "$w2"
  # session 1 reserves (dispatch-time, --reserve-only: work-lease acquire only, no push needed).
  r1="$(WORK_LEASE_SH="$F/work-lease.sh" bash "$F/lease-enqueue.sh" "$T" --worktree "$w1" --session s1 --reserve-only 2>&1)"; rc1=$?
  # session 2 tries to reserve the SAME ticket → must be REFUSED (rc3).
  r2="$(WORK_LEASE_SH="$F/work-lease.sh" bash "$F/lease-enqueue.sh" "$T" --worktree "$w2" --session s2 --reserve-only 2>&1)"; rc2=$?
  nlease="$(ls "$F/state/leases" 2>/dev/null | wc -l | tr -d ' ')"
  if [ "$rc1" -eq 0 ] && [ "$rc2" -eq 3 ] && [ "$nlease" = "1" ]; then
    ok "a active: s1 reserves (rc0), s2 refused (rc3), exactly 1 lease"
  else bad "a active: rc1=$rc1 rc2=$rc2 leases=$nlease ($r2)"; fi
  # REVERT: neuter reserve_lease → s2 no longer refused → protection gone → RED.
  revert_reserve > "$F/lease-enqueue.sh"
  rm -f "$F/state/leases/"*  # fresh
  WORK_LEASE_SH="$F/work-lease.sh" bash "$F/lease-enqueue.sh" "$T" --worktree "$w1" --session s1 --reserve-only >/dev/null 2>&1
  WORK_LEASE_SH="$F/work-lease.sh" bash "$F/lease-enqueue.sh" "$T" --worktree "$w2" --session s2 --reserve-only >/dev/null 2>&1; rcR=$?
  if [ "$rcR" -ne 3 ]; then ok "a fail-on-revert: neutered reserve stops refusing (rc=$rcR)"; else bad "a fail-on-revert: still refused after revert"; fi
  rm -rf "$d"
fi

# =============================================================================================
echo "== (b) a manager-sub commit for an un-reserved ticket is REFUSED =="
if [ -z "$WORK_LEASE" ]; then
  echo "PENDING-WORK-LEASE: (b) needs fleet/work-lease.sh (WORK-LEASE-GATE not landed)"; PEND=$((PEND+1))
else
  d="$(mk_sandbox)"; F="$d/fleet"; T="TKT-B"
  printf 'tier: sonnet\n' > "$F/board/$T.md"
  R="$d/repo"; git init -q "$R"
  git -C "$R" config user.email t@t; git -C "$R" config user.name t
  git -C "$R" commit -q --allow-empty -m init
  W="$d/wt"; git -C "$R" worktree add -q -b "$T" "$W" >/dev/null 2>&1
  git -C "$W" config core.hooksPath "$F/hooks"
  echo x > "$W/f.txt"; git -C "$W" add f.txt
  # un-reserved commit → pre-commit hook must REFUSE.
  git -C "$W" commit -q -m "work" >/dev/null 2>&1; rc_unleased=$?
  # now go through the chokepoint's reservation (acquire the lease in W) → commit allowed.
  ( cd "$W" && bash "$F/work-lease.sh" acquire "$T" sess-b ) >/dev/null 2>&1
  git -C "$W" commit -q -m "work" >/dev/null 2>&1; rc_leased=$?
  if [ "$rc_unleased" -ne 0 ] && [ "$rc_leased" -eq 0 ]; then
    ok "b active: un-reserved commit REFUSED, reserved commit allowed"
  else bad "b active: unleased_rc=$rc_unleased leased_rc=$rc_leased (expected !=0 then 0)"; fi
  # REVERT: WORK_LEASE_BYPASS=1 (gate disabled) → un-reserved commit slips through → RED.
  git -C "$R" worktree add -q -b "${T}-rev" "$d/wt2" >/dev/null 2>&1
  git -C "$d/wt2" config core.hooksPath "$F/hooks"
  printf 'tier: sonnet\n' > "$F/board/${T}-rev.md"
  echo y > "$d/wt2/g.txt"; git -C "$d/wt2" add g.txt
  WORK_LEASE_BYPASS=1 git -C "$d/wt2" commit -q -m "work" >/dev/null 2>&1; rcB=$?
  if [ "$rcB" -eq 0 ]; then ok "b fail-on-revert: bypass lets un-reserved commit through (gate is what blocks)"; else bad "b fail-on-revert: bypass still blocked (rc=$rcB)"; fi
  rm -rf "$d"
fi

# =============================================================================================
echo "== (c) an ACKed ticket cannot be re-fetched after a Faktory container restart =="
if ! faktory_live; then
  pend "(c) needs the REAL Faktory server from FAKTORY-ADOPT (client=$( [ -n "$FAKTORY" ] && echo present || echo absent ))"
else
  d="$(mk_sandbox)"; F="$d/fleet"; T="TKT-C-$$"
  Q="test-c-$$"
  bash "$F/faktory/faktory-client.sh" push --queue "$Q" --jobtype charon-run --jid "$T" --arg '["run"]' >/dev/null 2>&1
  bash "$F/faktory/faktory-client.sh" reserve --queue "$Q" --timeout 2 >/dev/null 2>&1
  bash "$F/faktory/faktory-client.sh" ack --jid "$T" >/dev/null 2>&1
  # restart the Faktory container (durability proof). Requires a restart hook from FAKTORY-ADOPT.
  if [ -n "${FAKTORY_RESTART_CMD:-}" ]; then
    eval "$FAKTORY_RESTART_CMD" >/dev/null 2>&1
    got="$(bash "$F/faktory/faktory-client.sh" reserve --queue "$Q" --timeout 2 2>/dev/null)"
    if [ -z "$got" ]; then ok "c active: ACKed jid not re-fetchable after restart"; else bad "c active: re-fetched an ACKed jid after restart ($got)"; fi
  else
    pend "(c) client live but no \$FAKTORY_RESTART_CMD to recreate the container (set it once FAKTORY-ADOPT lands)"
  fi
  rm -rf "$d"
fi

# =============================================================================================
echo "== (d) a double-enqueue of the same ticket-id creates exactly ONE job =="
if ! faktory_live; then
  pend "(d) needs the REAL Faktory server from FAKTORY-ADOPT (client=$( [ -n "$FAKTORY" ] && echo present || echo absent ))"
else
  d="$(mk_sandbox)"; F="$d/fleet"; T="TKT-D-$$"; Q="test-d-$$"
  # WORK_LEASE deliberately absent here → isolate the DEDUP (flock+marker) layer that (d) proves.
  enq(){ FAKTORY_CLIENT="$F/faktory/faktory-client.sh" WORK_LEASE_SH="/nonexistent" \
         bash "$1" "$T" --queue "$Q" --session sd -- charon-run.sh cwd out brief model1; }
  enq "$F/lease-enqueue.sh" >/dev/null 2>&1
  enq "$F/lease-enqueue.sh" >/dev/null 2>&1   # second push MUST be a DUP no-op
  # drain the queue and count reservable jobs for this jid.
  n=0
  for _ in 1 2 3; do
    j="$(bash "$F/faktory/faktory-client.sh" reserve --queue "$Q" --timeout 2 2>/dev/null)"
    [ -z "$j" ] && break
    case "$j" in *"$T"*) n=$((n+1)); bash "$F/faktory/faktory-client.sh" ack --jid "$T" >/dev/null 2>&1 ;; esac
  done
  if [ "$n" -eq 1 ]; then ok "d active: double-enqueue produced exactly ONE job"; else bad "d active: double-enqueue produced $n jobs (expected 1)"; fi
  # REVERT: neuter the DUP marker guard → both pushes land → >1 job → RED.
  revert_dedup > "$F/lease-enqueue.sh"; rm -f "$F/state/enqueued/"*
  Q2="test-d2-$$"
  enq2(){ FAKTORY_CLIENT="$F/faktory/faktory-client.sh" WORK_LEASE_SH="/nonexistent" \
          bash "$F/lease-enqueue.sh" "$T" --queue "$Q2" --session sd -- charon-run.sh cwd out brief model1; }
  enq2 >/dev/null 2>&1; enq2 >/dev/null 2>&1
  m=0
  for _ in 1 2 3; do
    j="$(bash "$F/faktory/faktory-client.sh" reserve --queue "$Q2" --timeout 2 2>/dev/null)"
    [ -z "$j" ] && break
    case "$j" in *"$T"*) m=$((m+1)); bash "$F/faktory/faktory-client.sh" ack --jid "$T" >/dev/null 2>&1 ;; esac
  done
  if [ "$m" -gt 1 ]; then ok "d fail-on-revert: neutered dedup produced $m jobs (>1)"; else bad "d fail-on-revert: still exactly-once after revert (m=$m)"; fi
  rm -rf "$d"
fi

echo "----------------------------------------------------------------"
echo "lease-exactly-once: PASS=$PASS FAIL=$FAIL PENDING=$PEND"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
