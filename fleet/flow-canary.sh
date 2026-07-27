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
#                served leg is the highest-priority NON-parked/keyed leg per the
#                LIVE SSOT funding_class_order (free-first respected — NO cry-wolf
#                on a sanctioned class-3 drain-then-park leg).
#   2. METER   — the served provider's observer counter ADVANCES (served +>=1)
#                and the meter records a priced amount for the request. An
#                inert meter (#167) leaves the counter flat -> RED. The
#                cost-delta backstop asserts >0 for a DRAINING (class-3 / drained)
#                leg — a near-un-failable >=0 was decorative and so is dropped.
#   3. PARK    — no parked/drained provider appears anywhere in the served path
#                (served leg OR any attempted failover leg). A dead-no-op
#                exclusion (#188) that lets a parked provider be attempted -> RED.
#                A positive-GREEN when providers ARE parked confirms at least one
#                excluded provider was actually a CANDIDATE in the head-model pool
#                (else the "EXCLUDED" claim is vacuous).
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
#   • funding-class priority (free-first): the SSOT
#     `charon.routing_policy._FUNDING_CLASS_ORDER` (ordering 1<3<2<4). Never
#     re-derive the order — that is what CRY-WOLFED the canary on a sanctioned
#     class-3 drain leg. Read live via _funding_order_json.
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
# Funding-class priority SSOT. The free-first invariant is defined by
# `charon.routing_policy._FUNDING_CLASS_ORDER` (lower = preferred; see
# routing_policy/__init__.py). The canary MUST NOT reimplement the order —
# like `charon tier ranks` for tier names, it reads the SSOT live. Two overridable
# hooks so the hermetic dogfood can pin a deterministic order without a `charon`
# install in the box:
#   FC_FUNDING_ORDER_JSON  a JSON {fc_str: rank} blob to use INSTEAD of the import
#                          (the test sets this to the known-good order).
#   FC_FUNDING_ORDER_CMD   a shell command that STDOUTs the JSON blob (default:
#                          import charon.routing_policy and dump it).
# When both are unset, the SSOT is read via the live `charon` module. If the
# import fails AND no override is set, the free-first stage errors out (RED) —
# never silently falls back to a reimplementation.

# Scratch dir for JSON snapshots + response capture. JSON is ALWAYS passed to
# python by FILE PATH (never embedded in a -c string — the status payload is
# full of double-quotes that would break the shell quoting).
FCTMP="$(mktemp -d 2>/dev/null || echo "/tmp/flow-canary.$$")"
trap 'rm -rf "$FCTMP" 2>/dev/null || true' EXIT

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

