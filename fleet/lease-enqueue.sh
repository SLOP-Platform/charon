#!/usr/bin/env bash
# lease-enqueue.sh — THE single enqueue chokepoint for the exactly-once claim-lease.
#
# claim.sh stays the SELECTOR; the winning ticket-id is handed HERE, and this is the ONLY
# sanctioned path that starts work. It binds the two substrates into ONE lease-with-ack claim:
#
#   • FAKTORY-ADOPT   — fleet/faktory/faktory-client.sh is the durable job/lease STORE
#                       (push/reserve/ack/fail/info). We call it; we do NOT reimplement it.
#   • WORK-LEASE-GATE — fleet/work-lease.sh is the commit-boundary lease (acquire/check/release
#                       + pre-commit hook). We COMPOSE with it (acquire the reservation at
#                       dispatch, let its hook refuse un-reserved commits). We do NOT duplicate it.
#   • DEDUP-AT-STORE  — the LOCKED idempotent-enqueue mechanism: reuse the ALREADY-OWNED flock on
#                       state/lock (same primitive as claim.sh:207) + a durable
#                       state/enqueued/<id> marker; check + PUSH inside the held lock → atomic,
#                       no TOCTOU. NO second lock, NO second daemon.
#
# Closes all three re-claim paths (CLAIM-INTEGRITY-EVAL):
#   1. single enqueue chokepoint  — un-reserved commits refused by WORK-LEASE-GATE's hook (leak #1)
#   2. idempotent enqueue         — flock+marker dedup a double-PUSH → exactly ONE job (this file)
#   3. atomic terminal via ACK    — marker removed at the ACK terminal (done.sh/ack path, gap #3)
#
# ── deadlock note (why the two atomic ops are SEQUENCED, never nested) ────────────────────────
# work-lease.sh acquire does its OWN `exec 9>state/lock; flock 9` in a child process. If we held
# our flock on the same file and then called it, the child's flock would block forever waiting on
# us → deadlock. So: Op A (work-lease acquire, its own lock) runs to completion and releases FIRST;
# THEN Op B (our flock: dedup+push+marker) takes the lock. No nesting → no deadlock. Both are the
# SAME fleet mutex (state/lock) — that is the point: one lock, taken serially, not two locks.
#
# Usage:
#   lease-enqueue.sh <ticket-id> [--session S] [--worktree W] [--queue Q] [--jobtype T] \
#                    [--reserve-only] -- <charon-run.sh invocation...>
#   exit 0 = enqueued (or idempotent no-op DUP); 1 = push failed; 3 = already reserved; 2 = usage.
set -euo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE="$FLEET/state"
LOCK="$STATE/lock"          # REUSE claim.sh's fleet lock — do NOT build a second (WORK-LEASE-GATE crit 1)
ENQ="$STATE/enqueued"       # durable idempotency markers (state/enqueued/<ticket-id>)

# Composed dependencies. Env-overridable so the test harness can point at sandbox / sibling-worktree
# copies during PARALLEL development; in production both resolve inside fleet/. We never reimplement
# either surface — we call it.
FAKTORY_CLIENT="${FAKTORY_CLIENT:-$FLEET/faktory/faktory-client.sh}"
WORK_LEASE="${WORK_LEASE_SH:-$FLEET/work-lease.sh}"

QUEUE_DEF="${LEASE_QUEUE:-charon}"
JOBTYPE_DEF="${LEASE_JOBTYPE:-charon-run}"

mkdir -p "$ENQ" "$(dirname "$LOCK")"; : >>"$LOCK"

die(){ echo "lease-enqueue: $*" >&2; exit 2; }
have(){ [ -n "${1:-}" ] && [ -f "$1" ]; }

