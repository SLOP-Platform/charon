#!/usr/bin/env bash
# flow-canary.sh — FLOW-CANARY: the PROACTIVE end-to-end money-path health check.
#
# WHY THIS EXISTS (fleet/board/FLOW-CANARY.md, operator-approved 2026-07-23):
#   Every silent break this fleet has hit — stray `standard` tier, dead-no-op
#   cooldown (#188), funding_class-inert, V4-Pro mis-route, the inert meter
#   (#167) — was found BY LUCK. This canary sends a REAL request through the
#   LIVE gateway per tier and ASSERTS OBSERVABLE EFFECTS at every stage, so the
#   whole silent-break class is "caught every run" instead of "found by luck".
#
# THE R44 CRUX — assert EXERCISED, not merely REACHABLE. A 200 from the gateway
# proves nothing. Each stage below asserts a side effect that a route-miss, an
# inert meter, or a dead-no-op exclusion CANNOT produce:
#   1. ROUTE   — X-Charon-Provider is a provider IN the tier model's pool, the
#                resolved upstream model is real (and never Anthropic), and the
#                SERVED leg is a funded-FREE class (free-first respected).
#   2. METER   — the served provider's observer counter ADVANCES (served +>=1)
#                and the per-request priced amount is present on the response.
#                An inert meter (#167) leaves the counter flat -> RED.
#   3. PARK    — no parked/drained provider appears anywhere in the served path
#                (served leg OR any attempted failover leg). A dead-no-op
#                exclusion (#188) that lets a parked provider be attempted -> RED.
#   4. CONFIG  — the tier set is canonical per `charon tier ranks`
#                (economy<strong<frontier, ranks 1/2/3, and NO stray `standard`),
#                the tier's head model is served, its providers are keyed.
#
# THIN VERTICAL SLICE: this runs ONE tier chain end-to-end (default: strong).
# It is deliberately structured to WIDEN to the tier x provider x model matrix —
# `run_tier <tier>` is the unit; a matrix driver loops it over
# `economy strong frontier` (and, later, per-model / per-provider legs). The
# assertions do not change; only the loop widens.
#
# GREEN IS NOT PROOF. The fail-on-revert dogfood in
# fleet/tests/flow-canary.test.sh seeds a real fault of each class against a
# hermetic fake gateway and proves this script goes RED on it, then GREEN on
# revert. If you touch a stage here, that test is what keeps it honest.
#
# ── ADOPT, DON'T HAND-ROLL ──────────────────────────────────────────────────
#   • gateway URL + Bearer token: the canonical derive-from-opencode.json
#     method documented in fleet/env-registry.sh:57 (CHARON_GATEWAY_TOKEN shell
#     env is STALE per preflight.sh:detect_gateway_token_drift — always
#     re-derive from the live opencode config).
#   • tier failover chain: fleet/tier-models.tsv, parsed the same way as
#     fleet/env-registry.sh:parse_tier_chain.
#   • tier canonicality: `charon tier ranks` (src/charon/cli.py:_tier_ranks) —
#     the SSOT for what a tier name means. Never re-derive tier ranks here.
#   • observable state: the gateway's own /charon/status snapshot
#     (proxy_server.py:status_snapshot) — providers[*].{served,cost}, usage,
#     and balance[*].{funding_class,parked,drained}. One source, not a second
#     copy of the meter.
#
# EXIT: 0 = all stages GREEN. non-zero = at least one stage RED (loud).
#
# ── ENV (all overridable; the test harness injects a hermetic fake) ─────────
#   FC_GATEWAY_URL       default http://10.0.1.60:8080   (4-LOM live gateway)
#   FC_TOKEN             default: derived from FC_OPENCODE_CFG
#   FC_OPENCODE_CFG      default ~/.config/opencode/opencode.json
#   FC_TIER              default strong                  (the slice's tier)
#   FC_TIER_TSV          default <fleet>/tier-models.tsv
#   FC_TIER_RANKS_CMD    default "charon tier ranks"
#   FC_PROMPT            default "reply with the single word: PONG"
#   FC_MAX_TOKENS        default 16
#   FC_REQ_TIMEOUT_S     default 45
#   FC_STATUS_TIMEOUT_S  default 8
set -uo pipefail

FLEET="${CHARON_FLEET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