# ── funding-class priority SSOT (charon.routing_policy._FUNDING_CLASS_ORDER) ──
# Returns a JSON {fc_str: rank_int} object on stdout, or 'ERR' + a reason.
# MUST NOT reimplement the order; the live `charon` module is the SSOT. The
# hermetic dogfood pins FC_FUNDING_ORDER_JSON so it never depends on `charon`
# being importable in the test box. Defaulting (the hardcode that caused the
# cry-wolf) is intentionally NOT done — a missing SSOT is a RED, not a guess.
_funding_order_json(){
  if [ -n "${FC_FUNDING_ORDER_JSON:-}" ]; then
    printf '%s' "$FC_FUNDING_ORDER_JSON"
    return 0
  fi
  local cmd="${FC_FUNDING_ORDER_CMD:-}"
  if [ -z "$cmd" ]; then
    cmd='python3 -c "from charon.routing_policy import _FUNDING_CLASS_ORDER as o; import json; print(json.dumps({str(k):v for k,v in o.items()}))"'
  fi
  local out
  out="$(eval "$cmd" 2>/dev/null)" || true
  if [ -n "$out" ]; then
    printf '%s' "$out"
  else
    printf 'ERR:funding_class_order SSOT unreadable (charon import failed and no FC_FUNDING_ORDER_JSON override)'
    return 1
  fi
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

# ── GET /charon/status -> writes JSON to $1 (returns non-zero if empty) ─────
_status_json(){
  local tok="$1" out="$2"
  curl -s --max-time "$FC_STATUS_TIMEOUT_S" \
    -H "Authorization: Bearer $tok" -H "Accept: application/json" \
    "$FC_GATEWAY_URL/charon/status" -o "$out" 2>/dev/null || true
  [ -s "$out" ]
}

# ── STAGE 4: CONFIG SANITY (cheap, no request — run first) ──────────────────
_stage_config(){
  local status_file="$1" tier="$2" head_model="$3"
  _stage "STAGE 4 — CONFIG SANITY (tier=$tier)"

  local ranks_file="$FCTMP/ranks.txt"
  $FC_TIER_RANKS_CMD > "$ranks_file" 2>/dev/null || true
  if [ ! -s "$ranks_file" ]; then
    _red "config: \`$FC_TIER_RANKS_CMD\` produced no output — cannot verify tier canonicality"
  else
    if python3 - "$tier" "$ranks_file" <<'PYEOF'
import sys
tier = sys.argv[1].lower()
ranks = {}
for line in open(sys.argv[2]):
    parts = line.split()
    if len(parts) < 2: continue
    try: ranks[parts[0].lower()] = int(parts[-1])
    except ValueError: pass
canon = ["economy", "strong", "frontier"]
bad = []
missing = [t for t in canon if t not in ranks]
if missing:
    bad.append("MISSING " + " ".join(missing))
elif not (ranks["economy"] < ranks["strong"] < ranks["frontier"]):
    bad.append(f"ORDER economy={ranks['economy']} strong={ranks['strong']} frontier={ranks['frontier']}")
if "standard" in ranks:
    bad.append("STRAY-standard")
if tier not in ranks:
    bad.append("TIER-MISSING " + tier)
if bad:
    print("; ".join(bad)); sys.exit(1)
sys.exit(0)
PYEOF
    then
      _pass "config: tier set canonical (economy<strong<frontier), no stray 'standard', '$tier' present"
    else
      _red "config: tier ranks NON-canonical — drift"
    fi
  fi

  if [ -z "$head_model" ]; then
    _red "config: tier '$tier' has no failover chain in $FC_TIER_TSV"
    return
  fi
  local chainline
  chainline="$(python3 - "$head_model" "$status_file" <<'PYEOF'
import json, sys
head = sys.argv[1]
try: d = json.load(open(sys.argv[2]))
except Exception: print("NOSTATUS"); sys.exit(1)
pools = d.get("pools") or {}
bal = d.get("balance") or {}
chain = pools.get(head)
if not chain:
    print("NOTSERVED"); sys.exit(1)
unkeyed = [p for p in chain if p not in bal]
if unkeyed:
    print("UNKEYED " + ",".join(unkeyed)); sys.exit(1)
print(",".join(chain)); sys.exit(0)
PYEOF
)"
  if [ $? -eq 0 ]; then
    _pass "config: head model '$head_model' served; providers keyed [$chainline]"
  else
    _red "config: head model '$head_model' not served OR has unkeyed providers ($chainline) — config drift"
  fi
}

