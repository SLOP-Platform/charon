#!/usr/bin/env bash
# balance-canary.sh — BALANCE-CANARY: the money-path LEDGER-PERSISTENCE +
# FUNDING-CLASS PARK-LIFECYCLE canary (fleet/board/BALANCE-CANARY.md).
#
# WHY THIS EXISTS (design of record: DESIGN-PLANE-CANARY-SUITE Phase 3 "P3
# money/balance", operator-approved 2026-07-23):
#   fleet/flow-canary.sh STAGE 2 already proves the served-count + cost DELTA
#   advances (the #167 inert-meter guard). It does NOT prove the two properties
#   that make the money ledger TRUSTWORTHY across time:
#     1. LEDGER-DECREMENT PERSISTENCE — a served request that decrements the
#        tracked balance must STILL show the decrement on a SECOND, independent
#        /charon/status read. A per-read in-memory counter that recomputes to the
#        starting value on the next read would satisfy flow-canary's delta but is
#        a SILENT LEDGER LOSS: money spent, money not recorded. [[charon-meter-inert]]
#     2. FUNDING-CLASS PARK LIFECYCLE — draining a prepaid leg must PARK it
#        (parked=true), that park must PERSIST across a re-read (the balance.py
#        park set claims to survive a gateway restart), the parked leg must be
#        EXCLUDED from the served path (#188 dead-no-op class), and a RE-ADMIT
#        must clear the park so the leg is eligible to serve again.
#   Every one of these has been a silent-break class in this fleet. This canary
#   asserts each as an OBSERVABLE EFFECT so the whole class is "caught every run".
#
# THE CRUX — assert PERSISTED, not merely OBSERVED-ONCE. A single status read
# proving a decrement/park happened is not enough: an in-memory-only ledger or
# park flag can show the right value on the first read and lose it on the next.
# Each stage below takes TWO independent reads and asserts the effect SURVIVES.
#
# SCOPE: read-only assertion against the LIVE /charon/status surface + the
# gateway's OWN drain/re-arm control (POST /charon/balance op=park|rearm). This
# canary NEVER re-implements BalanceTracker or the meter — it observes the meter
# of record exactly as flow-canary.sh does and drives park/re-arm through the
# gateway's own console control endpoint (adopt, don't hand-roll a second meter).
# It EXTENDS flow-canary's STAGE 2/3 coverage; it does not duplicate the delta
# assertion flow-canary already proves.
#
# GREEN IS NOT PROOF. The fail-on-revert dogfood in
# fleet/tests/balance-canary.test.sh seeds a real fault of each persistence class
# against a hermetic fake gateway (mirroring flow-canary.test.sh's scenario-
# rewrite pattern) and proves this script goes RED on it, then GREEN on revert.
#
# ── ADOPT, DON'T HAND-ROLL ──────────────────────────────────────────────────
#   This canary SOURCES fleet/flow-canary.sh and REUSES its plumbing verbatim:
#     • _bearer_token   — canonical opencode.json token derive (env-registry.sh:57)
#     • _tier_chain     — tier chain from tier-models.tsv
#     • _status_json    — GET /charon/status -> file (the observable surface)
#     • RED / _pass / _red / _info / _stage — the same GREEN/RED reporting shape
#     • FC_* env contract + $FCTMP scratch dir + its EXIT cleanup trap
#   The novel slice is ONLY the two persistence stages below.
#
# EXIT: 0 = every stage GREEN. non-zero = at least one stage RED (loud).
#
# ── ENV (BC_* novel; FC_* inherited from flow-canary.sh) ────────────────────
#   FC_GATEWAY_URL / FC_TOKEN / FC_OPENCODE_CFG / FC_TIER / FC_TIER_TSV /
#   FC_PROMPT / FC_MAX_TOKENS / FC_REQ_TIMEOUT_S / FC_STATUS_TIMEOUT_S / FC_NONCE
#       — see fleet/flow-canary.sh header (same meanings; the test injects a fake).
#   BC_DRAIN_PROVIDER   leg to exercise the park lifecycle on. Default: auto-pick
#                       the first funded, unparked, in-pool leg from /charon/status.
#   BC_PARK_CTL_CMD     override for the drain/re-arm control. Receives
#                       "<provider> <op>" (op = park|rearm). Default: POST
#                       /charon/balance {provider,op} to the live gateway. The
#                       hermetic dogfood lets the default hit its fake gateway.
#   BC_CONSOLE_COOKIE   console session cookie for the live /charon/balance write
#                       (the /charon/* console surface is session-gated, not the
#                       /v1 Bearer token). Optional; unused by the default path
#                       when the deployment accepts the Bearer token.
set -uo pipefail

