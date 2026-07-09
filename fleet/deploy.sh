#!/usr/bin/env bash
# Fleet-only 4-LOM deploy wrapper. This intentionally lives outside the product
# repo because it carries operator-specific host, ssh-key, and live-state checks.
set -euo pipefail

usage() {
  echo "usage: deploy.sh <tag>" >&2
  echo "example: deploy.sh v0.3.2" >&2
}

TAG="${1:-}"
if [ -z "$TAG" ]; then
  usage
  exit 2
fi

case "$TAG" in
  v[0-9]*.[0-9]*.[0-9]* | v[0-9]*.[0-9]*.[0-9]*-*) ;;
  *)
    echo "deploy: refusing suspicious tag '$TAG' (expected vMAJOR.MINOR.PATCH)" >&2
    exit 2
    ;;
esac

REMOTE_HOST="${CHARON_DEPLOY_HOST:-stack@10.0.1.60}"
SSH_KEY="${CHARON_DEPLOY_SSH_KEY:-$HOME/.ssh/4lom}"
REMOTE_REPO="${CHARON_DEPLOY_REPO:-/home/stack/charon}"
IMAGE_REPO="${CHARON_DEPLOY_IMAGE:-ghcr.io/slop-platform/charon}"
CONTAINER="${CHARON_DEPLOY_CONTAINER:-charon-gateway-1}"
SERVICE="${CHARON_DEPLOY_SERVICE:-gateway}"
# 50 pools live as of 2026-07-09 cline-wire — the +1 grok-4.3 frontier pool add left
# the total at 50 (mimo-v2.5 wiring was reverted, net zero on the 5 pre-existing
# cheap-first pools). Bump this if the live pool set intentionally grows/shrinks.
EXPECTED_POOL_COUNT="${CHARON_DEPLOY_POOL_COUNT:-50}"
# CLINE_PASS_API_KEY is now load-bearing: cline-pass is the cheap-first (drain-first)
# leg on 5 pools (glm-5.2, kimi-k2.6, deepseek-v4-pro/-flash, minimax-m3-free), so a
# missing key would silently drop cheap-first routing to spill. Guard it like the rest.
REQUIRED_KEY_ENVS="${CHARON_DEPLOY_REQUIRED_KEYS:-NANOGPT_API_KEY,GROQ_API_KEY,CEREBRAS_API_KEY,MISTRAL_API_KEY,TOGETHER_API_KEY,OPENROUTER_API_KEY,NEURALWATT_API_KEY,DEEPSEEK_API_KEY,OPENCODE_ZEN_KEY,CLINE_PASS_API_KEY}"

if [ ! -r "$SSH_KEY" ]; then
  echo "deploy: ssh key not readable: $SSH_KEY" >&2
  exit 2
fi

echo "deploy: target=$REMOTE_HOST repo=$REMOTE_REPO image=$IMAGE_REPO:$TAG"
echo "deploy: remote backup of /data will be created before any image change"

remote_env=(
  "TAG=$TAG"
  "IMAGE_REPO=$IMAGE_REPO"
  "REMOTE_REPO=$REMOTE_REPO"
  "CONTAINER=$CONTAINER"
  "SERVICE=$SERVICE"
  "EXPECTED_POOL_COUNT=$EXPECTED_POOL_COUNT"
  "REQUIRED_KEY_ENVS=$REQUIRED_KEY_ENVS"
)
remote_prefix=""
for env_pair in "${remote_env[@]}"; do
  printf -v quoted '%q' "$env_pair"
  remote_prefix+="$quoted "
done

ssh -i "$SSH_KEY" "$REMOTE_HOST" \
  "env ${remote_prefix}bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

log() { printf 'deploy: %s\n' "$*"; }
fail() { printf 'deploy: ERROR: %s\n' "$*" >&2; exit 1; }

cd "$REMOTE_REPO"

command -v docker >/dev/null 2>&1 || fail "docker is not installed on remote host"
[ -f docker-compose.yml ] || fail "missing docker-compose.yml in $REMOTE_REPO"
docker compose version >/dev/null 2>&1 || fail "docker compose plugin is unavailable"
docker inspect "$CONTAINER" >/dev/null 2>&1 || fail "container $CONTAINER does not exist"

current_image="$(docker inspect "$CONTAINER" --format '{{.Config.Image}}')"
previous_tag="${current_image##*:}"
if [ -z "$previous_tag" ] || [ "$previous_tag" = "$current_image" ]; then
  fail "cannot derive previous tag from image '$current_image'"
fi

data_volume="$(docker inspect "$CONTAINER" --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}')"
[ -n "$data_volume" ] || fail "container $CONTAINER has no named /data volume"

backup_root="$REMOTE_REPO/.charon-deploy-backups"
mkdir -p "$backup_root"
chmod 700 "$backup_root"
backup="$backup_root/data-$(date -u +%Y%m%dT%H%M%SZ)-$previous_tag-to-$TAG.tar"

override="$REMOTE_REPO/.charon-deploy.override.yml"
headers="$(mktemp)"
body="$(mktemp)"
trap 'rm -f "$headers" "$body"' EXIT

write_override() {
  local image_tag="$1"
  cat > "$override" <<YAML
services:
  gateway:
    image: ${IMAGE_REPO}:${image_tag}
  charon-service:
    image: ${IMAGE_REPO}:${image_tag}
YAML
}

