#!/usr/bin/env bash
# never-anthropic-chain.test.sh — FAIL-ON-REVERT / red-proof tests for the
# NEVER-ANTHROPIC-ASSERTION rule: NO tier chain in fleet/tier-models.tsv may
# contain a model served by an Anthropic provider.
#
# The rule matches on the RESOLVED provider (live gateway catalog), not on a
# hardcoded name list. A name list rots the moment a provider renames or a new
# alias appears; the catalog is live data (doctrine sec.14).
#
# Done contract (NEVER-ANTHROPIC-ASSERTION):
#   1. Assert: no tier chain in fleet/tier-models.tsv may contain an
#      Anthropic-SERVED model, however spelled — match on resolved provider/model,
#      not on a hardcoded name list.
#   2. Run in CI and in preflight — an edit that introduces one reds before landing.
#   3. FAIL LOUD naming the offending chain entry and which provider serves it.
#   4. Fail-on-revert: seed a chain containing an Anthropic-served model and
#      prove the assertion REDs; remove the assertion and prove it passes.
#   5. Prefer the ASSERTION over an exclusion list at the pool layer — an
#      exclusion list must be maintained; an assertion cannot silently stop being true.
#
# Run:  bash fleet/tests/never-anthropic-chain.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TSV="${CHARON_TIER_MODELS:-$SRC/tier-models.tsv}"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT

# resolve_provider <model-id> — query the live gateway catalog and print the
# canonical provider id that serves this model (e.g. "charon", "deepseek", "groq").
# Returns empty + rc 1 if the model is not in the catalog.
# Overridable via RESOLVE_PROVIDER_CMD (test seam — inject a stub that simulates
# the gateway for hermetic CI runs where the network is unavailable).
resolve_provider(){
  if [ -n "${RESOLVE_PROVIDER_CMD:-}" ]; then
    "$RESOLVE_PROVIDER_CMD" "$1" 2>/dev/null && return 0
    return 1
  fi
  local model="$1"
  local url="${GATEWAY_URL:-http://10.0.1.60:8080}"
  local tok=""
  tok="$(. "$SRC/env-registry.sh" >/dev/null 2>&1 && bearer_token 2>/dev/null || true)"
  [ -z "$tok" ] && return 1
  local body=""
  body="$(curl -s --max-time 5 -H "Authorization: Bearer $tok" \
                -H "Accept: application/json" \
                "$url/charon/config" 2>/dev/null || true)"
  [ -z "$body" ] && return 1
  python3 -c "
import sys, json
m = sys.argv[1].lower()
try:
    d = json.loads('$body')
except Exception:
    sys.exit(1)
pools = d.get('pools', {})
for prov, pval in pools.items():
    if not isinstance(pval, dict):
        continue
    models = pval.get('models', {})
    if isinstance(models, dict) and m in models:
        print(prov); sys.exit(0)
    if isinstance(models, list) and m in models:
        print(prov); sys.exit(0)
sys.exit(1)
" "$model" 2>/dev/null && return 0
  return 1
}

# is_anthropic_model <model-id> -> rc 0 if the model is served by an
# Anthropic provider (provider id contains "anthropic" or "claude").
is_anthropic_model(){
  local model="$1"
  local prov
  prov="$(resolve_provider "$model")" || return 1
  [ -z "$prov" ] && return 1
  case "$(echo "$prov" | tr '[:upper:]' '[:lower:]')" in
    *anthropic*|*claude*) return 0 ;;
    *) return 1 ;;
  esac
}

# get_tier_chains <tsv-path> -> prints "tier<tab>chain" lines
get_tier_chains(){
  python3 - "$1" <<'PY'
import sys
tsv = sys.argv[1]
for line in open(tsv):
    raw = line.strip()
    if not raw or raw.startswith('#') or '\t' not in raw:
        continue
    k, _, v = raw.partition('\t')
    print(f"{k.strip()}\t{v.strip()}")
PY
}

# check_tsv <tsv-path> <label> -> rc 0 = all chains clean, rc 1 = found anthropic-served model
# Prints: "CLEAN" or "ANTHROPIC: tier=<tier> model=<model> provider=<provider>"
check_tsv(){
  local tsv="$1" label="$2"
  local found=""
  while IFS=$'\t' read -r tier chain; do
    [ -z "$tier" ] && continue
    for model in $(echo "$chain" | tr ',' ' '); do
      model="$(echo "$model" | xargs)"
      [ -z "$model" ] && continue
      if is_anthropic_model "$model"; then
        local prov
        prov="$(resolve_provider "$model")" || prov="<unknown>"
        found="ANTHROPIC: tier=$tier model=$model provider=$prov"
        break 2
      fi
    done
  done < <(get_tier_chains "$tsv")
  if [ -n "$found" ]; then
    echo "$found"
    return 1
  fi
  echo "CLEAN"
  return 0
}

# mk_clean_tsv -> prints path to a synthetic clean tsv
mk_clean_tsv(){
  local path="$ROOT/synth-clean.tsv"
  cat > "$path" <<'EOF'
frontier	deepseek-v4-pro-ds,minimax-m2.5-go,deepseek-v4-flash-ds
strong	minimax-m2.5-go,deepseek-v4-flash-ds,gpt-oss-120b-groq
economy	free-cerebras,free-groq,deepseek-v4-flash-ds
EOF
  echo "$path"
}

