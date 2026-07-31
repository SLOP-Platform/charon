#!/usr/bin/env bash
# failover-canary.sh — FAILOVER-CANARY: proves the routing-brain's failover
# CASCADE is real, not merely configured (fleet/board/FAILOVER-CANARY.md).
#
# WHY THIS EXISTS: FLOW-CANARY proves the HAPPY-PATH observable effects (route/
# meter/park/config) on whatever leg happens to serve today. It has never once
# seen a live provider actually go down, so it has never proven the CASCADE
# itself works: that a failed head-tier leg hands off to the next leg, that
# `X-Charon-Failover-Reasons` correctly names the failed leg, that a parked/
# drained leg is never attempted mid-cascade (#188 class), and that total
# exhaustion is a LOUD structured error — never a hang, never a raw passthrough.
# This canary SEEDS that failure (real Toxiproxy fault, or a caller-supplied
# hook) and asserts the cascade's observable effects, the same
# assert-EXERCISED-not-REACHABLE discipline as flow-canary.sh.
#
# ── GROUND TRUTH (confirm-don't-trust-docs; read at build time from
#    src/charon/proxy.py + src/charon/forwarder.py on the charon product repo,
#    NOT re-derived here) ──────────────────────────────────────────────────
#   proxy.py:41  _EXHAUSTION_STATUSES = {429, 402, 503}      <- fail over
#   proxy.py:44  _DROP_STATUSES       = {404}                <- fail over (drop)
#   proxy.py:84  _UNSUPPORTED_STATUSES= {400, 401, 422}      <- fail over (body-gated)
#   A bare 500 is NOT in any of these sets, so obs.failover is False for it —
#   forwarder.py's R6 comment ("a single-upstream exhaustion, OR a 400/401/403
#   client/auth error we must NOT fail over — relay the real upstream response
#   as-is") applies to a bare 500 too: it is RELAYED, not cascaded. A connection-
#   level fault (timeout / reset_peer — Toxiproxy's two toxics, forwarder.py's
#   `except Exception:` branch around line 586) ALWAYS fails over regardless of
#   status, recorded as reason "unreachable" (forwarder.py:593).
#   Terminal-exhaustion envelopes (forwarder.py:596-600 vs :732-745): a
#   connection-only all-down synthesizes 502 {"error":{"message":"all upstreams
#   unreachable"}}; a status-based all-down (e.g. every leg 429) synthesizes the
#   richer ADR-0016 503 {"error":{"message":"all providers exhausted", "type":
#   "all_providers_exhausted", "providers_tried":[...], "failover_reasons":[...]}}.
#   Both are STRUCTURED — this canary's ALL-DOWN stage accepts either.
#   THIS MEANS: "head-500" is deliberately encoded here as a NO-CASCADE class
#   (FO_EXPECT_CASCADE=0) — asserting the current, correct, documented R6
#   behavior (clean passthrough, no cascade attempt) — NOT a cascade class like
#   429/timeout/503. If a future change adds 500 to the exhaustion set, this
#   stage's expectation must move with it (same maintenance contract as
#   flow-canary's tier-canonicality assertions).
#
# TOOL-EVAL (Phase 1, ticket-cited ADOPT): Toxiproxy is the fault injector for
# LIVE runs. It is a single static Go binary (no docker required) — validated
# during this ticket's build: `toxiproxy-server` fronting a stdlib fake
# upstream, a `reset_peer` toxic added via its HTTP control API measurably cut
# the connection (curl exit 56) and a DELETE of the toxic restored 200 — see
# fleet/board/FAILOVER-CANARY.md for the ticket's ADOPT citation. This script
# does NOT embed Toxiproxy calls directly (mirrors flow-canary.sh's separation:
# the canary asserts observable effects of ONE real request; it does not know
# or care HOW the fault got seeded). Instead FO_SEED_HEAD_CMD / FO_RESTORE_
# HEAD_CMD / FO_SEED_ALLDOWN_CMD / FO_RESTORE_ALLDOWN_CMD are `bash -c`-eval'd
# hooks the CALLER wires — in production, Toxiproxy's HTTP API via curl, e.g.:
#   FO_SEED_HEAD_CMD='curl -s -X POST $TOXI/proxies/head/toxics \
#     -d "{\"name\":\"fo-cut\",\"type\":\"reset_peer\",\"attributes\":{\"timeout\":0}}"'
#   FO_RESTORE_HEAD_CMD='curl -s -X DELETE $TOXI/proxies/head/toxics/fo-cut'
# — in the hermetic dogfood (fleet/tests/failover-canary.test.sh) a scenario-
# JSON rewrite read fresh by a stdlib fake gateway (flow-canary.test.sh's
# proven pattern). Unset hooks == skip that stage (a bare health-check run,
# same posture as flow-canary's thin slice) rather than silently no-op green.
#
# GREEN IS NOT PROOF. fleet/tests/failover-canary.test.sh seeds each of the
# four fault classes (head-429, head-timeout, head-500, all-legs-down) against
# a hermetic fake and proves this script goes RED on a broken cascade, then
# GREEN on revert — that test is what keeps this one honest.
#
# EXIT: 0 = all run stages GREEN. non-zero = at least one stage RED (loud).
#
# ── ENV ──────────────────────────────────────────────────────────────────
#   FO_GATEWAY_URL        default http://10.0.1.60:8080   (4-LOM live gateway)
#   FO_TOKEN              default: derived from FO_OPENCODE_CFG
#   FO_OPENCODE_CFG       default ~/.config/opencode/opencode.json
#   FO_TIER               default strong
#   FO_TIER_TSV           default <fleet>/tier-models.tsv
#   FO_PROMPT             default "reply with the single word: PONG"
#   FO_MAX_TOKENS         default 16
#   FO_REQ_TIMEOUT_S      default 20   (bounds the "not a hang" assertion)
#   FO_STATUS_TIMEOUT_S   default 8
#   FO_SEED_HEAD_CMD / FO_RESTORE_HEAD_CMD       — head-tier fault hook (unset = skip cascade stage)
#   FO_EXPECT_CASCADE     default 1 (0 = expect a clean same-leg relay, no cascade — the head-500 class)
#   FO_EXPECT_STATUS      default 500 (used only when FO_EXPECT_CASCADE=0 — the relayed status to assert)
#   FO_SEED_ALLDOWN_CMD / FO_RESTORE_ALLDOWN_CMD — all-legs-down fault hook (unset = skip all-down stage)
#   FO_FAULT_LABEL        default "unspecified" — free-text label for output only (e.g. "head-429")
#   FO_PROXY_MAP          optional "provider=proxyname,provider2=proxyname2" — resolves the
#                         BASELINE-discovered head provider to its Toxiproxy proxy name,
#                         exported as FO_HEAD_PROXY (alongside FO_DISCOVERED_HEAD) before
#                         FO_SEED_HEAD_CMD/FO_RESTORE_HEAD_CMD run, so a real seed command can
#                         address the right proxy instead of hardcoding a guess at what serves.
set -uo pipefail

