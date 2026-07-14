#!/usr/bin/env bash
# fleet/add-provider.sh — ONE command to add a provider to the LIVE Charon gateway
# (ADD-PROVIDER-MECHANIZE). Ends the "reverse-engineer .60/CLI/keys plumbing every
# session" problem: everything below is the grounded, tested sequence.
#
# usage: fleet/add-provider.sh [--dry-run] <name> <base_url> <local-key-file> [model:upstream ...]
#
#   <name>            provider id (letters/digits/_/-  only)
#   <base_url>        OpenAI-compatible base URL, http(s) only, ends in /v1
#   <local-key-file>  a LOCAL file holding the raw API key — read once, NEVER
#                     placed on argv / in `ps` / in any log. Piped over stdin
#                     through ssh -> `docker exec -i ... providers add` -> the
#                     CLI's no-echo getpass prompt (falls back to reading stdin
#                     when there is no controlling tty, which is exactly the
#                     `docker exec -i` case).
#   model:upstream    optional gateway-name:upstream-model-id pairs; ensures each
#                     exists in the catalog with that upstream_model + a cost_rank.
#
# Steps (fail-loud on any of them):
#   1. back up /data/providers.json + /data/models.json to *.bak-<UTC-ts>
#   2. `charon.cli providers add <name> --base-url <url>` (key via stdin, never argv)
#   3. `charon.cli models import <name>` (+ ensure any model:upstream mappings)
#   4. `charon.cli providers test <name>`
#   5. `docker restart charon-gateway-1` (WARNS — does not check — for an in-flight
#      fleet build; that's the caller's responsibility, per ticket)
#   6. verify the new models are visible via GET /v1/models (bearer token read from
#      the local opencode.json, never printed)
#
# Idempotent: every step re-applies cleanly on re-run (config.add_provider/add_model
# merge; models import re-adds the same catalog; a second restart is harmless).
#
# Testing: --dry-run prints the exact remote command sequence and performs NO ssh/
# docker/network calls at all — see fleet/tests/test_add_provider.sh.
set -uo pipefail

usage() {
  cat >&2 <<'USAGE'
usage: add-provider.sh [--dry-run] <name> <base_url> <local-key-file> [model:upstream ...]
example: add-provider.sh myprov https://api.example.com/v1 ~/.secrets/myprov.key phi-4:microsoft/phi-4
USAGE
}

# --- config (env-overridable for testing / alternate hosts) -------------------
SSH_KEY="${ADD_PROVIDER_SSH_KEY:-$HOME/.ssh/4lom}"
SSH_HOST="${ADD_PROVIDER_SSH_HOST:-stack@10.0.1.60}"
CONTAINER="${ADD_PROVIDER_CONTAINER:-charon-gateway-1}"
GATEWAY_URL="${ADD_PROVIDER_GATEWAY_URL:-http://10.0.1.60:8080}"
OPENCODE_CONFIG="${ADD_PROVIDER_OPENCODE_CONFIG:-$HOME/.config/opencode/opencode.json}"
DEFAULT_COST_RANK="${ADD_PROVIDER_DEFAULT_COST_RANK:-50}"

log()  { printf 'add-provider: %s\n' "$*"; }
warn() { printf 'add-provider WARNING: %s\n' "$*" >&2; }
fail() { printf 'add-provider ERROR: %s\n' "$*" >&2; exit 1; }

# POSIX-safe single-quote a value for embedding in the remote shell command string
# (defense in depth: base_url/model/upstream are operator-supplied but every value
# that reaches the remote command line goes through this — no unquoted interpolation).
_shq() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }

# --- arg parsing ---------------------------------------------------------------
DRY_RUN=0
args=()
for a in "$@"; do
  case "$a" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) args+=("$a") ;;
  esac
done
set -- "${args[@]+"${args[@]}"}"

[ $# -ge 3 ] || { usage; exit 2; }
NAME="$1"; BASE_URL="$2"; KEYFILE="$3"; shift 3 || true
MAPPINGS=("$@")

case "$NAME" in
  [A-Za-z0-9]*) ;;
  *) fail "provider name must start with a letter/digit: '$NAME'" ;;