FLEET="${CHARON_FLEET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

# ── adopt flow-canary's plumbing (token/status/tier + RED/_pass/_red/_info) ──
FC_LIB="${FC_LIB:-$FLEET/flow-canary.sh}"
if [ ! -r "$FC_LIB" ]; then
  echo "balance-canary: cannot source flow-canary lib at $FC_LIB" >&2
  exit 2
fi
# shellcheck source=/dev/null
# Sourcing DEFINES the helpers + FC_* env + $FCTMP + RED; flow-canary's own main
# does NOT run (guarded by its BASH_SOURCE test).
. "$FC_LIB"

# ── BC-specific env ─────────────────────────────────────────────────────────
BC_DRAIN_PROVIDER="${BC_DRAIN_PROVIDER:-}"
BC_PARK_CTL_CMD="${BC_PARK_CTL_CMD:-}"
BC_CONSOLE_COOKIE="${BC_CONSOLE_COOKIE:-}"
BC_DECREMENT_FLOOR="${BC_DECREMENT_FLOOR:-0.0}"   # a spend below this is "no decrement"

# ── read a balance[provider][field] from a status snapshot ──────────────────
_bc_bal(){ # <status_file> <provider> <field> -> value | None
  python3 -c "
import json,sys
try: d=json.load(open(sys.argv[1]))
except Exception: print('None'); sys.exit(0)
b=(d.get('balance') or {}).get(sys.argv[2]) or {}
v=b.get(sys.argv[3])
print('None' if v is None else v)
" "$1" "$2" "$3" 2>/dev/null
}

# ── aggregate usage.cost_usd from a status snapshot ─────────────────────────
_bc_usage_cost(){ # <status_file> -> float
  python3 -c "
import json,sys
try: print((json.load(open(sys.argv[1])).get('usage') or {}).get('cost_usd',0) or 0)
except Exception: print(0)
" "$1" 2>/dev/null
}

# ── served-count delta for a provider between two snapshots ─────────────────
_bc_served_delta(){ # <before> <after> <provider> -> int
  python3 -c "
import json,sys
def g(p):
    try: return json.load(open(p))
    except Exception: return {}
b=g(sys.argv[1]);a=g(sys.argv[2]);pr=sys.argv[3]
def sv(d): return int(((d.get('providers') or {}).get(pr) or {}).get('served',0) or 0)
print(sv(a)-sv(b))
" "$1" "$2" "$3" 2>/dev/null
}

# ── float compare helpers (bash can't) ──────────────────────────────────────
_bc_lt(){  python3 -c "import sys;print('yes' if float(sys.argv[1])<float(sys.argv[2]) else 'no')" "$1" "$2" 2>/dev/null; }
_bc_gt(){  python3 -c "import sys;print('yes' if float(sys.argv[1])>float(sys.argv[2]) else 'no')" "$1" "$2" 2>/dev/null; }
_bc_eq(){  python3 -c "import sys;print('yes' if abs(float(sys.argv[1])-float(sys.argv[2]))<1e-12 else 'no')" "$1" "$2" 2>/dev/null; }

# ── drain / re-arm control (adopt the gateway's own /charon/balance write) ──
_bc_park_ctl(){ # <provider> <op:park|rearm>
  local prov="$1" op="$2"
  if [ -n "$BC_PARK_CTL_CMD" ]; then
    # shellcheck disable=SC2086
    $BC_PARK_CTL_CMD "$prov" "$op"
    return $?
  fi
  local tok payload
  tok="$(_bearer_token)"
  payload="$(python3 -c "import json,sys;print(json.dumps({'provider':sys.argv[1],'op':sys.argv[2]}))" "$prov" "$op" 2>/dev/null)"
  curl -s --max-time "${FC_REQ_TIMEOUT_S:-45}" \
    -H "Authorization: Bearer $tok" -H "Content-Type: application/json" \
    ${BC_CONSOLE_COOKIE:+-H "Cookie: $BC_CONSOLE_COOKIE"} \
    -X POST "$FC_GATEWAY_URL/charon/balance" --data-binary "$payload" >/dev/null 2>&1
}