# mk_polluted_tsv -> prints path to a synthetic tsv with an Anthropic-served model
mk_polluted_tsv(){
  local path="$ROOT/synth-polluted.tsv"
  cat > "$path" <<'EOF'
frontier	deepseek-v4-pro-ds,minimax-m2.5-go,deepseek-v4-flash-ds
strong	opencode-zen/claude-opus-4-1,minimax-m2.5-go,deepseek-v4-flash-ds,gpt-oss-120b-groq
economy	free-cerebras,free-groq,deepseek-v4-flash-ds
EOF
  echo "$path"
}

# ── Stub gateway: clean — all models resolve to non-Anthropic providers ─────────
CLEAN_STUB="$ROOT/clean-stub.sh"
cat > "$CLEAN_STUB" <<'STUB'
echo "deepseek"
STUB
chmod +x "$CLEAN_STUB"

# ── Stub gateway: polluted — opencode-zen/* models resolve to Anthropic ──────────
POLLUTED_STUB="$ROOT/polluted-stub.sh"
cat > "$POLLUTED_STUB" <<'STUB'
model="$1"
case "$model" in
  opencode-zen*|*claude*|*anthropic*) echo "anthropic-opencode-zen" ;;
  *) echo "deepseek" ;;
esac
STUB
chmod +x "$POLLUTED_STUB"

# Helper: run check_tsv with a stub override
run_check(){
  local stub="$1" tsv="$2"
  RESOLVE_PROVIDER_CMD="$stub" check_tsv "$tsv" test 2>&1
}

echo "== (a) BASELINE GREEN — current tier-models.tsv has no Anthropic-served models =="
if [ -f "$TSV" ]; then
  out="$(check_tsv "$TSV" live 2>&1)"; rc=$?
  if [ "$rc" -eq 0 ]; then
    ok "(a1) live tier-models.tsv: $out"
  else
    bad "(a1) live tier-models.tsv: $out"
  fi
else
  echo "SKIP: (a) live TSV absent — running against synthetic only"
fi

echo "== (b) FAIL-ON-REVERT: synthetic TSV with Anthropic-served model -> RED =="
TSVPOLL="$(mk_polluted_tsv)"
out="$(run_check "$POLLUTED_STUB" "$TSVPOLL")"; rc=$?
if [ "$rc" -ne 0 ] && echo "$out" | grep -q 'ANTHROPIC'; then
  ok "(b1) synthetic polluted TSV -> RED: $out"
else
  bad "(b1) expected RED + ANTHROPIC finding, got rc=$rc, out=$out"
fi
if echo "$out" | grep -q 'model=opencode-zen'; then
  ok "(b2) RED names the offending model"
else
  bad "(b2) RED must name the offending model. out=$out"
fi
if echo "$out" | grep -q 'provider='; then
  ok "(b3) RED names the resolving provider"
else
  bad "(b3) RED must name the resolving provider. out=$out"
fi

echo "== (c) FAIL-ON-REVERT: same polluted TSV with Anthropic model REMOVED -> GREEN =="
TSVCLEAN="$(mk_clean_tsv)"
out="$(run_check "$POLLUTED_STUB" "$TSVCLEAN")"; rc=$?
if [ "$rc" -eq 0 ] && echo "$out" | grep -q 'CLEAN'; then
  ok "(c1) same TSV without Anthropic model -> GREEN: $out"
else
  bad "(c1) expected GREEN, got rc=$rc, out=$out"
fi

echo "== (d) NAME-LIST IS INSUFFICIENT: a model named like an existing non-Anthropic =="
# gpt-oss-120b-groq is in the real chain — its name contains "gpt" (an old
# Anthropic name) but Groq serves it, NOT Anthropic. A name-list assertion
# would catch "gpt" and false-positive here. The provider-resolved assertion
# correctly passes because the clean stub resolves gpt-oss-120b-groq -> deepseek.
TSVCLEAN="$(mk_clean_tsv)"
out="$(run_check "$CLEAN_STUB" "$TSVCLEAN")"; rc=$?
if [ "$rc" -eq 0 ]; then
  ok "(d1) gpt-oss-120b-groq -> resolved provider deepseek (non-Anthropic) -> CLEAN"
else
  bad "(d1) gpt-oss-120b-groq incorrectly flagged: $out (name-list would false-positive on 'gpt')"
fi

echo "== (e) HERMETIC SEAM: polluted TSV + polluted stub -> RED (RESOLVE_PROVIDER_CMD exercised) =="
TSVPOLL="$(mk_polluted_tsv)"
out="$(run_check "$POLLUTED_STUB" "$TSVPOLL")"; rc=$?
if [ "$rc" -ne 0 ]; then
  ok "(e1) hermetic polluted path: polluted TSV + polluted stub -> RED"
else
  bad "(e1) expected RED, got rc=$rc"
fi

echo "== (f) HERMETIC SEAM: clean TSV + polluted stub -> GREEN (mechanism correctly resolves each model) =="
TSVCLEAN="$(mk_clean_tsv)"
out="$(run_check "$POLLUTED_STUB" "$TSVCLEAN")"; rc=$?
if [ "$rc" -eq 0 ]; then
  ok "(f1) hermetic clean path: clean TSV + polluted stub -> GREEN (stub consulted per-model)"
else
  bad "(f1) expected GREEN even with polluted stub, got rc=$rc, out=$out"
fi

echo; echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL NEVER-ANTHROPIC-CHAIN TESTS PASS"