FLEET="${CHARON_FLEET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

FO_GATEWAY_URL="${FO_GATEWAY_URL:-http://10.0.1.60:8080}"
FO_OPENCODE_CFG="${FO_OPENCODE_CFG:-$HOME/.config/opencode/opencode.json}"
FO_TIER="${FO_TIER:-strong}"
FO_TIER_TSV="${FO_TIER_TSV:-$FLEET/tier-models.tsv}"
FO_PROMPT="${FO_PROMPT:-reply with the single word: PONG}"
FO_MAX_TOKENS="${FO_MAX_TOKENS:-16}"
FO_REQ_TIMEOUT_S="${FO_REQ_TIMEOUT_S:-20}"
FO_STATUS_TIMEOUT_S="${FO_STATUS_TIMEOUT_S:-8}"
FO_EXPECT_CASCADE="${FO_EXPECT_CASCADE:-1}"
FO_EXPECT_STATUS="${FO_EXPECT_STATUS:-500}"
FO_FAULT_LABEL="${FO_FAULT_LABEL:-unspecified}"

FOTMP="$(mktemp -d 2>/dev/null || echo "/tmp/failover-canary.$$")"
trap 'rm -rf "$FOTMP" 2>/dev/null || true' EXIT

RED=0
_pass(){ echo "  GREEN  $1"; }
_red(){ RED=1; echo "  RED    $1"; }
_info(){ echo "         $1"; }
_stage(){ echo; echo "── $1 ─────────────────────────────────────────"; }