esac
case "$NAME" in
  *[!A-Za-z0-9_-]*) fail "provider name has invalid characters (allowed: A-Za-z0-9_-): '$NAME'" ;;
esac
case "$BASE_URL" in
  http://*|https://*) ;;
  *) fail "base_url must be http(s)://... , got: '$BASE_URL'" ;;
esac
case "$BASE_URL" in
  *169.254.*|*metadata.google.internal*) fail "refusing link-local/metadata base_url: '$BASE_URL'" ;;
esac
[ -f "$KEYFILE" ] || fail "key file not found: $KEYFILE"
[ -s "$KEYFILE" ] || fail "key file is empty: $KEYFILE"

for m in "${MAPPINGS[@]+"${MAPPINGS[@]}"}"; do
  case "$m" in
    *:*) ;;
    *) fail "model mapping must be 'model:upstream', got: '$m'" ;;
  esac
done

# --- remote execution (single choke point; --dry-run never touches the network) -
# _remote <remote-shell-command> [stdin-file]
#   No stdin-file  -> remote command runs with stdin from /dev/null (never lets a
#                     stray prompt hang the script on a non-interactive shell).
#   stdin-file     -> that file's bytes are piped through ssh -> the remote
#                     command's stdin (used ONLY for the key, in step 2).
_remote() {
  local cmd="$1" stdin_file="${2:-}"
  if [ "$DRY_RUN" -eq 1 ]; then
    if [ -n "$stdin_file" ]; then
      local nbytes; nbytes="$(wc -c < "$stdin_file" | tr -d ' ')"
      log "DRYRUN ssh -i $SSH_KEY -o ConnectTimeout=10 $SSH_HOST '$cmd'   [stdin: <redacted, ${nbytes} bytes from $stdin_file>]"
    else
      log "DRYRUN ssh -i $SSH_KEY -o ConnectTimeout=10 $SSH_HOST '$cmd'"
    fi
    return 0
  fi
  if [ -n "$stdin_file" ]; then
    ssh -i "$SSH_KEY" -o ConnectTimeout=10 "$SSH_HOST" "$cmd" < "$stdin_file"
  else
    ssh -i "$SSH_KEY" -o ConnectTimeout=10 "$SSH_HOST" "$cmd" < /dev/null
  fi
}

# --- step 1: backup -------------------------------------------------------------
TS="$(date -u +%Y%m%dT%H%M%SZ)"
backup_cmd="docker exec $(_shq "$CONTAINER") sh -c 'cp -f /data/providers.json /data/providers.json.bak-$TS 2>/dev/null; cp -f /data/models.json /data/models.json.bak-$TS 2>/dev/null; true'"
log "step 1/6: backing up /data/{providers,models}.json -> *.bak-$TS"
_remote "$backup_cmd" || fail "backup step failed"

# --- step 2: providers add (key over stdin, never argv) -------------------------
add_cmd="docker exec -i $(_shq "$CONTAINER") python3 -m charon.cli providers add $(_shq "$NAME") --base-url $(_shq "$BASE_URL")"
log "step 2/6: providers add $NAME (key piped via stdin — never appears on argv/ps/logs)"
_remote "$add_cmd" "$KEYFILE" || fail "providers add failed for '$NAME'"

# --- step 3: models import + explicit model:upstream mappings -------------------
import_cmd="docker exec $(_shq "$CONTAINER") python3 -m charon.cli models import $(_shq "$NAME")"
log "step 3/6: models import $NAME"
_remote "$import_cmd" || fail "models import failed for '$NAME'"