# ── STAGES 1-3: send the REAL request, then assert route/meter/park ─────────
_stage_flow(){
  local tok="$1" before_file="$2" tier="$3" head_model="$4"
  local hdr="$FCTMP/hdr.txt" body="$FCTMP/body.json" after_file="$FCTMP/after.json"
  local reqbody="$FCTMP/req.json"

  # A per-run NONCE defeats the gateway response cache: a cache hit serves
  # provider="cache" without touching a pool leg or advancing the meter, so it
  # would exercise NONE of route/meter/free-first. The canary must force a real
  # upstream call every run (unless the test pins FC_NONCE for determinism).
  local nonce="${FC_NONCE:-$(date -u +%s)-$RANDOM}"
  python3 -c "
import json, sys
json.dump({'model': sys.argv[1],
           'messages': [{'role':'user','content': sys.argv[2] + ' (canary ' + sys.argv[5] + ')'}],
           'max_tokens': int(sys.argv[3])}, open(sys.argv[4],'w'))
" "$head_model" "$FC_PROMPT" "$FC_MAX_TOKENS" "$reqbody" "$nonce"

  local code
  code="$(curl -s --max-time "$FC_REQ_TIMEOUT_S" -o "$body" -D "$hdr" -w '%{http_code}' \
    -H "Authorization: Bearer $tok" -H "Content-Type: application/json" \
    -X POST "$FC_GATEWAY_URL/v1/chat/completions" --data-binary "@$reqbody" 2>/dev/null)"

  _status_json "$tok" "$after_file" || : > "$after_file"

  local provider reasons resolved_model
  provider="$(grep -i '^X-Charon-Provider:' "$hdr" | head -1 | sed 's/^[^:]*:[[:space:]]*//; s/[[:space:]]*$//' | tr -d '\r')"
  reasons="$(grep -i '^X-Charon-Failover-Reasons:' "$hdr" | head -1 | sed 's/^[^:]*:[[:space:]]*//' | tr -d '\r')"
  resolved_model="$(python3 -c "
import json,sys
try: print((json.load(open(sys.argv[1])) or {}).get('model') or '')
except Exception: print('')
" "$body" 2>/dev/null)"

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
    local inpool
    inpool="$(python3 -c "
import json,sys
try:
    d=json.load(open(sys.argv[1])); ch=(d.get('pools') or {}).get(sys.argv[2]) or []
    print('yes' if sys.argv[3] in ch else 'no:'+','.join(ch))
except Exception: print('err')
" "$before_file" "$head_model" "$provider" 2>/dev/null)"
    if [ "$inpool" = "yes" ]; then
      _pass "route: X-Charon-Provider '$provider' is a member of '$head_model' pool"
    else
      _red "route: served provider '$provider' is NOT in the '$head_model' pool ($inpool) — MIS-ROUTE"
    fi
  fi
  if [ -z "$resolved_model" ]; then
    _red "route: response body carried no resolved 'model' — cannot assert what was served"
  elif printf '%s' "$resolved_model" | grep -qiE 'anthropic|claude'; then
    _red "route: resolved model '$resolved_model' is ANTHROPIC — SG must never route to Claude"
  else
    _pass "route: resolved upstream model '$resolved_model' is real and non-Anthropic"
  fi
  # FREE-FIRST: the served leg must be the HIGHEST-PRIORITY NON-parked/keyed
  # leg in the pool per the live SSOT `charon.routing_policy._FUNDING_CLASS_ORDER`
  # (order 1<3<2<4 → free-recurring first, then class-3 drain-then-park, then
  # flat-sub, then PAYG). The prior check hardcoded `fc∈{1,2}=free` — that
  # reimplementation CRY-WOLFED on a legitimate class-3 (sanctioned
  # drain-then-park) leg serving. A proactive guard that false-REDs on normal
  # operation is worse than none, so we read the SSOT, not a guess, and we
  # compare against the BEST non-parked candidate the forwarder would have
  # picked, thresholding on parking (not funding_class) — exactly what the
  # forwarder's order-then-exclude routing does.
  if [ -n "$provider" ]; then
    local order_json
    order_json="$(_funding_order_json)" || {
      _red "route/free-first: $order_json"
      return
    }
    local ff
    ff="$(python3 - "$after_file" "$head_model" "$provider" "$order_json" <<'PYEOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as exc:
    print("ERR:status snapshot unreadable: %s" % exc); sys.exit(0)
head, served, order_raw = sys.argv[2], sys.argv[3], sys.argv[4]
pool = (d.get("pools") or {}).get(head) or []
bal = d.get("balance") or {}
try:
    order = {int(k) if k != "None" else None: int(v) for k, v in json.loads(order_raw).items()}
except Exception as exc:
    print("ERR:funding-class order unreadable: %s" % exc); sys.exit(0)

def fc_of(p):
    v = bal.get(p)
    if not isinstance(v, dict):
        return None
    fc = v.get("funding_class")
    try:
        return int(fc) if fc is not None else None
    except Exception:
        return None

def is_excluded(p):
    v = bal.get(p)
    if not isinstance(v, dict):
        return False
    return bool(v.get("parked")) or bool(v.get("drained"))

# Candidates the forwarder would consider from this pool: keyed (in balance)
# and NOT parked/drained. Unknown funding_class → None → order 5 (sort last),
# matching `funding_class_order`. The PROOF that the served leg was the
# free-first pick is: served == the BEST candidate by SSOT order (ties broken
# arbitrarily — the snapshot cannot expose drain-remaining, so we treat a tie
# as acceptable; parking/exclusion is the load-bearing signal).
candidates = [(p, order.get(fc_of(p), 5)) for p in pool
              if p in bal and not is_excluded(p)]
served_fc = fc_of(served)
served_order = order.get(served_fc, 5)
if not candidates:
    print("ERR:pool '%s' has no keyed/non-excluded candidates to free-first against (pool=%s)" % (head, ",".join(pool)))
    sys.exit(0)
best_order = min(o for _, o in candidates)
# If the served leg isn't a candidate at all (e.g. it was served anyway
# because every leg was parked — the never-strand fallback) we don't have a
# free-first violation: the forwarder's never-strand fallback explicitly
# serves the original chain when no live leg exists.
best_candidates = [p for p, o in candidates if o == best_order]
if is_excluded(served):
    # served an EXCLUDED leg — STAGE 3 catches that as a PARK/dead-no-op; here
    # we don't double-count it as a free-first break (different failure mode).
    print("OK:skip served an excluded leg; park stage reports it")
elif served in best_candidates:
    print("OK:%s (fc=%s, order=%d) is the highest-priority non-parked candidate in the pool (best=%s, orders=%s)" % (
        served, served_fc, served_order, ",".join(best_candidates),
        ",".join(str(o) for _, o in sorted(candidates, key=lambda c: c[1]))))
elif served_order < best_order:
    print("OK:%s (fc=%s, order=%d) outranks the other candidates (best=%d)" % (
        served, served_fc, served_order, best_order))
else:
    ranked = ",".join("%s(fc=%s,o=%d)" % (p, fc_of(p), o) for p, o in sorted(candidates, key=lambda c: c[1]))
    print("BAD:%s (fc=%s, order=%d) served while a higher-priority non-parked candidate was skipped: %s" % (
        served, served_fc, served_order, ranked))
PYEOF
)"
    case "$ff" in
      OK:*)    _pass "route/free-first: ${ff#OK:} — the SSOT free-first ordering was respected (no cry-wolf on a sanctioned class-3 drain leg)" ;;
      ERR:*)  _red "route/free-first: ${ff#ERR:}" ;;
      BAD:*)  _red "route/free-first: ${ff#BAD:} — free-first ordering violated (a lower-priority leg served before a higher-priority non-parked one)" ;;
      *)      _red "route/free-first: unexpected analysis output: $ff" ;;
    esac
  fi
  _info "funding-class order SSOT: ${order_json}"

  # ── STAGE 2: METER ────────────────────────────────────────────────────────
  # Observable, concurrency-robust: the SERVED provider's observer counter must
  # advance by >= 1 (other live traffic only adds). A flat counter = inert meter
  # (#167). The cost-delta is a DRAINING-leg backstop ONLY: a funded-free leg
  # legitimately prices at ~0, so a blanket `cost >= 0` was near-un-failable
  # (decorative). A class-3 / drained leg is a PAYING leg, so its cost-delta MUST
  # be > 0 — that proves the leg actually drew against its balance (a no-op drain
  # would leave cost flat). The served-count advance remains the load-bearing
  # anti-inert signal for every other class.
  _stage "STAGE 2 — METER (served-by=$provider)"
  if [ -z "$provider" ]; then
    _red "meter: no served provider known — cannot assert a meter delta"
  else
    local metric
    metric="$(python3 -c "
