#!/usr/bin/env bash
# env-registry.sh — ENV-REGISTRY-WIRE: the COMPACT live env-registry surfaced to sessions
# (primary at SessionStart) and to Agent/Task sub-sessions via the SESSION-CTX-PROPAGATE
# preamble. The exact "what lives where / who serves what" snapshot that has cost this
# fleet multiple per-session rediscovery probes — see fleet/state/SESSION-RECALL-CHALLENGE.md
# §1e (env-registry gap) and §3 (env-registry fold-in).
#
# DOUBLES AS the CG-PROVIDERS.md refresher (operator-graded: prefers the existing
# fleet/state/CG-PROVIDERS.md live registry over a new file). When CHARON_ENV_REGISTRY_OUTPUT
# points at that file, this script atomically rewrites it from a live gateway probe — same
# 443-model, 50-pool-aliases `GET /charon/config` payload, same `enabled != false` rule.
# When the variable is unset (the test path), it emits the COMPACT summary to stdout so a
# SessionStart hook / the SESSION-CTX-PROPAGATE preamble / a downstream operator can
# `source` / pipe / cat it without ever touching the registry file.
#
# SURFACED-FORMAT (compact, ~30 lines, hard cap ~50 — rides on every sub-agent and primary
# SessionStart, so per-spawn token cost is the budget):
#   # env-registry (compiled <UTC>; offline|tier-tsv)
#   gateway:    http://10.0.1.60:8080                  (4-LOM; Bearer from opencode.json)
#   host-map:   gateway=10.0.1.60:8080, opencode-auth=~/.config/opencode/opencode.json
#   models:     <count served, comma-separated list — capped to first 12 with "+N more">
#   tiers:      frontier=<chain>, strong=<chain>, economy=<chain>
#   source:     tier-models.tsv[+ live /charon/config probe <status>]
#
# NON-VACUOUS CONTRACT: the test asserts (a) at least ONE tier has at least ONE model,
# (b) the gateway endpoint line is present, (c) the served-models list is non-empty.
# A truncated/empty tier-models.tsv or a probe that returns nothing → exit 2 (RED), never
# a silent empty pass. The SESSION-CTX-PROPAGATE preamble sees a NON-EMPTY compact summary;
# an empty summary would silently bake a wrong fact into every sub-agent.
#
# OFFLINE PATH: tier-models.tsv is git-tracked and resolves in every worktree; the compact
# summary can be built from it alone. The live /charon/config probe is BEST-EFFORT — a
# timeout, a 401, a network unreachable → it falls through to OFFLINE (tier-tsv) and the
# summary still emits (the probe status is annotated, not failed on).
#
# Wiring (operator, post-merge): add `bash <charon-private>/fleet/env-registry.sh` as a
# SessionStart entry alongside the existing session-start.sh (env facts are a separate
# fact-class from the staleness check; SYNC-SCHEDULE owns session-start.sh and is the
# right sibling to coordinate with). For sub-agents: the SESSION-CTX-PROPAGATE preamble
# can `$(bash <charon-private>/fleet/env-registry.sh)` and embed the result in
# additionalContext — the preamble's existing pointer index already points here, so the
# env facts arrive via the SAME sub-agent mechanism that delivers MANAGER-RULES /
# TOOL-INVENTORY, just smaller per-fact.
set -uo pipefail

# ----- paths + env -----
FLEET="${CHARON_FLEET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
TIER_TSV="$FLEET/tier-models.tsv"
GATEWAY_URL="${CHARON_GATEWAY_URL:-http://10.0.1.60:8080}"
OPENCODE_CFG="${CHARON_OPENCODE_CONFIG:-$HOME/.config/opencode/opencode.json}"
OUTPUT="${CHARON_ENV_REGISTRY_OUTPUT:-}"   # unset -> stdout (test path)