compose() {
  docker compose -f docker-compose.yml -f "$override" "$@"
}

backup_data() {
  log "backing up /data volume '$data_volume' to $backup"
  docker run --rm --entrypoint sh -v "$data_volume:/data:ro" "$current_image" -c 'tar -C /data -cpf - .' > "$backup"
  chmod 600 "$backup"
  [ -s "$backup" ] || fail "backup is empty: $backup"
}

restore_data() {
  local image_tag="$1"
  log "restoring /data from $backup"
  docker run --rm -i --entrypoint sh -v "$data_volume:/data" "${IMAGE_REPO}:${image_tag}" -c \
    'set -e; find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} +; tar -C /data -xpf -' < "$backup"
}

wait_healthy() {
  local i status
  for i in $(seq 1 40); do
    status="$(docker inspect "$CONTAINER" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)"
    [ "$status" = "healthy" ] && return 0
    sleep 3
  done
  docker inspect "$CONTAINER" --format '{{json .State}}' >&2 || true
  return 1
}

pool_count() {
  docker exec -i "$CONTAINER" python3 - <<'PY'
import json
with open('/data/pools.json', encoding='utf-8') as f:
    print(len(json.load(f)))
PY
}

token() {
  docker exec "$CONTAINER" printenv CHARON_GATEWAY_TOKEN
}

verify_keys_present() {
  docker exec -i -e REQUIRED_KEY_ENVS="$REQUIRED_KEY_ENVS" "$CONTAINER" python3 - <<'PY'
import json
import os
import sys

required = [k for k in os.environ['REQUIRED_KEY_ENVS'].split(',') if k]
with open('/data/secrets.json', encoding='utf-8') as f:
    secrets = json.load(f)
missing = [k for k in required if not secrets.get(k)]
if missing:
    print('missing key envs: ' + ','.join(missing), file=sys.stderr)
    sys.exit(1)
print('keys_present=' + str(len(required)))
PY
}

verify_deepseek_provider() {
  local t provider nonce probe_body
  t="$(token)"
  [ -n "$t" ] || fail "CHARON_GATEWAY_TOKEN is empty in $CONTAINER"
  # Per-call nonce so each probe is a unique raw body -> cache MISS (real
  # upstream call), never a stale X-Charon-Provider: cache hit. Re-evaluated
  # on every invocation because it is built inside this function.
  nonce="$(date +%s%N)-$RANDOM"
  probe_body="{\"model\":\"deepseek-v4-pro\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with ok.\"}],\"max_tokens\":1,\"user\":\"charon-deploy-verify-${nonce}\"}"
  curl -fsS -D "$headers" -o "$body" \
    -H "Authorization: Bearer $t" \
    -H 'Content-Type: application/json' \
    -X POST 'http://127.0.0.1:8080/v1/chat/completions' \
    -d "$probe_body"
  provider="$(python3 - "$headers" <<'PY'
import sys
for line in open(sys.argv[1], encoding='utf-8', errors='replace'):
    if line.lower().startswith('x-charon-provider:'):
        print(line.split(':', 1)[1].strip().lower())
        break
PY
)"
  # 2026-07-09 cline-wire: cline-pass is now the cheap-first (drain-first) leg on the
  # deepseek-v4-pro pool (order: cline,ng,ds,or). nanogpt/deepseek/openrouter remain
  # BELOW it as spill/backstop. A fresh (uncached) probe must therefore route to
  # cline-pass; getting nanogpt back means the cheap-first leg silently dropped.
  [ "$provider" = "cline-pass" ] || fail "deepseek-v4-pro provider changed: expected cline-pass (cheap-first leg), got '${provider:-missing}'"
  log "deepseek-v4-pro provider remains cline-pass (nanogpt/ds/or spill below)"
}

verify_all() {
  local pools_after="$1"
  wait_healthy || fail "$CONTAINER did not become healthy"
  [ "$(pool_count)" = "$pools_after" ] || fail "pool count changed after deploy"
  verify_keys_present >/dev/null
  verify_deepseek_provider
}

rollback() {
  local rc=$?
  trap - ERR
  log "failure detected; rolling back to $previous_tag and restoring /data backup"
  set +e
  write_override "$previous_tag"
  docker pull "${IMAGE_REPO}:${previous_tag}"
  compose stop "$SERVICE"
  restore_data "$previous_tag"
  compose up -d "$SERVICE"
  wait_healthy
  verify_all "$pools_before"
  rollback_rc=$?
  set -e
  if [ "$rollback_rc" -eq 0 ]; then
    log "rollback complete; original failure exit=$rc"
  else
    log "ROLLBACK VERIFY FAILED; backup remains at $backup"
  fi
  exit "$rc"
}

pools_before="$(pool_count)"
[ "$pools_before" = "$EXPECTED_POOL_COUNT" ] || fail "preflight pool count is $pools_before, expected $EXPECTED_POOL_COUNT"
verify_keys_present >/dev/null
verify_deepseek_provider
backup_data

trap rollback ERR

log "pulling ${IMAGE_REPO}:${TAG}"
docker pull "${IMAGE_REPO}:${TAG}"
write_override "$TAG"
compose pull "$SERVICE"
compose up -d "$SERVICE"
verify_all "$pools_before"

trap - ERR
log "deploy complete: $previous_tag -> $TAG"
log "backup retained at $backup"
REMOTE_SCRIPT