FC_GATEWAY_URL="${FC_GATEWAY_URL:-http://10.0.1.60:8080}"
FC_OPENCODE_CFG="${FC_OPENCODE_CFG:-$HOME/.config/opencode/opencode.json}"
FC_TIER="${FC_TIER:-strong}"
FC_TIER_TSV="${FC_TIER_TSV:-$FLEET/tier-models.tsv}"
FC_TIER_RANKS_CMD="${FC_TIER_RANKS_CMD:-charon tier ranks}"
FC_PROMPT="${FC_PROMPT:-reply with the single word: PONG}"
FC_MAX_TOKENS="${FC_MAX_TOKENS:-16}"
FC_REQ_TIMEOUT_S="${FC_REQ_TIMEOUT_S:-45}"
FC_STATUS_TIMEOUT_S="${FC_STATUS_TIMEOUT_S:-8}"

# The canonical tier set (economy/strong/frontier), ranks 1/2/3. This is the
# axis the ticket's config-sanity stage guards; a `standard` here is the exact
# drift class that once shipped silently.
CANONICAL_TIERS="economy strong frontier"

RED=0
_pass(){ echo "  GREEN  $1"; }
_red(){ RED=1; echo "  RED    $1"; }
_info(){ echo "         $1"; }
_stage(){ echo; echo "── $1 ─────────────────────────────────────────"; }

# ── token: canonical opencode.json derive (env-registry.sh:57) ──────────────
_bearer_token(){
  [ -n "${FC_TOKEN:-}" ] && { printf '%s' "$FC_TOKEN"; return 0; }
  [ -r "$FC_OPENCODE_CFG" ] || return 1
  python3 -c "
import json, sys
try:
    d = json.load(open('$FC_OPENCODE_CFG'))
    tok = (((d.get('provider') or {}).get('charon') or {}).get('options') or {}).get('apiKey')
    sys.stdout.write(tok or '')
except Exception:
    pass
" 2>/dev/null
}

# ── tier chain from tier-models.tsv (env-registry.sh:parse_tier_chain) ──────
_tier_chain(){
  local tier="$1"
  [ -r "$FC_TIER_TSV" ] || { echo "flow-canary: tier-models.tsv unreadable at $FC_TIER_TSV" >&2; return 1; }
  python3 -c "
import sys
target = '$tier'.lower()
with open('$FC_TIER_TSV') as f:
    for raw in f:
        line = raw.strip()
        if not line or line.startswith('#') or '\t' not in line:
            continue
        k, _, v = line.partition('\t')
        if k.strip().lower() == target:
            print(v.strip()); sys.exit(0)
sys.exit(0)
"
}

# ── GET /charon/status -> JSON on stdout (empty on failure) ─────────────────
_status_json(){
  local tok="$1"
  curl -s --max-time "$FC_STATUS_TIMEOUT_S" \
    -H "Authorization: Bearer $tok" -H "Accept: application/json" \
    "$FC_GATEWAY_URL/charon/status" 2>/dev/null || true
}