# ── token: canonical opencode.json derive (same as flow-canary.sh) ──────────
_bearer_token(){
  [ -n "${FO_TOKEN:-}" ] && { printf '%s' "$FO_TOKEN"; return 0; }
  [ -r "$FO_OPENCODE_CFG" ] || return 1
  python3 -c "
import json, sys
try:
    d = json.load(open('$FO_OPENCODE_CFG'))
    tok = (((d.get('provider') or {}).get('charon') or {}).get('options') or {}).get('apiKey')
    sys.stdout.write(tok or '')
except Exception:
    pass
" 2>/dev/null
}

# ── head model for the tier, from tier-models.tsv (same as flow-canary.sh) ──
_head_model(){
  local tier="$1"
  [ -r "$FO_TIER_TSV" ] || { echo "failover-canary: tier-models.tsv unreadable at $FO_TIER_TSV" >&2; return 1; }
  python3 -c "
import sys
target = '$tier'.lower()
with open('$FO_TIER_TSV') as f:
    for raw in f:
        line = raw.strip()
        if not line or line.startswith('#') or '\t' not in line:
            continue
        k, _, v = line.partition('\t')
        if k.strip().lower() == target:
            print(v.strip().split(',')[0].strip()); sys.exit(0)
sys.exit(0)
"
}

# ── GET /charon/status -> writes JSON to $1 ─────────────────────────────────
_status_json(){
  local tok="$1" out="$2"
  curl -s --max-time "$FO_STATUS_TIMEOUT_S" \
    -H "Authorization: Bearer $tok" -H "Accept: application/json" \
    "$FO_GATEWAY_URL/charon/status" -o "$out" 2>/dev/null || true
  [ -s "$out" ]
}

# ── the model's provider pool (chain[0] == the head-tier provider) ──────────
_pool_for_model(){
  local status_file="$1" model="$2"
  python3 -c "
import json,sys
try: d=json.load(open(sys.argv[1]))
except Exception: print(''); sys.exit(0)
ch=(d.get('pools') or {}).get(sys.argv[2]) or []
print(','.join(ch))
" "$status_file" "$model" 2>/dev/null
}

# ── one real request against the gateway; captures headers+body+timing ──────
# writes: $FOTMP/hdr.txt $FOTMP/body.json  and echoes "<http_code> <elapsed_s> <curl_rc>"
_send_request(){
  local tok="$1" model="$2" nonce="$3"
  local reqbody="$FOTMP/req.json"
  python3 -c "
import json, sys
json.dump({'model': sys.argv[1],
           'messages': [{'role':'user','content': sys.argv[2] + ' (failover-canary ' + sys.argv[4] + ')'}],
           'max_tokens': int(sys.argv[3])}, open(sys.argv[5],'w'))
" "$model" "$FO_PROMPT" "$FO_MAX_TOKENS" "$nonce" "$reqbody"

  local t0 t1 code rc
  t0="$(date +%s.%N)"
  code="$(curl -s --max-time "$FO_REQ_TIMEOUT_S" -o "$FOTMP/body.json" -D "$FOTMP/hdr.txt" -w '%{http_code}' \
    -H "Authorization: Bearer $tok" -H "Content-Type: application/json" \
    -X POST "$FO_GATEWAY_URL/v1/chat/completions" --data-binary "@$reqbody" 2>/dev/null)"
  rc=$?
  t1="$(date +%s.%N)"
  local elapsed
  elapsed="$(python3 -c "print(round(float('$t1')-float('$t0'),2))" 2>/dev/null || echo "?")"
  printf '%s %s %s\n' "${code:-000}" "$elapsed" "$rc"
}

