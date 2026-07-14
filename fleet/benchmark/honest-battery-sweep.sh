#!/usr/bin/env bash
# honest-battery-sweep.sh — preflight a set of NON-ANTHROPIC models through the
# three RED-proof honest-battery tickets (PROVIDER-URL-HELPER / SECRET-HOTROTATE /
# RFL-3), one model at a time, so each clean run lands a source=live/stage=active
# scorecard row via dogfood-eval's finalize_live_capture. assign.py then drives
# per-tier picks off the real-outcome live lane.
#
# HARD RULE [sg-never-anthropic]: no claude-*/opus/sonnet/haiku id is ever swept.
# Leg-parked ids (phi-4, gpt-5.5, gpt-oss-120b-groq) are excluded by default.
#
# Usage: honest-battery-sweep.sh [model ...]   (defaults to the healthy roster below)
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 3   # -> charon-private
FLEET="fleet"
BRIEFS="$FLEET/board/briefs"

# --- healthy non-Anthropic roster (opencode.json aliases minus parked) ---
DEFAULT_MODELS=(
  deepseek-v4-pro minimax-m3-together kimi-k2.6 glm-5.2   # strong anchors
  deepseek-v4-flash gemma-4-31b-cb free-mistral-code minimax-m2.7  # economy
)
MODELS=("$@"); [ ${#MODELS[@]} -eq 0 ] && MODELS=("${DEFAULT_MODELS[@]}")

# hard guard: strip any Anthropic id that slips in
FILTERED=()
for m in "${MODELS[@]}"; do
  case "$m" in
    *claude*|*opus*|*sonnet*|*haiku*|*anthropic*)
      echo "[sweep] SKIP (sg-never-anthropic): $m" >&2 ;;
    phi-4|gpt-5.5|gpt-oss-120b-groq)
      echo "[sweep] SKIP (leg-parked): $m" >&2 ;;
    *) FILTERED+=("$m") ;;
  esac
done
MODELS=("${FILTERED[@]}")
echo "[sweep] models: ${MODELS[*]}"

# --- ticket table: label | brief | work_class | DOGFOOD_TEST_CMD | expect-files ---
run_ticket() {
  local label="$1" wclass="$2" testcmd="$3" expect="$4"
  echo "[sweep] ===== TICKET $label (work_class=$wclass) x ${#MODELS[@]} models ====="
  DOGFOOD_WORK_CLASS="$wclass" \
  DOGFOOD_TEST_CMD="$testcmd" \
  DOGFOOD_EXPECT_FILES="$expect" \
  DOGFOOD_LATENCY_BUDGET_S="${SWEEP_LATENCY_BUDGET_S:-480}" \
    bash "$FLEET/benchmark/dogfood-eval.sh" "$label" "$BRIEFS/${label}-eval.md" "${MODELS[@]}"
}

run_ticket SECRET-HOTROTATE bugfix \
  'PYTHONPATH=src python3 -m pytest tests/test_secrets.py -q && python3 -c "import re,sys; c=open(\"tests/test_secrets.py\").read(); sys.exit(0 if re.search(r\"def test_.*(force_refresh|hot_rotat)\", c) else 1)"' \
  'src/charon/secrets.py tests/test_secrets.py'

run_ticket PROVIDER-URL-HELPER refactor \
  'PYTHONPATH=src python3 -c "from charon.providers import models_url, chat_url" && python3 -c "import re,sys; c=open(\"tests/test_providers.py\").read(); sys.exit(0 if re.search(r\"def test_(models_url|chat_url)_\w+\", c) else 1)" && PYTHONPATH=src python3 -m pytest tests/test_providers.py tests/test_discover.py tests/test_config.py -q' \
  'src/charon/providers.py src/charon/discover.py src/charon/config/keyprobe.py tests/test_providers.py'

run_ticket RFL-3 routing \
  'PYTHONPATH=src python3 -m pytest -q tests/test_image_routing.py && python3 -c "import re,sys; c=open(\"tests/test_image_routing.py\").read(); sys.exit(0 if re.search(r\"def test_image_request_excludes_text_only_model\", c) else 1)" && PYTHONPATH=src python3 -m pytest -q' \
  'src/charon/forwarder.py src/charon/proxy_server.py tests/test_image_routing.py'

echo "[sweep] DONE. Review live-lane rows: python3 fleet/capability/assign.py --work-class <wc> [--tier <t>]"