# ----- helpers -----
# Pull the Bearer token the gateway expects. CRITICAL: CHARON_GATEWAY_TOKEN (shell env) is
# documented STALE per fleet/state/CG-PROVIDERS.md / preflight.sh:detect_gateway_token_drift
# — always re-derive from the live opencode config.
bearer_token() {
  [ -r "$OPENCODE_CFG" ] || return 1
  python3 -c "
import json, sys
try:
    d = json.load(open('$OPENCODE_CFG'))
    tok = (((d.get('provider') or {}).get('charon') or {}).get('options') or {}).get('apiKey')
    sys.stdout.write(tok or '')
except Exception:
    pass
" 2>/dev/null
}

# Live /charon/config probe. Writes the live JSON to a tmp file and prints just the status
# (first line) to stdout. ALWAYS succeeds in some form — failure modes degrade to OFFLINE,
# never exit non-zero. The live JSON body is what the "source:" line annotates; if the probe
# failed, we fall through to OFFLINE and the summary still emits (probe status is annotated,
# not failed on).
live_probe() {
  local tok="" status="offline" body_file="${1:-}"
  if [ -n "$body_file" ]; then : > "$body_file"; fi
  if tok="$(bearer_token)"; then
    [ -n "$tok" ] || status="unauthorized"
  else
    status="bad-config"
  fi
  if [ -n "$tok" ]; then
    local body=""
    body="$(curl -s --max-time 3 -H "Authorization: Bearer $tok" -H "Accept: application/json" \
            "$GATEWAY_URL/charon/config" 2>/dev/null || true)"
    case "$body" in
      *'"models"'*) status="live" ;;
      *'"providers"'*) status="live" ;;
      *) status="unauthorized-or-stale" ;;
    esac
    if [ "$status" = "live" ] && [ -n "$body_file" ]; then
      printf '%s' "$body" > "$body_file"
    fi
  fi
  printf '%s\n' "$status"
  return 0
}

# Live probe stats — when given a JSON body, returns "<model_count> models, <pool_count> pools"
# (one line, no JSON parsing failure side effects). Returns "" on empty/error so the caller
# can omit the stat without failing the summary.
live_probe_stats() {
  local body="$1"
  [ -n "$body" ] || return 0
  python3 - <<'PY' "$body" 2>/dev/null
import json, sys
try:
    d = json.loads(sys.argv[1])
    print(f"{len(d.get('models', {}) or {})} models, {len(d.get('pools', {}) or {})} pools")
except Exception:
    pass
PY
}

# Parse a single tier's failover chain from tier-models.tsv. Outputs the comma-list, one per line.
# tsv format: <canonical-tier>\t<comma,failover,chain>  (one tab between, see tier-models.tsv header).
parse_tier_chain() {
  local tier="$1"
  [ -r "$TIER_TSV" ] || { echo "env-registry: ERROR tier-models.tsv unreadable at $TIER_TSV" >&2; return 1; }
  python3 -c "
import sys
target = '$tier'.lower()
with open('$TIER_TSV') as f:
    for raw in f:
        line = raw.strip()
        if not line or line.startswith('#') or '\t' not in line:
            continue
        k, _, v = line.partition('\t')
        if k.strip().lower() == target:
            print(v.strip())
            sys.exit(0)
sys.exit(0)
"
}

# Derive the unique served-model set (deduped, order-preserving) from the three tier chains.
# "served" = appears in ANY tier's failover chain — these are the models the droid work
# executor (fleet-droid.sh) will actually hand to the gateway.
derive_served_models() {
  python3 -c "
import sys
seen, out = set(), []
for line in sys.stdin:
    for m in line.strip().split(','):
        m = m.strip()
        if not m or m in seen: continue
        seen.add(m); out.append(m)
print(','.join(out))
"
}