import json,sys
def g(p):
    try: return json.load(open(p))
    except Exception: return {}
b=g(sys.argv[1]); a=g(sys.argv[2]); pr=sys.argv[3]
def prov(d): return (d.get('providers') or {}).get(pr) or {}
sb=int(prov(b).get('served',0) or 0); sa=int(prov(a).get('served',0) or 0)
cb=float(prov(b).get('cost',0) or 0); ca=float(prov(a).get('cost',0) or 0)
print(f'{sa-sb} {ca-cb}')
" "$before_file" "$after_file" "$provider" 2>/dev/null)"
    local dserved dcost
    dserved="$(printf '%s' "$metric" | awk '{print $1}')"; dserved="${dserved:-0}"
    dcost="$(printf '%s' "$metric" | awk '{print $2}')"; dcost="${dcost:-0}"
    _info "observer served-delta=$dserved  cost-delta=$dcost"
    if [ "$dserved" -ge 1 ] 2>/dev/null; then
      _pass "meter: observer 'served' for '$provider' advanced by $dserved (>=1) — the request was METERED, not merely served"
    else
      _red "meter: observer 'served' for '$provider' did NOT advance (delta=$dserved) — INERT METER (#167 class)"
    fi
    # Draining leg backstop: a class-3 (drain-then-park) or any drained leg is
    # a PAYING leg — its cost-delta MUST be > 0, or the meter recorded a free
    # ride on a balance it should have drawn against. A funded-free leg may
    # legitimately price at ~0, so we DO NOT assert > 0 there (that was the
    # decorative >=0 trap). The funding-class is read from the snapshot.
    local sv_fc sv_drained
    sv_fc="$(python3 -c "