# ── arg parse ────────────────────────────────────────────────────────────────────────────────
TICKET=""; SESSION=""; WT=""; QUEUE="$QUEUE_DEF"; JOBTYPE="$JOBTYPE_DEF"; RESERVE_ONLY=false
INVOCATION=()
[ $# -ge 1 ] || die "usage: lease-enqueue.sh <ticket-id> [opts] -- <charon-run invocation...>"
TICKET="$1"; shift
case "$TICKET" in --*) die "first arg must be <ticket-id>, got '$TICKET'";; esac
while [ $# -gt 0 ]; do
  case "$1" in
    --session)      SESSION="${2:?--session needs value}"; shift 2;;
    --worktree)     WT="${2:?--worktree needs value}"; shift 2;;
    --queue)        QUEUE="${2:?--queue needs value}"; shift 2;;
    --jobtype)      JOBTYPE="${2:?--jobtype needs value}"; shift 2;;
    --reserve-only) RESERVE_ONLY=true; shift;;
    --)             shift; INVOCATION=("$@"); break;;
    *)              die "unknown arg '$1' (charon-run invocation must follow '--')";;
  esac
done
WT="${WT:-$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || echo "$PWD")}"
SESSION="${SESSION:-$(basename "$WT")}"

# JSON-encode the invocation array (pure bash; no jq dependency) → faktory --arg payload.
json_args(){
  local out="[" first=1 tok esc
  for tok in "$@"; do
    esc="${tok//\\/\\\\}"; esc="${esc//\"/\\\"}"
    if [ "$first" -eq 1 ]; then first=0; else out+=","; fi
    out+="\"$esc\""
  done
  out+="]"; printf '%s' "$out"
}

# is there a LIVE faktory job for this ticket-id? (contract: info rc0 => present)
live_faktory_job(){ have "$FAKTORY_CLIENT" && bash "$FAKTORY_CLIENT" info --jid "$TICKET" >/dev/null 2>&1; }

# ── Op A: WORK-LEASE reservation at DISPATCH (operator nit: reserve before BUILD, not just pre-commit)
# Reuses WORK-LEASE-GATE's atomic acquire (which itself reuses state/lock's flock — NO second lock).
# Bind the lease to the builder worktree by running acquire FROM that cwd (work-lease derives the
# worktree from cwd; we do not modify it). CONFLICT => another session already holds it => case (a):
# two sessions cannot both hold the reservation → refuse.
reserve_lease(){
  have "$WORK_LEASE" || { echo "lease-enqueue: WORK-LEASE absent ($WORK_LEASE) — skipping reservation" >&2; return 0; }
  if ( cd "$WT" && bash "$WORK_LEASE" acquire "$TICKET" "$SESSION" ) >/dev/null 2>&1; then
    return 0
  fi
  # acquire failed — distinguish "already reserved (live lease)" from a transient failure.
  if ( cd "$WT" && bash "$WORK_LEASE" check "$TICKET" ) >/dev/null 2>&1; then
    echo "RESERVED: $TICKET already holds a live work-lease — refusing double-reserve" >&2
    return 3
  fi
  echo "LEASE-ACQUIRE-FAILED: $TICKET (no live lease, acquire still failed)" >&2
  return 3
}

reserve_lease; rc=$?
[ "$rc" -eq 0 ] || exit "$rc"

if $RESERVE_ONLY; then
  echo "RESERVED $TICKET ($SESSION @ $WT)"
  exit 0
fi

# ── Op B: idempotent enqueue under the OWNED flock (LOCKED DEDUP-AT-STORE mechanism) ───────────
have "$FAKTORY_CLIENT" || die "faktory-client absent ($FAKTORY_CLIENT) — cannot enqueue (use --reserve-only, or wait for FAKTORY-ADOPT)"
exec 9>"$LOCK"; flock 9
# check-then-act, BOTH inside the held lock → atomic, no GET-then-SET window (TOCTOU).
if [ -e "$ENQ/$TICKET" ] || live_faktory_job; then
  echo "DUP: $TICKET already enqueued — no-op (exactly-once)"
  exit 0
fi
ARG_JSON="$(json_args "${INVOCATION[@]}")"
if ! bash "$FAKTORY_CLIENT" push --queue "$QUEUE" --jobtype "$JOBTYPE" --jid "$TICKET" --arg "$ARG_JSON"; then
  # PUSH FIRST, marker only on success → a failed push leaves NO phantom marker (ticket stays claimable).
  echo "PUSH-FAILED: $TICKET" >&2
  exit 1
fi
printf '%s\t%s\t%s\n' "$SESSION" "$WT" "$(date -u +%FT%TZ)" > "$ENQ/$TICKET"
echo "ENQUEUED $TICKET jid=$TICKET queue=$QUEUE"
exit 0