# ── STAGE 4: CONFIG SANITY (cheap, no request — run first) ──────────────────
# Asserts the tier set is canonical per `charon tier ranks`, surfaces the
# stray-`standard` drift class, and that the tier's head model is served with
# keyed providers.
_stage_config(){
  local tok="$1" status_json="$2" tier="$3" head_model="$4"
  _stage "STAGE 4 — CONFIG SANITY (tier=$tier)"

  local ranks
  ranks="$($FC_TIER_RANKS_CMD 2>/dev/null)"
  if [ -z "$ranks" ]; then
    _red "config: \`$FC_TIER_RANKS_CMD\` produced no output — cannot verify tier canonicality"
    return
  fi
  # name->rank map from the ranks output. Assert canonical set present with the
  # 1/2/3 ordering, the requested tier present, and NO stray `standard`.
  python3 - "$tier" <<PYEOF
import sys
tier = sys.argv[1].lower()
ranks = {}
for line in """$ranks""".splitlines():
    line = line.strip()
    if not line: continue
    parts = line.split()
    if len(parts) < 2: continue
    name, rank = parts[0].lower(), parts[-1]
    try: ranks[name] = int(rank)
    except ValueError: pass
canon = "economy strong frontier".split()
bad = 0
missing = [t for t in canon if t not in ranks]
if missing:
    print(f"MISSING {' '.join(missing)}"); bad = 1
else:
    if not (ranks["economy"] < ranks["strong"] < ranks["frontier"]):
        print(f"ORDER economy={ranks['economy']} strong={ranks['strong']} frontier={ranks['frontier']}"); bad = 1
if "standard" in ranks:
    print("STRAYSTANDARD"); bad = 1
if tier not in ranks:
    print(f"TIERMISSING {tier}"); bad = 1
sys.exit(1 if bad else 0)
PYEOF
  local rc=$?
  if [ "$rc" -eq 0 ]; then
    _pass "config: tier set canonical (economy<strong<frontier), no stray 'standard', '$tier' present"
  else
    _red "config: tier ranks NON-canonical (see above token: MISSING/ORDER/STRAYSTANDARD/TIERMISSING) — drift"
  fi

  # head model served + providers keyed (from the live status snapshot)
  if [ -z "$head_model" ]; then
    _red "config: tier '$tier' has no failover chain in $FC_TIER_TSV"
    return
  fi
  python3 - "$head_model" <<PYEOF
import json, sys
head = sys.argv[1]
try:
    d = json.loads(r'''$status_json''')
except Exception:
    print("NOSTATUS"); sys.exit(1)
pools = d.get("pools") or {}
bal = d.get("balance") or {}
chain = pools.get(head)
if not chain:
    print(f"NOTSERVED {head}"); sys.exit(1)
unkeyed = [p for p in chain if p not in bal]
if unkeyed:
    # a provider in the served chain with no balance/funding-class record is a
    # config-drift signal (provider not configured/keyed on the gateway).
    print("UNKEYED " + ",".join(unkeyed)); sys.exit(1)
print("OK " + ",".join(chain))
sys.exit(0)
PYEOF
  local rc2=$?
  local chainline
  chainline="$(python3 -c "
import json
try:
    d=json.loads(r'''$status_json'''); print(','.join((d.get('pools') or {}).get('$head_model') or []))
except Exception: pass
" 2>/dev/null)"
  if [ "$rc2" -eq 0 ]; then
    _pass "config: head model '$head_model' served; providers keyed [$chainline]"
  else
    _red "config: head model '$head_model' not served OR has unkeyed providers — config drift"
  fi
}