_header(){ # <name>
  grep -i "^$1:" "$FOTMP/hdr.txt" 2>/dev/null | head -1 | sed 's/^[^:]*:[[:space:]]*//; s/[[:space:]]*$//' | tr -d '\r'
}

# ── optional provider -> Toxiproxy-proxy-name map (FO_PROXY_MAP="p1=px1,p2=px2")
# for a live run: resolves the EMPIRICALLY DISCOVERED head provider (see
# _stage_baseline) to the Toxiproxy proxy fronting it, exported as
# FO_HEAD_PROXY before FO_SEED_HEAD_CMD/FO_RESTORE_HEAD_CMD are eval'd, so a
# real seed command can address the right proxy without hardcoding a guess at
# which provider will serve. Unmapped/unset -> empty (the seed command must
# then already know its own target, as the hermetic test's hooks do). ───────
_proxy_for(){ # <provider>
  local provider="$1"
  [ -n "${FO_PROXY_MAP:-}" ] || return 0
  printf '%s' "$FO_PROXY_MAP" | tr ',' '\n' | while IFS='=' read -r p px; do
    [ "$p" = "$provider" ] && { printf '%s' "$px"; break; }
  done
}

# provider names named in an X-Charon-Failover-Reasons value ("p1=429; p2=unreachable")
_reason_providers(){
  printf '%s' "$1" | grep -oE '[A-Za-z0-9_.-]+=' | sed 's/=$//' | paste -sd, -
}

# ── PARK / FUNDING-CLASS EXCLUSION assertion (reused shape, flow-canary.sh
#    STAGE 3 / #188 dead-no-op class) — no parked/drained leg anywhere in the
#    served+attempted path for THIS response. ────────────────────────────────
_assert_no_parked_in_path(){ # <status_file> <served> <attempted-csv> <label>
  local status_file="$1" served="$2" attempted="$3" label="$4"
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
print(('SERVED:'+sv if served_excluded else '') + '|' + ','.join(bad))
" "$status_file" "$served" "$attempted" 2>/dev/null)"
  local served_bad path_bad
  served_bad="$(printf '%s' "$violation" | cut -d'|' -f1)"
  path_bad="$(printf '%s' "$violation" | cut -d'|' -f2)"
  if [ -n "$served_bad" ]; then
    _red "$label park: the SERVED leg is parked/drained ($served_bad) — exclusion is a DEAD NO-OP (#188 class)"
  elif [ -n "$path_bad" ]; then
    _red "$label park: a parked/drained provider was ATTEMPTED in the cascade ($path_bad) — exclusion did not fire (#188 class)"
  else
    _pass "$label park: no parked/drained provider appears in the served+attempted path"
  fi
}