import json,sys
try: print((json.load(open(sys.argv[1])).get('balance') or {}).get(sys.argv[2],{}).get('funding_class'))
except Exception: print('None')
" "$after_file" "$provider" 2>/dev/null)"
    sv_drained="$(python3 -c "
import json,sys
try: print('yes' if (json.load(open(sys.argv[1])).get('balance') or {}).get(sys.argv[2],{}).get('drained') else 'no')
except Exception: print('no')
" "$after_file" "$provider" 2>/dev/null)"
    if [ "$sv_fc" = "3" ] || [ "$sv_drained" = "yes" ]; then
      local drain_ok
      drain_ok="$(python3 -c "print('yes' if float('$dcost') > 0 else 'no')" 2>/dev/null)"
      if [ "$drain_ok" = "yes" ]; then
        _pass "meter: draining leg '$provider' (fc=$sv_fc, drained=$sv_drained) recorded a positive cost-delta ($dcost, >0) — balance was drawn, not a free ride"
      else
        _red "meter: draining leg '$provider' (fc=$sv_fc, drained=$sv_drained) recorded a zero/negative cost-delta ($dcost) — a PAYING leg took a free ride (decorative >=0 would have passed this)"
      fi
    else
      _info "meter: served leg '$provider' is fc=$sv_fc (not a draining/payg leg) — cost-delta backstop not applicable (served-count advance is the load-bearing signal)"
    fi
  fi

  # ── STAGE 3: PARK / FUNDING-CLASS EXCLUSION (#188 dead-no-op class) ────────
  _stage "STAGE 3 — PARK / FUNDING-CLASS EXCLUSION"
  local attempted
  attempted="$(printf '%s' "$reasons" | grep -oE '[A-Za-z0-9_-]+=' | sed 's/=$//' | paste -sd, -)"
  local violation
  violation="$(python3 -c "
import json,sys
try: d=json.load(open(sys.argv[1]))
except Exception: d={}
bal=d.get('balance') or {}
excluded=set(p for p,v in bal.items() if v.get('parked') or v.get('drained'))
sv=sys.argv[2].strip()
path=set([sv]) if sv else set()
for p in sys.argv[3].split(','):
    p=p.strip()
    if p: path.add(p)