# ── send ONE real request; echo "served\treasons\thttp_code" ────────────────
_bc_send(){ # <tok> <head_model>
  local tok="$1" head="$2"
  local hdr="$FCTMP/bc_hdr.txt" body="$FCTMP/bc_body.json" reqbody="$FCTMP/bc_req.json"
  # nonce defeats the response cache (a cache hit exercises no pool leg / ledger)
  local nonce="${FC_NONCE:-$(date -u +%s)-$RANDOM}"
  python3 -c "
import json,sys
json.dump({'model': sys.argv[1],
           'messages': [{'role':'user','content': sys.argv[2] + ' (balance-canary ' + sys.argv[4] + ')'}],
           'max_tokens': int(sys.argv[3])}, open(sys.argv[5],'w'))
" "$head" "${FC_PROMPT:-reply with the single word: PONG}" "${FC_MAX_TOKENS:-16}" "$nonce" "$reqbody" 2>/dev/null
  local code
  code="$(curl -s --max-time "${FC_REQ_TIMEOUT_S:-45}" -o "$body" -D "$hdr" -w '%{http_code}' \
    -H "Authorization: Bearer $tok" -H "Content-Type: application/json" \
    -X POST "$FC_GATEWAY_URL/v1/chat/completions" --data-binary "@$reqbody" 2>/dev/null)"
  local provider reasons
  provider="$(grep -i '^X-Charon-Provider:' "$hdr" 2>/dev/null | head -1 | sed 's/^[^:]*:[[:space:]]*//; s/[[:space:]]*$//' | tr -d '\r')"
  reasons="$(grep -i '^X-Charon-Failover-Reasons:' "$hdr" 2>/dev/null | head -1 | sed 's/^[^:]*:[[:space:]]*//' | tr -d '\r')"
  printf '%s\t%s\t%s\n' "$provider" "$reasons" "$code"
}

# ── STAGE A — LEDGER-DECREMENT PERSISTENCE ──────────────────────────────────
_stage_ledger(){ # <tok> <tier> <head_model>
  local tok="$1" tier="$2" head="$3"
  local A="$FCTMP/bc_A.json" B="$FCTMP/bc_B.json" C="$FCTMP/bc_C.json"
  _stage "STAGE A — LEDGER-DECREMENT PERSISTENCE (tier=$tier, head=$head)"

  if ! _status_json "$tok" "$A"; then
    _red "ledger: /charon/status unreadable (before) at $FC_GATEWAY_URL — cannot canary"
    return
  fi

  local sent served reasons code
  sent="$(_bc_send "$tok" "$head")"
  served="$(printf '%s' "$sent" | cut -f1)"
  reasons="$(printf '%s' "$sent" | cut -f2)"
  code="$(printf '%s' "$sent" | cut -f3)"
  if [ "$code" != "200" ]; then
    _red "ledger: served request returned HTTP $code (not 200) — cannot exercise the ledger"
    return
  fi
  if [ -z "$served" ]; then
    _red "ledger: no X-Charon-Provider header — cannot identify the metered leg"
    return
  fi

  # TWO independent post-request reads (the persistence property lives here)
  if ! _status_json "$tok" "$B"; then _red "ledger: /charon/status unreadable (read #1)"; return; fi
  if ! _status_json "$tok" "$C"; then _red "ledger: /charon/status unreadable (read #2)"; return; fi
  _info "served-by: $served   failover: ${reasons:-<none>}"

  # anti-inert baseline (adopted from flow-canary STAGE 2): served counter advanced
  local dserved
  dserved="$(_bc_served_delta "$A" "$B" "$served")"; dserved="${dserved:-0}"
  if [ "$dserved" -ge 1 ] 2>/dev/null; then
    _pass "ledger/meter: served-count for '$served' advanced by $dserved — the request was metered (spend exists to persist)"
  else
    _red "ledger/meter: served-count for '$served' did NOT advance (delta=$dserved) — INERT METER (#167 class); no spend recorded to persist"
  fi

  local remA remB remC
  remA="$(_bc_bal "$A" "$served" remaining_usd)"
  remB="$(_bc_bal "$B" "$served" remaining_usd)"
  remC="$(_bc_bal "$C" "$served" remaining_usd)"

  if [ "$remA" != "None" ] && [ "$remB" != "None" ]; then
    # TRACKED prepaid leg: remaining_usd must DECREASE and the decrement must PERSIST
    _info "tracked leg '$served' remaining_usd:  before=$remA  read1=$remB  read2=$remC"
    if [ "$(_bc_lt "$remB" "$remA")" = "yes" ]; then
      _pass "ledger: served request DECREMENTED the tracked balance of '$served' ($remA -> $remB) — spend recorded to the ledger"
    else
      _red "ledger: served request did NOT decrement '$served' balance (before=$remA read1=$remB) — DECREMENT NO-OP (inert ledger; #167 money class)"
    fi
    if [ "$remC" != "None" ] && [ "$(_bc_eq "$remC" "$remB")" = "yes" ]; then
      _pass "ledger: the decrement PERSISTED across an independent re-read (read1=$remB == read2=$remC) — a recorded ledger, not an in-memory counter that resets"
    else
      _red "ledger: the decrement did NOT PERSIST — read1=$remB but read2=$remC (value reset on the independent re-read) — NON-PERSISTENT LEDGER (silent money loss)"
    fi
  else
    # UNTRACKED / free served leg: fall back to the aggregate usage ledger
    local cA cB cC
    cA="$(_bc_usage_cost "$A")"; cB="$(_bc_usage_cost "$B")"; cC="$(_bc_usage_cost "$C")"
    _info "served leg '$served' has no tracked balance (remaining_usd=None) — asserting on aggregate usage.cost_usd:  before=$cA  read1=$cB  read2=$cC"
    if [ "$(_bc_gt "$cB" "$cA")" = "yes" ]; then
      _pass "ledger: served request RECORDED aggregate spend ($cA -> $cB) to usage.cost_usd"
    else
      _red "ledger: served request recorded NO aggregate spend (before=$cA read1=$cB) — DECREMENT NO-OP (inert ledger)"
    fi
    if [ "$(_bc_eq "$cC" "$cB")" = "yes" ]; then
      _pass "ledger: aggregate spend PERSISTED across an independent re-read ($cB == $cC)"
    else
      _red "ledger: aggregate spend did NOT PERSIST — read1=$cB but read2=$cC (reset on re-read) — NON-PERSISTENT LEDGER"
    fi
  fi
}