for m in "${MAPPINGS[@]+"${MAPPINGS[@]}"}"; do
  model="${m%%:*}"
  upstream="${m#*:}"
  # config.add_model is the SAME atomic-write library call `charon.cli` uses
  # internally (config/models.py) — not a hand-edit of models.json. There is no
  # dedicated `models add` subcommand for a single explicit upstream_model
  # mapping, so this is the correct, non-JSON-hand-editing way to set one.
  # model/upstream/provider/cost_rank ride in as sys.argv (never interpolated
  # into the python source) so there is no quoting/injection hazard either way.
  map_cmd="docker exec $(_shq "$CONTAINER") python3 -c \"import sys; from charon import config; config.add_model(sys.argv[1], provider=sys.argv[2], upstream_model=sys.argv[3], cost_rank=int(sys.argv[4]))\" $(_shq "$model") $(_shq "$NAME") $(_shq "$upstream") $(_shq "$DEFAULT_COST_RANK")"
  log "step 3b: ensuring model '$model' -> upstream '$upstream' (provider=$NAME, cost_rank=$DEFAULT_COST_RANK)"
  _remote "$map_cmd" || fail "model mapping failed for '$model:$upstream'"
done

# --- step 4: providers test ------------------------------------------------------
test_cmd="docker exec $(_shq "$CONTAINER") python3 -m charon.cli providers test $(_shq "$NAME")"
log "step 4/6: providers test $NAME"
_remote "$test_cmd" || fail "providers test reports '$NAME' unreachable — check base_url/network before restarting"

# --- step 5: restart --------------------------------------------------------------
warn "about to restart $CONTAINER — verify no fleet build is currently in flight on this host before proceeding (this script does not check that for you)"
restart_cmd="docker restart $(_shq "$CONTAINER")"
log "step 5/6: docker restart $CONTAINER"
_remote "$restart_cmd" || fail "docker restart failed for '$CONTAINER'"

# --- step 6: verify via GET /v1/models -------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
  log "step 6/6: DRYRUN GET $GATEWAY_URL/v1/models (bearer token from $OPENCODE_CONFIG, redacted)"
  log "add-provider: DRY-RUN complete for '$NAME' — no ssh/docker/network calls were made"
  exit 0
fi

log "step 6/6: verifying models are live via GET $GATEWAY_URL/v1/models"
[ -f "$OPENCODE_CONFIG" ] || fail "opencode config not found (needed for the gateway bearer token): $OPENCODE_CONFIG"
TOKEN="$(python3 - "$OPENCODE_CONFIG" <<'PY'
import json, os, sys
cfg = json.load(open(sys.argv[1], encoding="utf-8"))
opts = (((cfg.get("provider") or {}).get("charon") or {}).get("options") or {})
key = opts.get("apiKey", "") or ""
if key.startswith("{env:") and key.endswith("}"):
    key = os.environ.get(key[5:-1], "")
elif key.startswith("{file:") and key.endswith("}"):
    p = os.path.expanduser(key[6:-1])
    key = open(p, encoding="utf-8").read().strip() if os.path.isfile(p) else ""
print(key)
PY
)"
[ -n "$TOKEN" ] || fail "could not resolve a charon gateway apiKey from $OPENCODE_CONFIG"

# small wait for the container to come back healthy after the restart.
ok=0
for _ in $(seq 1 20); do
  if printf 'header = "Authorization: Bearer %s"\n' "$TOKEN" \
       | curl -sS -m 5 -o /dev/null -w '%{http_code}' -K - \
       "$GATEWAY_URL/v1/models" 2>/dev/null | grep -q '^200$'; then
    ok=1
    break
  fi
  sleep 3
done
[ "$ok" -eq 1 ] || fail "gateway did not come back healthy (GET /v1/models never returned 200) after restart"

MODELS_JSON="$(printf 'header = "Authorization: Bearer %s"\n' "$TOKEN" | curl -sS -m 10 -K - "$GATEWAY_URL/v1/models")"
present=0
for m in "${MAPPINGS[@]+"${MAPPINGS[@]}"}"; do
  model="${m%%:*}"
  printf '%s' "$MODELS_JSON" | grep -qF "\"$model\"" && present=$((present + 1))
done
if [ "${#MAPPINGS[@]}" -gt 0 ] && [ "$present" -ne "${#MAPPINGS[@]}" ]; then
  fail "not all requested models are visible in GET /v1/models yet ($present/${#MAPPINGS[@]})"
fi

log "add-provider: '$NAME' added, imported, tested, restarted, and verified live."