# ── STAGES 1-3: send the REAL request, then assert route/meter/park ─────────
_stage_flow(){
  local tok="$1" before_json="$2" tier="$3" head_model="$4"
  local hdr body code
  hdr="$(mktemp)"; body="$(mktemp)"
  trap 'rm -f "$hdr" "$body"' RETURN

  code="$(curl -s --max-time "$FC_REQ_TIMEOUT_S" -o "$body" -D "$hdr" -w '%{http_code}' \
    -H "Authorization: Bearer $tok" -H "Content-Type: application/json" \
    -X POST "$FC_GATEWAY_URL/v1/chat/completions" \
    -d "$(python3 -c "
import json,sys
print(json.dumps({'model': sys.argv[1],
                  'messages': [{'role':'user','content': sys.argv[2]}],
                  'max_tokens': int(sys.argv[3])}))
" "$head_model" "$FC_PROMPT" "$FC_MAX_TOKENS")" 2>/dev/null)"

  local after_json
  after_json="$(_status_json "$tok")"

  local provider reasons resolved_model req_cost
  provider="$(grep -i '^X-Charon-Provider:' "$hdr" | head -1 | sed 's/^[^:]*:[[:space:]]*//; s/[[:space:]]*$//' | tr -d '\r')"
  reasons="$(grep -i '^X-Charon-Failover-Reasons:' "$hdr" | head -1 | sed 's/^[^:]*:[[:space:]]*//' | tr -d '\r')"
  resolved_model="$(python3 -c "
import json
try: print((json.load(open('$body')) or {}).get('model') or '')
except Exception: print('')
" 2>/dev/null)"
  req_cost="$(python3 -c "
import json
try:
    u=(json.load(open('$body')) or {}).get('usage') or {}
    c=u.get('cost')
    print('' if c is None else repr(float(c)))
except Exception: print('')
" 2>/dev/null)"

  # ── STAGE 1: ROUTE ────────────────────────────────────────────────────────
  _stage "STAGE 1 — ROUTE (tier=$tier, head=$head_model)"
  if [ "$code" != "200" ]; then
    _red "route: gateway returned HTTP $code (not 200) — request did not complete"
    _info "body: $(head -c 200 "$body" 2>/dev/null)"
    return
  fi
  _pass "route: gateway returned HTTP 200"
  if [ -z "$provider" ]; then
    _red "route: NO X-Charon-Provider header — cannot prove which leg served (reachability only)"
  else
    _info "served-by: $provider   failover-reasons: ${reasons:-<none>}   resolved-model: ${resolved_model:-<none>}"
    # served provider must be in the head model's pool (from the BEFORE snapshot)
    local inpool
    inpool="$(python3 -c "
import json
try:
    d=json.loads(r'''$before_json'''); ch=(d.get('pools') or {}).get('$head_model') or []
    print('yes' if '$provider' in ch else 'no:'+','.join(ch))
except Exception: print('err')
" 2>/dev/null)"
    if [ "$inpool" = "yes" ]; then
      _pass "route: X-Charon-Provider '$provider' is a member of '$head_model' pool"
    else
      _red "route: served provider '$provider' is NOT in the '$head_model' pool ($inpool) — MIS-ROUTE"
    fi
  fi
  # resolved model real + never Anthropic (sg-never-anthropic)
  if [ -z "$resolved_model" ]; then
    _red "route: response body carried no resolved 'model' — cannot assert what was served"
  elif printf '%s' "$resolved_model" | grep -qiE 'anthropic|claude'; then
    _red "route: resolved model '$resolved_model' is ANTHROPIC — SG must never route to Claude"
  else
    _pass "route: resolved upstream model '$resolved_model' is real and non-Anthropic"
  fi
  # FREE-FIRST: the served leg must be a funded-free class (fc 1 or 2). A paid
  # (fc 3) leg serving while a free one exists is the free-first break.
  if [ -n "$provider" ]; then
    local fc
    fc="$(python3 -c "
import json
try:
    d=json.loads(r'''$after_json'''); print((d.get('balance') or {}).get('$provider',{}).get('funding_class'))
except Exception: print('None')
" 2>/dev/null)"
    if [ "$fc" = "1" ] || [ "$fc" = "2" ]; then
      _pass "route/free-first: served leg '$provider' is funding_class $fc (funded-free) — a free leg served before any paid leg"
    else
      _red "route/free-first: served leg '$provider' is funding_class $fc (NOT free 1/2) — free-first ordering violated (a paid leg served)"
    fi
  fi

  # ── STAGE 2: METER ────────────────────────────────────────────────────────
  # Observable, concurrency-robust: the SERVED provider's observer counter must
  # advance by >= 1 (other live traffic only adds). A flat counter = inert meter
  # (#167). The per-request priced amount is the response usage.cost.
  _stage "STAGE 2 — METER (served-by=$provider)"
  if [ -z "$provider" ]; then
    _red "meter: no served provider known — cannot assert a meter delta"
  else
    local dserved dcost
    read -r dserved dcost <<<"$(python3 -c "
import json
def g(js):
    try: return json.loads(js)
    except Exception: return {}
b=g(r'''$before_json'''); a=g(r'''$after_json''')
def prov(d):
    return (d.get('providers') or {}).get('$provider') or {}
sb=prov(b).get('served',0) or 0; sa=prov(a).get('served',0) or 0
cb=prov(b).get('cost',0) or 0;   ca=prov(a).get('cost',0) or 0
print(int(sa)-int(sb), float(ca)-float(cb))
" 2>/dev/null)"
    dserved="${dserved:-0}"; dcost="${dcost:-0}"
    _info "served-delta=$dserved  cost-delta=$dcost  per-request usage.cost=${req_cost:-<none>}"
    if [ "$dserved" -ge 1 ] 2>/dev/null; then
      _pass "meter: observer 'served' for '$provider' advanced by $dserved (>=1) — the request was METERED, not merely served"
    else
      _red "meter: observer 'served' for '$provider' did NOT advance (delta=$dserved) — INERT METER (#167 class)"
    fi
    # per-request priced amount must be present & numeric (>= 0). A funded-free
    # leg legitimately prices at 0, so 0 is honest here; absence is the break.
    if [ -z "$req_cost" ]; then
      _red "meter: response carried NO per-request usage.cost — the priced amount is unobservable"
    else
      local costok
      costok="$(python3 -c "print('yes' if float('$req_cost') >= 0 else 'no')" 2>/dev/null)"
      if [ "$costok" = "yes" ]; then
        _pass "meter: per-request priced amount observable (usage.cost=$req_cost); observer cost-delta=$dcost (>=0)"
      else
        _red "meter: per-request usage.cost is negative ($req_cost) — nonsensical price"
      fi
    fi
  fi

  # ── STAGE 3: PARK / FUNDING-CLASS EXCLUSION (#188 dead-no-op class) ────────
  # A parked/drained provider must be EXCLUDED from routing — not served, and
  # not even attempted. Assert none appears in the served path
  # {served leg} U {attempted failover legs}. If one does, the exclusion is a
  # dead no-op (#188) and this goes RED.
  _stage "STAGE 3 — PARK / FUNDING-CLASS EXCLUSION"
  local attempted
  attempted="$(printf '%s' "$reasons" | grep -oE '[A-Za-z0-9_-]+=' | sed 's/=$//' | paste -sd, -)"
  local violation
  violation="$(python3 -c "
import json
try: d=json.loads(r'''$after_json''')
except Exception: d={}
bal=d.get('balance') or {}
excluded=set(p for p,v in bal.items() if v.get('parked') or v.get('drained'))
path=set()
sv='$provider'.strip()
if sv: path.add(sv)
for p in '$attempted'.split(','):
    p=p.strip()
    if p: path.add(p)
bad=sorted(excluded & path)
served_excluded = sv in excluded
print(('SERVED:'+sv if served_excluded else '') + '|' + ','.join(bad) + '|' + ','.join(sorted(excluded)))
" 2>/dev/null)"
  local served_bad path_bad all_excluded
  served_bad="$(printf '%s' "$violation" | cut -d'|' -f1)"
  path_bad="$(printf '%s' "$violation" | cut -d'|' -f2)"
  all_excluded="$(printf '%s' "$violation" | cut -d'|' -f3)"
  _info "parked/drained providers on gateway: [${all_excluded:-<none>}]   served-path: [${provider}${attempted:+,$attempted}]"
  if [ -n "$served_bad" ]; then
    _red "park: the SERVED leg is parked/drained ($served_bad) — exclusion is a DEAD NO-OP (#188 class)"
  elif [ -n "$path_bad" ]; then
    _red "park: a parked/drained provider was ATTEMPTED in the route ($path_bad) — exclusion did not fire (#188 class)"
  elif [ -z "$all_excluded" ]; then
    _pass "park: no provider is currently parked/drained — exclusion not exercised on this run (positive firing proven in the dogfood)"
  else
    _pass "park: parked/drained providers [$all_excluded] were EXCLUDED from the served path"
  fi
}