# ── STAGE B — FUNDING-CLASS PARK LIFECYCLE ──────────────────────────────────
_stage_park(){ # <tok> <tier> <head_model>
  local tok="$1" tier="$2" head="$3"
  local S0="$FCTMP/bc_S0.json" S1="$FCTMP/bc_S1.json" S2="$FCTMP/bc_S2.json"
  local SX="$FCTMP/bc_SX.json" S3="$FCTMP/bc_S3.json"
  _stage "STAGE B — FUNDING-CLASS PARK LIFECYCLE (tier=$tier)"

  if ! _status_json "$tok" "$S0"; then _red "park: /charon/status unreadable (baseline)"; return; fi

  # pick the drain target: explicit BC_DRAIN_PROVIDER, else first funded/unparked/in-pool leg
  local D="$BC_DRAIN_PROVIDER"
  if [ -z "$D" ]; then
    D="$(python3 -c "
import json,sys
try: d=json.load(open(sys.argv[1]))
except Exception: print(''); sys.exit(0)
bal=d.get('balance') or {}
pool=set((d.get('pools') or {}).get(sys.argv[2]) or [])
for p,v in bal.items():
    if v.get('funding_class') is not None and not v.get('parked') and not v.get('drained') and (not pool or p in pool):
        print(p); sys.exit(0)
print('')
" "$S0" "$head" 2>/dev/null)"
  fi
  if [ -z "$D" ]; then
    _red "park: no eligible drain target (no funded, unparked, in-pool leg on the gateway) — cannot exercise the park lifecycle"
    return
  fi
  _info "drain target: $D"

  # baseline: D MUST start unparked, else a park transition is unprovable
  local p0; p0="$(_bc_bal "$S0" "$D" parked)"
  case "$p0" in
    True|true) _red "park: drain target '$D' is ALREADY parked at baseline — cannot prove a park transition"; return ;;
  esac
  _pass "park: drain target '$D' starts unparked (baseline clean)"

  # 1) DRAIN / PARK D via the gateway's own control surface
  _bc_park_ctl "$D" park

  # 2) parked=true on read #1
  if ! _status_json "$tok" "$S1"; then _red "park: /charon/status unreadable (read #1 post-park)"; return; fi
  local p1; p1="$(_bc_bal "$S1" "$D" parked)"
  case "$p1" in
    True|true) _pass "park: '$D' reports parked=true after the drain (read #1)" ;;
    *)         _red "park: '$D' did NOT report parked=true after the drain (read #1 parked=$p1) — PARK NO-OP" ;;
  esac

  # 3) parked=true STILL on an independent read #2 (PERSISTENCE)
  if ! _status_json "$tok" "$S2"; then _red "park: /charon/status unreadable (read #2 post-park)"; return; fi
  local p2; p2="$(_bc_bal "$S2" "$D" parked)"
  case "$p2" in
    True|true) _pass "park: '$D' parked=true PERSISTED across an independent re-read (read #2) — a persisted park set, not an in-memory flag that resets" ;;
    *)         _red "park: '$D' parked flag RESET on re-read (read1=$p1 read2=$p2) — PARK NOT PERSISTED (the survive-restart claim is false)" ;;
  esac

  # 4) EXCLUDED from the served path (reuse flow-canary STAGE 3 #188 pattern)
  local sent served reasons attempted excl
  sent="$(_bc_send "$tok" "$head")"
  served="$(printf '%s' "$sent" | cut -f1)"
  reasons="$(printf '%s' "$sent" | cut -f2)"
  _status_json "$tok" "$SX" || : > "$SX"
  attempted="$(printf '%s' "$reasons" | grep -oE '[A-Za-z0-9_-]+=' | sed 's/=$//' | paste -sd, - 2>/dev/null)"
  excl="$(python3 -c "