# ── STAGE: BASELINE — normal request; the leg that serves it (with an EMPTY
#    X-Charon-Failover-Reasons, i.e. nothing already failed over) is discovered
#    as THIS RUN's head-tier leg, written to $FOTMP/head.txt for the cascade
#    stage to target. We deliberately do NOT assume the head is pools[model][0]
#    — the live routing brain reorders that raw pool by cooldown/cost/quality
#    (forwarder.py order_by_cooldown / order_pool_by_live_cost / quality_scorer)
#    before picking a leg, so "whoever actually served a clean baseline" is the
#    only honest ground truth for what "head" means on a given run (confirmed
#    empirically against the live 4-LOM gateway during this ticket's build —
#    pools[model][0] did NOT match the live served-by). ──────────────────────
_stage_baseline(){ # <tok> <model> <before_file> <label>
  local tok="$1" model="$2" before_file="$3" label="$4"
  _stage "$label — BASELINE (model=$model)"
  local pool result code elapsed rc provider reasons
  pool="$(_pool_for_model "$before_file" "$model")"
  if [ -z "$pool" ]; then
    _red "$label baseline: model '$model' has no provider pool in /charon/status — cannot canary"
    return 1
  fi
  result="$(_send_request "$tok" "$model" "baseline-$(date -u +%s)-$RANDOM")"
  code="$(printf '%s' "$result" | awk '{print $1}')"
  elapsed="$(printf '%s' "$result" | awk '{print $2}')"
  rc="$(printf '%s' "$result" | awk '{print $3}')"
  if [ "$rc" != "0" ]; then
    _red "$label baseline: curl failed (rc=$rc, elapsed=${elapsed}s) — gateway unreachable"
    return 1
  fi
  if [ "$code" != "200" ]; then
    _red "$label baseline: gateway returned HTTP $code (expected 200) — $(head -c 200 "$FOTMP/body.json" 2>/dev/null)"
    return 1
  fi
  provider="$(_header 'X-Charon-Provider')"
  reasons="$(_header 'X-Charon-Failover-Reasons')"
  _info "served-by=$provider  pool=[$pool]  reasons=${reasons:-<none>}  elapsed=${elapsed}s"
  if [ -z "$provider" ]; then
    _red "$label baseline: no X-Charon-Provider header — cannot identify the head-tier leg"
  elif printf '%s' "$pool" | tr ',' '\n' | grep -qxF "$provider"; then
    _pass "$label baseline: served-by '$provider' is a member of the '$model' pool"
    printf '%s' "$provider" > "$FOTMP/head.txt"
  else
    _red "$label baseline: served-by '$provider' is NOT in the '$model' pool ($pool) — MIS-ROUTE"
  fi
  if [ -z "$reasons" ]; then
    _pass "$label baseline: no X-Charon-Failover-Reasons — nothing failed over"
  else
    _red "$label baseline: unexpected X-Charon-Failover-Reasons ($reasons) on a baseline run — something is already failing"
  fi
  local after_file="$FOTMP/after-baseline.json"
  _status_json "$tok" "$after_file" || : > "$after_file"
  _assert_no_parked_in_path "$after_file" "$provider" "$(_reason_providers "$reasons")" "$label baseline"
}

