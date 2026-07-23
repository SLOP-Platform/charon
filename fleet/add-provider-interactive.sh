#!/usr/bin/env bash
# fleet/add-provider-interactive.sh — interactive loop front-end for add-provider.sh
#
# Operator types a provider NAME + API KEY; this script looks the name up in an
# embedded PROVIDER REGISTRY (base_url + optional model:upstream mappings) and
# calls fleet/add-provider.sh (the tested backend) to do the actual wiring. No
# CLI/ssh/docker plumbing is reinvented here — this is a thin UX shell over the
# existing, tested add-provider.sh.
#
# Model mappings are deliberately left EMPTY for every registry entry: step 3 of
# add-provider.sh (`charon.cli models import <name>`) already auto-imports the
# provider's whole catalog. Hand-guessing exact upstream model-id strings here
# (e.g. a chutes.ai HF-style path) risks silently wiring a WRONG mapping; the
# safer default is base_url + key + auto-import, then pin specific
# model:upstream mappings later once verified live against the provider's own
# GET /models response. (This mirrors the guidance in
# fleet/state/PROVIDER-WIRING-RECIPES.md.)
#
# Usage: fleet/add-provider-interactive.sh [--dry-run]
#   --dry-run is forwarded to add-provider.sh for every provider added this run.
#
# Loop, per provider:
#   1. Prompt for a provider name. Blank -> print a summary and exit (blank ENDS
#      the whole script, it does not skip to the next iteration).
#   2. Prompt for that provider's API key — NO ECHO (read -rs, secrets ratchet).
#      The key is never visible in terminal scrollback/tmux history.
#   3. Registry lookup: known name -> base_url (+ funding_class + any mappings)
#      auto-filled. Unknown name -> prompt once for a base_url fallback.
#   4. Prompt for funding_class (1=free 2=sub 3=drain 4=PAYG) if not registry-known.
#   5. Write key to mktemp (chmod 600), run add-provider.sh with --funding-class,
#      capture pass/fail, remove the temp key file.
#   6. Print pass/fail for that provider, loop back to step 1.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADD_PROVIDER="$SCRIPT_DIR/add-provider.sh"

DRY_RUN_FLAG=()
for a in "$@"; do
  case "$a" in
    --dry-run) DRY_RUN_FLAG=(--dry-run) ;;
    -h|--help)
      printf 'usage: %s [--dry-run]\n' "$0"
      exit 0
      ;;
  esac
done

[ -x "$ADD_PROVIDER" ] || {
  printf 'add-provider-interactive: ERROR: backend not found or not executable: %s\n' "$ADD_PROVIDER" >&2
  exit 1
}

# --- PROVIDER REGISTRY -----------------------------------------------------
# name -> base_url. Empty value means "no confirmed base_url" (prompts the
# operator with a warning instead of guessing). Populated from the wiring
# recipes compiled in fleet/state/PROVIDER-WIRING-RECIPES.md +
# fleet/state/CG-PROVIDERS.md (already-wired providers, included for
# completeness so this one script covers both new and existing providers).
declare -A REGISTRY_BASE_URL=(
  # --- operator-active, wiring-pending-key (this task) ---
  [chutes]="https://llm.chutes.ai/v1"
  [commandcode]="https://api.commandcode.ai/provider/v1/"
  [synthetic]="https://api.synthetic.new/openai/v1"
  [trae]=""   # TODO: confirm base_url — no public model-serving API found as of
              # 2026-07-13 (ByteDance Trae is an IDE product; BYOK custom-model
              # support is client-side inside the IDE, not a hosted endpoint a
              # gateway can route through). Confirmed twice: fleet/reviews/
              # PROVIDER-REVIEW-2026-07-10.md + a live web search this session.
              # Re-verify before assuming this changed.
  [featherless]="https://api.featherless.ai/v1"

  # --- already-wired presets (fleet/state/CG-PROVIDERS.md, for completeness) ---
  [nanogpt]="https://nano-gpt.com/api/v1"
  [openrouter]="https://openrouter.ai/api/v1"
  [deepseek]="https://api.deepseek.com/v1"
  [groq]="https://api.groq.com/openai/v1"
  [cerebras]="https://api.cerebras.ai/v1"
  [mistral]="https://api.mistral.ai/v1"
  [together]="https://api.together.xyz/v1"
  [zai]="https://api.z.ai/api/paas/v4"
  [cline-pass]="https://api.cline.bot/api/v1"
  [fireworks]="https://api.fireworks.ai/inference/v1"
  [sambanova]="https://api.sambanova.ai/v1"
  [replicate]="https://api.replicate.com/v1"
  [xai]="https://api.x.ai/v1"
  [nvidia]="https://integrate.api.nvidia.com/v1"
)

# name -> space-separated "model:upstream" pairs. Deliberately empty for every
# entry (see header note) — models import auto-catalogs on add. Left as a real
# associative array (not just a comment) so a future recipe can populate a row
# without changing the lookup logic.
declare -A REGISTRY_MODELS=()

# name -> funding_class. 1=free-recurring, 2=flat-sub, 3=drain-prepaid, 4=PAYG.
# Populated from fleet/state/REGISTRY-CANDIDATES.md and CG-PROVIDERS.md research.
# Unknown providers are prompted.
declare -A REGISTRY_FUNDING_CLASS=(
  [chutes]="4"
  [commandcode]="4"
  [synthetic]="4"
  [trae]="4"
  [featherless]="4"
  [nanogpt]="4"
  [openrouter]="4"
  [deepseek]="4"
  [groq]="1"
  [cerebras]="1"
  [mistral]="4"
  [together]="4"
  [zai]="4"
  [cline-pass]="4"
  [fireworks]="4"
  [sambanova]="4"
  [replicate]="4"
  [xai]="4"
  [nvidia]="4"
)