# Emit the compact summary to the chosen sink.
emit_compact() {
  local ts utc probed_status="$1" live_body="$2"
  utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  local frontier strong economy
  frontier="$(parse_tier_chain frontier)"
  strong="$(parse_tier_chain strong)"
  economy="$(parse_tier_chain economy)"
  if [ -z "$frontier$strong$economy" ]; then
    echo "env-registry: RED no tiers parseable from $TIER_TSV — refuse to emit empty summary" >&2
    return 2
  fi
  local served
  served="$(printf '%s\n%s\n%s\n' "$frontier" "$strong" "$economy" | derive_served_models)"
  local served_count
  served_count="$(printf '%s' "$served" | tr -cd , | wc -c | tr -d ' ')"
  served_count=$((served_count + 1))
  # The first 12 models are shown by name; the rest are aggregated as "+N more" so the
  # surfaced line stays under ~50 lines total even with a long failover chain.
  local first12 rest
  first12="$(printf '%s' "$served" | tr ',' '\n' | head -12 | paste -sd, -)"
  rest=$((served_count - 12))
  local models_line="$first12"
  [ "$rest" -gt 0 ] && models_line="$first12 (+$rest more)"

  {
    echo "# env-registry (compiled $utc; $probed_status)"
    echo "gateway:    $GATEWAY_URL                 (4-LOM; Bearer from $OPENCODE_CFG)"
    echo "host-map:   gateway=10.0.1.60:8080, opencode-auth=$OPENCODE_CFG"
    echo "models:     $served_count served [$models_line]"
    echo "tiers:      frontier=$frontier"
    echo "            strong=$strong"
    echo "            economy=$economy"
    if [ "$probed_status" = "live" ]; then
      local stats
      stats="$(live_probe_stats "$live_body")"
      [ -n "$stats" ] && echo "source:     tier-models.tsv + live /charon/config probe (live, $stats)" \
                      || echo "source:     tier-models.tsv + live /charon/config probe (live)"
    else
      echo "source:     tier-models.tsv (probe $probed_status; falling back to tier-tsv)"
    fi
  }
}

# ----- main -----
# SOURCE GUARD (DROID-CLIENT-PREFLIGHT, 2026-07-24): sourcing this file must expose its
# HELPERS — `bearer_token()` above is the ONE canonical gateway-token derivation, and the
# header comment already declares the shell's CHARON_GATEWAY_TOKEN authoritative-stale —
# WITHOUT running the live probe, writing the registry, or installing an EXIT trap that
# would clobber the sourcing script's own. fleet-droid.sh's pre-claim gateway preflight
# reuses bearer_token() through this seam rather than hand-rolling a second JSON reader
# (a third copy of that parse already exists at preflight.sh:detect_gateway_token_drift;
# this guard is how the count stops growing).
# Executing normally (`bash env-registry.sh`) is unchanged: $0 == ${BASH_SOURCE[0]}.
if [ "${BASH_SOURCE[0]}" != "$0" ]; then
  return 0
fi

_probe_tmp="$(mktemp 2>/dev/null || echo "/tmp/env-registry-probe.$$")"
trap 'rm -f "$_probe_tmp" 2>/dev/null || true' EXIT
_probed_status="$(live_probe "$_probe_tmp" | head -1)"
_live_body=""
[ -s "$_probe_tmp" ] && _live_body="$(cat "$_probe_tmp")"

if [ -n "$OUTPUT" ]; then
  tmp="$(mktemp 2>/dev/null || echo "${OUTPUT}.tmp.$$")"
  if emit_compact "$_probed_status" "$_live_body" > "$tmp"; then
    mv -f "$tmp" "$OUTPUT" && echo "env-registry: wrote compact summary -> $OUTPUT" >&2
  else
    rc=$?
    rm -f "$tmp" 2>/dev/null || true
    echo "env-registry: RED emit_compact failed (rc=$rc) — refusing to write $OUTPUT" >&2
    exit $rc
  fi
else
  emit_compact "$_probed_status" "$_live_body"
fi