# ── STAGE: CASCADE — head-tier fault seeded; assert the cascade (or, for a
#    non-failover-eligible status like a bare 500, assert the correct clean
#    same-leg relay — see the _EXHAUSTION_STATUSES note up top). `head` is the
#    EMPIRICALLY DISCOVERED leg from the just-ran BASELINE stage (not an
#    assumed pool[0] — see _stage_baseline's header comment for why). ───────
_stage_cascade(){ # <tok> <model> <before_file> <label> <head>
  local tok="$1" model="$2" before_file="$3" label="$4" head="$5"
  _stage "$label — CASCADE (expect_cascade=$FO_EXPECT_CASCADE, head=$head)"
  local pool result code elapsed rc provider reasons attempted
  pool="$(_pool_for_model "$before_file" "$model")"
  if [ -z "$head" ]; then
    _red "$label cascade: no head-tier leg was discovered by the BASELINE stage — cannot assert the cascade moved off it"
    return 1
  fi
  result="$(_send_request "$tok" "$model" "cascade-$(date -u +%s)-$RANDOM")"
  code="$(printf '%s' "$result" | awk '{print $1}')"
  elapsed="$(printf '%s' "$result" | awk '{print $2}')"
  rc="$(printf '%s' "$result" | awk '{print $3}')"
  if [ "$rc" = "28" ]; then
    _red "$label cascade: request HUNG (curl timeout after ${FO_REQ_TIMEOUT_S}s) — must be loud, never a hang"
    return 1
  fi
  if [ "$rc" != "0" ]; then
    _red "$label cascade: curl failed (rc=$rc, elapsed=${elapsed}s)"
    return 1
  fi
  provider="$(_header 'X-Charon-Provider')"
  reasons="$(_header 'X-Charon-Failover-Reasons')"
  attempted="$(_reason_providers "$reasons")"
  _info "served-by=$provider  reasons=${reasons:-<none>}  http=$code  elapsed=${elapsed}s  pool=[$pool]"

  if [ "$FO_EXPECT_CASCADE" = "1" ]; then
    if [ "$code" != "200" ]; then
      _red "$label cascade: gateway returned HTTP $code (expected 200 — the healthy NEXT leg should have served) — $(head -c 200 "$FOTMP/body.json" 2>/dev/null)"
      return 1
    fi
    _pass "$label cascade: gateway still returned HTTP 200 despite the seeded head-tier fault"
    if [ -z "$provider" ]; then
      _red "$label cascade: no X-Charon-Provider on the cascaded response"
    elif [ "$provider" = "$head" ]; then
      _red "$label cascade: served-by is STILL the faulted head '$head' — cascade did not occur"
    else
      _pass "$label cascade: served-by moved off the faulted head to '$provider'"
    fi
    if [ -z "$reasons" ]; then
      _red "$label cascade: X-Charon-Failover-Reasons is EMPTY — the failed head leg is not named"
    elif printf '%s' "$attempted" | tr ',' '\n' | grep -qxF "$head"; then
      _pass "$label cascade: X-Charon-Failover-Reasons names the failed head '$head' ($reasons)"
    else
      _red "$label cascade: X-Charon-Failover-Reasons ($reasons) does NOT name the failed head '$head'"
    fi
  else
    # non-cascade-eligible status (e.g. bare 500): correct behavior is a clean
    # same-leg relay, NOT a cascade attempt (proxy.py _EXHAUSTION_STATUSES).
    if [ "$code" = "$FO_EXPECT_STATUS" ]; then
      _pass "$label cascade: gateway relayed HTTP $code as-is (status not in the fail-over-eligible set — correct, no cascade attempted)"
    else
      _red "$label cascade: expected a clean relay of HTTP $FO_EXPECT_STATUS, got $code instead"
    fi
    if [ "$provider" = "$head" ] || [ -z "$provider" ]; then
      _pass "$label cascade: X-Charon-Provider still names the head leg '$head' (relay, not cascade)"
    else
      _red "$label cascade: served-by unexpectedly moved to '$provider' for a non-failover-eligible status — should not have cascaded"
    fi
    if [ -n "$reasons" ]; then
      _red "$label cascade: X-Charon-Failover-Reasons ($reasons) present on a non-cascading relay — no leg should have been recorded as failed-over"
    else
      _pass "$label cascade: no X-Charon-Failover-Reasons — consistent with a non-cascading relay"
    fi
  fi
  local after_file="$FOTMP/after-cascade.json"
  _status_json "$tok" "$after_file" || : > "$after_file"
  _assert_no_parked_in_path "$after_file" "$provider" "$attempted" "$label cascade"
}

# ── STAGE: ALL-LEGS-DOWN — every leg faulted; assert a clean LOUD error ─────
_stage_alldown(){ # <tok> <model> <label>
  local tok="$1" model="$2" label="$3"
  _stage "$label — ALL-LEGS-DOWN"
  local result code elapsed rc
  result="$(_send_request "$tok" "$model" "alldown-$(date -u +%s)-$RANDOM")"
  code="$(printf '%s' "$result" | awk '{print $1}')"
  elapsed="$(printf '%s' "$result" | awk '{print $2}')"
  rc="$(printf '%s' "$result" | awk '{print $3}')"
  _info "http=$code  elapsed=${elapsed}s  curl_rc=$rc"
  if [ "$rc" = "28" ]; then
    _red "$label all-down: request HUNG (curl timeout after ${FO_REQ_TIMEOUT_S}s) — a total-exhaustion must be a LOUD error, never a hang"
    return 1
  fi
  if [ "$rc" != "0" ]; then
    _red "$label all-down: curl failed outright (rc=$rc) instead of a clean HTTP error"
    return 1
  fi
  case "$code" in
    502|503) _pass "$label all-down: HTTP $code — a clean gateway-synthesized error status (not a raw upstream passthrough)" ;;
    200) _red "$label all-down: HTTP 200 — a request should NOT succeed when every leg is down" ;;
    *) _red "$label all-down: HTTP $code — not the expected clean 502/503 exhaustion status" ;;
  esac
  local msg
  msg="$(python3 -c "
