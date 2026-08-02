#!/usr/bin/env bash
# fleet/reviewer-tab.sh — open a NAMED, COLOURED Windows Terminal TAB running review-pool.sh.
# One reviewer-tab per physical machine; each tab is a reviewer-pool process.
# Usage: reviewer-tab.sh [--tier <frontier|strong|economy>] [--color <#hex>] [--wait <min>] [--retries <n>]
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── DROID-CLIENT-PREFLIGHT (same fault class as fleet-droid.sh:21-32) ──────────────────
# A tab launched via `wt bash <script>` runs a NON-LOGIN bash, so ~/.local/bin is absent.
# APPEND, never prepend.
case ":${PATH}:" in
  *":$HOME/.local/bin:"*) : ;;
  *) [ -d "$HOME/.local/bin" ] && export PATH="$PATH:$HOME/.local/bin" ;;
esac

# Fail LOUD and EARLY when any required binary is missing.
_missing=()
for _b in git gh python3 timeout curl; do
  command -v "$_b" >/dev/null 2>&1 || _missing+=("$_b")
done
if [ "${#_missing[@]}" -gt 0 ]; then
  echo "[reviewer-tab] FATAL: required binary not found: ${_missing[*]}" >&2
  echo "[reviewer-tab]   PATH searched: $PATH" >&2
  echo "[reviewer-tab]   LOCAL ENVIRONMENT fault — no review cycle attempted." >&2
  echo "[reviewer-tab]   Likely cause: launched from a non-login, non-interactive shell." >&2
  unset _b _missing
  exit 4
fi
unset _b _missing

# ── gh auth check ─────────────────────────────────────────────────────────────────────
if ! gh auth status >/dev/null 2>&1; then
  echo "[reviewer-tab] FATAL: gh is not authenticated — review-pool.sh needs gh pr list/diff." >&2
  exit 4
fi

# ── gateway token derivation (same approach as fleet-droid.sh:77-96) ─────────────────
# opencode.json's provider.charon.options.apiKey is the only source of truth.
# ambient env may be stale; re-derive unconditionally.
if [ -r "$FLEET/env-registry.sh" ]; then
  _tok="$( . "$FLEET/env-registry.sh" >/dev/null 2>&1 && bearer_token 2>/dev/null || true )"
  [ -n "$_tok" ] && export CHARON_GATEWAY_TOKEN="$_tok"
fi
unset _tok

# ── /v1/models parse check ──────────────────────────────────────────────────────────
# Refuse to start when the gateway is unreachable or its model list is unparseable.
# review-pool.sh hard-loops "no claimable review items" when models are absent,
# and BOUNCE verdict reads like a code defect — so fail loudly here instead.
if [ -n "${CHARON_GATEWAY_TOKEN:-}" ]; then
  _models_raw="$(curl -s -m 5 -H "Authorization: Bearer $CHARON_GATEWAY_TOKEN" \
    "http://10.0.1.60:8080/v1/models" 2>/dev/null)" || true
  if [ -z "$_models_raw" ]; then
    echo "[reviewer-tab] FATAL: /v1/models returned empty or unreachable." >&2
    echo "[reviewer-tab]   gateway=$CHARON_GATEWAY_URL token=<derived>" >&2
    exit 4
  fi
  if ! printf '%s' "$_models_raw" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    echo "[reviewer-tab] FATAL: /v1/models response is not valid JSON." >&2
    exit 4
  fi
fi
unset _models_raw

# ── derive the review model chain from tier-models.tsv ───────────────────────────────
# Tier must be canonical (frontier/strong/economy). reviewer-tab always uses
# STRONG by default (adversarial code review, not high-tier evaluation work).
canon_tier(){ case "$1" in
  high|opus) echo frontier;;
  med|sonnet) echo strong;;
  low|haiku) echo economy;;
  *) echo "$1";;
esac; }
tier_chain(){
  local tmf="${CHARON_TIER_MODELS:-$FLEET/tier-models.tsv}"
  awk -F'\t' -v t="$1" '$1!~/^#/ && $1==t {print $NF; exit}' "$tmf" 2>/dev/null || true
}

# ── argument parsing ───────────────────────────────────────────────────────────────
TIER="strong"; COLOR="#f59e0b"; WAIT_MIN=3; RETRIES=6
while [ $# -gt 0 ]; do case "$1" in
  --tier)     TIER="${2:?--tier needs a value}"; shift 2;;
  --color)    COLOR="${2:?--color needs a #hex}"; shift 2;;
  --wait)     WAIT_MIN="${2:?--wait needs minutes}"; shift 2;;
  --retries)  RETRIES="${2:?--retries needs a count}"; shift 2;;
  --help|-h)  echo "usage: reviewer-tab.sh [--tier <frontier|strong|economy>] [--color #hex>] [--wait <min>] [--retries <n>]"; exit 0;;
  *)          echo "unknown arg: $1" >&2; exit 2;;
esac; done

CANON="$(canon_tier "$TIER")"
CHAIN="$(tier_chain "$CANON")"
if [ -z "$CHAIN" ]; then
  echo "[reviewer-tab] FATAL: no gateway model chain for tier '$TIER' in $FLEET/tier-models.tsv." >&2
  exit 3
fi
echo "[reviewer-tab] launching reviewer tab — tier=$TIER model-chain=$CHAIN color=$COLOR"

# ── identity ─────────────────────────────────────────────────────────────────────────
DROID_ID="reviewer-tab-$$"
export CHARON_DROID_ID="$DROID_ID"
export CHARON_REVIEW_MODELS="$CHAIN"

# ── spawn the tab ───────────────────────────────────────────────────────────────────
exec "$FLEET/spawn-tab.sh" "reviewer($DROID_ID)" "$COLOR" \
  bash "$FLEET/review-pool.sh" "$TIER" --wait "$WAIT_MIN" --retries "$RETRIES"