bad=sorted(excluded & path)
served_excluded = sv in excluded
print(('SERVED:'+sv if served_excluded else '') + '|' + ','.join(bad) + '|' + ','.join(sorted(excluded)))
" "$after_file" "$provider" "$attempted" 2>/dev/null)"
  local served_bad path_bad all_excluded
  served_bad="$(printf '%s' "$violation" | cut -d'|' -f1)"
  path_bad="$(printf '%s' "$violation" | cut -d'|' -f2)"
  all_excluded="$(printf '%s' "$violation" | cut -d'|' -f3)"
  _info "parked/drained on gateway: [${all_excluded:-<none>}]   served-path: [${provider}${attempted:+,$attempted}]"
  if [ -n "$served_bad" ]; then
    _red "park: the SERVED leg is parked/drained ($served_bad) — exclusion is a DEAD NO-OP (#188 class)"
  elif [ -n "$path_bad" ]; then
    _red "park: a parked/drained provider was ATTEMPTED in the route ($path_bad) — exclusion did not fire (#188 class)"
  elif [ -z "$all_excluded" ]; then
    _pass "park: no provider is currently parked/drained — exclusion not exercised on this run (positive firing proven in the dogfood)"
  else
    # FIX-4 (minor): the positive-GREEN "X was EXCLUDED" is only meaningful if
    # at least one of the parked/drained providers was actually a CANDIDATE in
    # the head-model pool — else the EXCLUDED claim is vacuous (the provider was
    # never going to be considered). A provider that isn't even in the pool being
    # "excluded" proves nothing about the exclusion path. The pool is the
    # head-model's pool from the snapshot; a candidate is a keyed (in balance)
    # member of it. We don't RED on a vacuous-park positive (it's a weak signal,
    # not a silent break), but we downgrade it from a passing assertion to an
    # info note so the GREEN verdict can't be misread as "exclusion proven".
    local pool_csv
    pool_csv="$(python3 -c "
import json,sys
try: print(','.join((json.load(open(sys.argv[1])).get('pools') or {}).get(sys.argv[2],[])))
except Exception: print('')
" "$after_file" "$head_model" 2>/dev/null)"
    local excluded_in_pool
    excluded_in_pool="$(python3 - "$pool_csv" "$all_excluded" <<'PYEOF'
import sys
pool = set(p for p in sys.argv[1].split(',') if p)
excluded = set(p for p in sys.argv[2].split(',') if p)
print(','.join(sorted(pool & excluded)) or '')
PYEOF
)"
    if [ -n "$excluded_in_pool" ]; then
      _pass "park: parked/drained providers [$all_excluded] were EXCLUDED from the served path; [$excluded_in_pool] were head-model pool candidates — exclusion is non-vacuous"
    else
      _red "park: parked/drained providers [$all_excluded] were none of them candidates in the '$head_model' pool — the EXCLUDED positive-GREEN is VACUOUS (proves nothing; exclusion must fire against a real candidate to be load-bearing)"
    fi
  fi
}

# ── run one tier chain end-to-end (the widen-to-matrix unit) ────────────────
run_tier(){
  local tier="$1" tok chain head_model
  local before_file="$FCTMP/before.json"
  tok="$(_bearer_token)"
  if [ -z "$tok" ]; then
    _red "no gateway Bearer token (FC_TOKEN unset and $FC_OPENCODE_CFG unreadable/empty)"
    return
  fi
  chain="$(_tier_chain "$tier")"
  head_model="$(printf '%s' "$chain" | cut -d, -f1 | tr -d '[:space:]')"
  if ! _status_json "$tok" "$before_file"; then
    _red "gateway /charon/status unreachable/empty at $FC_GATEWAY_URL — cannot canary"
    return
  fi

  echo "FLOW-CANARY  gateway=$FC_GATEWAY_URL  tier=$tier  chain=[$chain]"
  _stage_config "$before_file" "$tier" "$head_model"
  _stage_flow   "$tok" "$before_file" "$tier" "$head_model"
}

main(){
  echo "════════════════════════════════════════════════════════════"
  echo " FLOW-CANARY — proactive e2e money-path health check"
  echo " $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "════════════════════════════════════════════════════════════"
  # THIN SLICE: one tier. WIDEN-TO-MATRIX: replace with
  #   for t in economy strong frontier; do run_tier "$t"; done
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