import json,sys
try: d=json.load(open(sys.argv[1]))
except Exception: print(''); sys.exit(0)
print(((d.get('error') or {}).get('message')) or '')
" "$FOTMP/body.json" 2>/dev/null)"
  if [ -z "$msg" ]; then
    _red "$label all-down: response body has no structured error.message — looks like a raw passthrough, not a clean loud error"
  elif printf '%s' "$msg" | grep -qiE 'unreachable|exhausted'; then
    _pass "$label all-down: structured error.message ('$msg') names the exhaustion — LOUD, not silent"
  else
    _red "$label all-down: error.message ('$msg') does not read as an exhaustion/unreachable verdict"
  fi
}

main(){
  echo "════════════════════════════════════════════════════════════"
  echo " FAILOVER-CANARY — proves the routing-brain's failover cascade"
  echo " fault=$FO_FAULT_LABEL  gateway=$FO_GATEWAY_URL  tier=$FO_TIER"
  echo " $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "════════════════════════════════════════════════════════════"

  local tok model before_file
  tok="$(_bearer_token)"
  if [ -z "$tok" ]; then
    _red "no gateway Bearer token (FO_TOKEN unset and $FO_OPENCODE_CFG unreadable/empty)"
    echo; echo "████ FAILOVER-CANARY: RED ████"; exit 1
  fi
  model="$(_head_model "$FO_TIER")"
  if [ -z "$model" ]; then
    _red "tier '$FO_TIER' has no head model in $FO_TIER_TSV"
    echo; echo "████ FAILOVER-CANARY: RED ████"; exit 1
  fi
  before_file="$FOTMP/before.json"
  if ! _status_json "$tok" "$before_file"; then
    _red "gateway /charon/status unreachable/empty at $FO_GATEWAY_URL — cannot canary"
    echo; echo "████ FAILOVER-CANARY: RED ████"; exit 1
  fi

  _stage_baseline "$tok" "$model" "$before_file" "BASELINE"
  local head=""
  [ -f "$FOTMP/head.txt" ] && head="$(cat "$FOTMP/head.txt")"

  if [ -n "${FO_SEED_HEAD_CMD:-}" ]; then
    # export the discovered head (+ its resolved Toxiproxy proxy, if a map was
    # given) so a real seed/restore hook can target it without guessing.
    export FO_DISCOVERED_HEAD="$head"
    export FO_HEAD_PROXY="$(_proxy_for "$head")"
    bash -c "$FO_SEED_HEAD_CMD"
    _stage_cascade "$tok" "$model" "$before_file" "$FO_FAULT_LABEL" "$head"
    [ -n "${FO_RESTORE_HEAD_CMD:-}" ] && bash -c "$FO_RESTORE_HEAD_CMD"
    # revert proof — re-run baseline stage-shape assertions
    _stage_baseline "$tok" "$model" "$before_file" "REVERT-AFTER-$FO_FAULT_LABEL"
  else
    _info "FO_SEED_HEAD_CMD unset — skipping CASCADE stage (health-check-only run)"
  fi

  if [ -n "${FO_SEED_ALLDOWN_CMD:-}" ]; then
    bash -c "$FO_SEED_ALLDOWN_CMD"
    _stage_alldown "$tok" "$model" "ALL-DOWN"
    [ -n "${FO_RESTORE_ALLDOWN_CMD:-}" ] && bash -c "$FO_RESTORE_ALLDOWN_CMD"
    _stage_baseline "$tok" "$model" "$before_file" "REVERT-AFTER-ALL-DOWN"
  else
    _info "FO_SEED_ALLDOWN_CMD unset — skipping ALL-LEGS-DOWN stage"
  fi

  echo
  if [ "$RED" -eq 0 ]; then
    echo "════ FAILOVER-CANARY: GREEN — cascade behaved correctly ════"
    exit 0
  fi
  echo "████ FAILOVER-CANARY: RED — a broken cascade was caught (see RED lines above) ████"
  exit 1
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  main "$@"
fi