# --- summary tracking --------------------------------------------------------
declare -a SUMMARY=()

print_summary() {
  printf '\n=== add-provider-interactive: summary (%d provider(s)) ===\n' "${#SUMMARY[@]}"
  if [ "${#SUMMARY[@]}" -eq 0 ]; then
    printf '(none added this run)\n'
    return
  fi
  local line
  for line in "${SUMMARY[@]}"; do
    printf '%s\n' "$line"
  done
}

# --- unconditional key-file cleanup (FLAW-1 fix: survive Ctrl-C/SIGINT/TERM) ---
# The key temp file must never outlive the script, including on an operator
# Ctrl-C mid-run (proven to leak otherwise). A trap guarantees cleanup on ANY exit.
keyfile=""
cleanup_keyfile() {
  [ -n "${keyfile:-}" ] || return 0
  if command -v shred >/dev/null 2>&1; then shred -u "$keyfile" 2>/dev/null || rm -f "$keyfile"; else rm -f "$keyfile"; fi
  keyfile=""
}
trap cleanup_keyfile EXIT INT TERM

# --- main loop ----------------------------------------------------------------
while true; do
  printf 'Provider name (blank to finish): '
  if ! IFS= read -r name; then
    break   # EOF on stdin — treat like blank: finish and summarize.
  fi

  if [ -z "$name" ]; then
    break
  fi

  # SECURITY: read with echo disabled so the key is NEVER visible in terminal
  # scrollback/tmux history/screen-recording (secrets ratchet — see TICKETS.md
  # ADD-PROVIDER-MECHANIZE-COMPLETE requirement 4b).
  printf 'API key for %s: ' "$name"
  if ! IFS= read -rs key; then
    printf 'add-provider-interactive: no key read (EOF) for "%s" — skipping.\n' "$name"
    SUMMARY+=("$name: SKIPPED (no key entered)")
    continue
  fi

  if [ -z "$key" ]; then
    printf 'add-provider-interactive: empty key for "%s" — skipping.\n' "$name"
    SUMMARY+=("$name: SKIPPED (empty key)")
    continue
  fi

  base_url="${REGISTRY_BASE_URL[$name]:-}"
  if [ -z "$base_url" ]; then
    if [ -v "REGISTRY_BASE_URL[$name]" ]; then
      printf 'add-provider-interactive: WARNING: "%s" is registered but has NO confirmed base_url (see registry TODO comment).\n' "$name" >&2
    else
      printf 'add-provider-interactive: "%s" is not in the registry.\n' "$name"
    fi
    printf 'Base URL for %s (must be http(s)://... , ends in /v1): ' "$name"
    if ! IFS= read -r base_url || [ -z "$base_url" ]; then
      printf 'add-provider-interactive: no base_url entered for "%s" — skipping.\n' "$name"
      SUMMARY+=("$name: SKIPPED (no base_url)")
      continue
    fi
    printf 'add-provider-interactive: WARNING: no registry mappings for "%s" — models will need a manual import/pin pass after this add.\n' "$name" >&2
  fi

  # Resolve funding_class: registry-known or prompt.
  funding_class="${REGISTRY_FUNDING_CLASS[$name]:-}"
  if [ -z "$funding_class" ]; then
    printf 'Funding class for %s (1=free 2=sub 3=drain 4=PAYG) [default=4]: ' "$name"
    if ! IFS= read -r fc_in; then fc_in=""; fi
    funding_class="${fc_in:-4}"
    case "$funding_class" in
      1|2|3|4) ;;
      *) printf 'add-provider-interactive: invalid funding_class "%s" — using 4 (PAYG)\n' "$funding_class" >&2
         funding_class="4" ;;
    esac
  fi

  # Optional: record free-tier rate limits from a JSON file.
  ft_flag=()
  printf 'Free-tier limits file for %s (blank to skip): ' "$name"
  if IFS= read -r ft_path && [ -n "$ft_path" ]; then
    if [ -f "$ft_path" ]; then
      ft_flag=(--free-tier "$ft_path")
    else
      printf 'add-provider-interactive: WARNING: free-tier file not found: %s — skipping\n' "$ft_path" >&2
    fi
  fi

  # shellcheck disable=SC2206 # word-splitting is intentional: registry values
  # are literal "model:upstream" tokens with no embedded whitespace/globs.
  mappings=(${REGISTRY_MODELS[$name]:-})

  keyfile="$(mktemp)"
  chmod 600 "$keyfile"
  printf '%s' "$key" > "$keyfile"
  # Drop the key out of the shell variable as soon as it's on disk in the
  # chmod-600 tempfile; the tempfile itself is removed/shredded right after
  # add-provider.sh consumes it below.
  unset key

  printf 'add-provider-interactive: adding "%s" (base_url=%s, funding_class=%s)...\n' "$name" "$base_url" "$funding_class"
  if "$ADD_PROVIDER" "${DRY_RUN_FLAG[@]}" --funding-class "$funding_class" "${ft_flag[@]+"${ft_flag[@]}"}" "$name" "$base_url" "$keyfile" "${mappings[@]+"${mappings[@]}"}"; then
    printf 'add-provider-interactive: "%s" — SUCCESS\n' "$name"
    SUMMARY+=("$name: SUCCESS")
  else
    printf 'add-provider-interactive: "%s" — FAILED (see add-provider.sh output above)\n' "$name" >&2
    SUMMARY+=("$name: FAILED")
  fi

  cleanup_keyfile
done

print_summary