# ── run one tier chain end-to-end (the widen-to-matrix unit) ────────────────
run_tier(){
  local tier="$1" tok status_json chain head_model
  tok="$(_bearer_token)"
  if [ -z "$tok" ]; then
    _red "no gateway Bearer token (FC_TOKEN unset and $FC_OPENCODE_CFG unreadable/empty)"
    return
  fi
  chain="$(_tier_chain "$tier")"
  head_model="$(printf '%s' "$chain" | cut -d, -f1 | tr -d '[:space:]')"
  status_json="$(_status_json "$tok")"
  if [ -z "$status_json" ]; then
    _red "gateway /charon/status unreachable/empty at $FC_GATEWAY_URL — cannot canary"
    return
  fi

  echo "FLOW-CANARY  gateway=$FC_GATEWAY_URL  tier=$tier  chain=[$chain]"
  _stage_config  "$tok" "$status_json" "$tier" "$head_model"
  _stage_flow    "$tok" "$status_json" "$tier" "$head_model"
}

main(){
  echo "════════════════════════════════════════════════════════════"
  echo " FLOW-CANARY — proactive e2e money-path health check"
  echo " $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "════════════════════════════════════════════════════════════"
  # THIN SLICE: one tier. WIDEN-TO-MATRIX: replace with
  #   for t in $CANONICAL_TIERS; do run_tier "$t"; done
  run_tier "$FC_TIER"
  echo
  if [ "$RED" -eq 0 ]; then
    echo "════ FLOW-CANARY: GREEN — all observable effects asserted ════"
    exit 0
  fi
  echo "████ FLOW-CANARY: RED — a silent break was caught (see RED lines above) ████"
  exit 1
}

# Only run main when executed directly (sourcing for tests exposes the fns).
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  main "$@"
fi