import sys
served=sys.argv[1].strip()
attempted=[x.strip() for x in sys.argv[2].split(',') if x.strip()]
D=sys.argv[3]
path=set()
if served: path.add(served)
for a in attempted: path.add(a)
print('SERVED' if D==served else ('ATTEMPTED' if D in path else 'EXCLUDED'))
" "$served" "$attempted" "$D" 2>/dev/null)"
  _info "post-park served-path: served=$served attempted=[${attempted:-<none>}]"
  case "$excl" in
    EXCLUDED)  _pass "park: parked leg '$D' was EXCLUDED from the served path (served=$served) — exclusion fired (#188 dead-no-op guard)" ;;
    SERVED)    _red "park: parked leg '$D' was itself SERVED — exclusion is a DEAD NO-OP (#188 class)" ;;
    ATTEMPTED) _red "park: parked leg '$D' was ATTEMPTED in the route despite being parked — exclusion did not fire (#188 class)" ;;
    *)         _red "park: could not determine whether parked leg '$D' was excluded (served='$served')" ;;
  esac

  # 5) RE-ADMIT D — park cleared + leg eligible to serve again
  _bc_park_ctl "$D" rearm
  if ! _status_json "$tok" "$S3"; then _red "park: /charon/status unreadable (post-rearm)"; return; fi
  local p3 inpool
  p3="$(_bc_bal "$S3" "$D" parked)"
  inpool="$(python3 -c "
import json,sys
try: d=json.load(open(sys.argv[1]))
except Exception: print('no'); sys.exit(0)
ch=(d.get('pools') or {}).get(sys.argv[2]) or []
print('yes' if sys.argv[3] in ch else 'no')
" "$S3" "$head" "$D" 2>/dev/null)"
  case "$p3" in
    False|false) _pass "park: '$D' RE-ADMITTED — parked cleared (parked=$p3); pool-eligible=$inpool — the re-armed leg can serve again" ;;
    *)           _red "park: '$D' still parked after re-admit (parked=$p3) — RE-ADMIT NO-OP (a re-armed leg stays excluded from serving)" ;;
  esac
}

# ── run one tier chain end-to-end ───────────────────────────────────────────
bc_run(){
  local tier="${FC_TIER:-strong}" tok chain head
  tok="$(_bearer_token)"
  if [ -z "$tok" ]; then
    _red "no gateway Bearer token (FC_TOKEN unset and ${FC_OPENCODE_CFG:-<cfg>} unreadable/empty)"
    return
  fi
  chain="$(_tier_chain "$tier")"
  head="$(printf '%s' "$chain" | cut -d, -f1 | tr -d '[:space:]')"
  if [ -z "$head" ]; then
    _red "tier '$tier' has no failover chain in ${FC_TIER_TSV:-<tsv>}"
    return
  fi
  echo "BALANCE-CANARY  gateway=$FC_GATEWAY_URL  tier=$tier  head=$head"
  _stage_ledger "$tok" "$tier" "$head"
  _stage_park   "$tok" "$tier" "$head"
}

bc_main(){
  echo "════════════════════════════════════════════════════════════"
  echo " BALANCE-CANARY — money-path ledger-persistence + park-lifecycle canary"
  echo " $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "════════════════════════════════════════════════════════════"
  bc_run
  echo
  if [ "$RED" -eq 0 ]; then
    echo "════ BALANCE-CANARY: GREEN — ledger persists + park lifecycle sound ════"
    exit 0
  fi
  echo "████ BALANCE-CANARY: RED — a money-path break was caught (see RED lines above) ████"
  exit 1
}

# Only run main when executed directly (sourcing for tests exposes the fns).
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  bc_main "$@"
fi
