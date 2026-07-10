#!/usr/bin/env bash
# Fleet-only 4-LOM deploy wrapper. This intentionally lives outside the product
# repo because it carries operator-specific host, ssh-key, and live-state checks.
set -euo pipefail

usage() {
  echo "usage: deploy.sh <tag>" >&2
  echo "       deploy.sh --selftest   # exercise the key-env derivation, no ssh/deploy" >&2
  echo "example: deploy.sh v0.3.2" >&2
}

# --- Shared key-presence check -------------------------------------------------
# One program, used both in-container (against /data) by verify_keys_present and
# locally by --selftest (against a fixture). The set of REQUIRED key-envs is
# DERIVED from the live routing config so a provider added to a pool can never be
# silently dropped from the presence check:
#   * pools.json  -> {role: [model_id,...]}                (which models are live)
#   * tiers.json  -> {"members": {vid: [model_id,...]}}    (tier members, same)
#   * models.json -> {model_id: {..., key_env|provider}}   (model -> key_env)
# key_env resolves as the gateway itself resolves it (charon.routing_policy):
#   spec["key_env"]  OR  charon.providers.resolve(spec["provider"]).key_env
# REQUIRED_KEY_ENVS is kept only as a NON-REDUCING FLOOR (e.g. global fallback
# providers such as NeuralWatt that live in no pool): the effective requirement is
# floor UNION derived, so this is strictly at least as strict as the old hand list
# and additionally catches drift. Derivation errors fail SAFE to floor-only.
KEY_CHECK_PY="$(cat <<'PYEOF'
import json, os, sys

state_dir = os.environ.get("CHARON_STATE_DIR", "/data")
secrets_path = os.environ.get("CHARON_SECRETS") or os.path.join(state_dir, "secrets.json")
floor = [k for k in os.environ.get("REQUIRED_KEY_ENVS", "").split(",") if k]


def _load(name):
    try:
        with open(os.path.join(state_dir, name), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _preset_key_env(prov):
    # Authoritative provider -> key_env, via charon's own preset table when the
    # package is importable (it is, inside the gateway container). No hand copy.
    try:
        from charon import providers as P
        return P.resolve(prov).key_env
    except Exception:
        return None


def derive():
    registry = _load("models.json")
    registry = registry if isinstance(registry, dict) else {}
    model_ids = set()
    pools = _load("pools.json")
    if isinstance(pools, dict):
        for members in pools.values():
            if isinstance(members, list):
                model_ids.update(m for m in members if isinstance(m, str))
    tiers = _load("tiers.json")
    tmembers = tiers.get("members") if isinstance(tiers, dict) else None
    if isinstance(tmembers, dict):
        for members in tmembers.values():
            if isinstance(members, list):
                model_ids.update(m for m in members if isinstance(m, str))
    req = set()
    for mid in model_ids:
        spec = registry.get(mid)
        if not isinstance(spec, dict):
            continue
        ke = spec.get("key_env")
        if not ke and spec.get("provider"):
            ke = _preset_key_env(spec["provider"])
        if ke:
            req.add(ke)
    return req


required = set(floor)
derived = set()
try:
    derived = derive()
except Exception as exc:  # fail-safe: never LESS strict than the hand floor
    print("deploy: WARN key-env derivation skipped (%s); using floor only" % exc,
          file=sys.stderr)
required |= derived

with open(secrets_path, encoding="utf-8") as f:
    secrets = json.load(f)
missing = sorted(k for k in required if not secrets.get(k))
if missing:
    print("missing key envs: " + ",".join(missing), file=sys.stderr)
    sys.exit(1)
print("keys_present=%d (floor=%d derived=%d)" % (len(required), len(floor), len(derived)))
PYEOF
)"

run_selftest() {
  local tmp out rc
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  cat > "$tmp/models.json" <<'JSON'
{
  "drift-model":   {"agent": "opencode", "key_env": "CHARON_SELFTEST_DRIFT_KEY"},
  "covered-model": {"agent": "opencode", "key_env": "CHARON_SELFTEST_COVERED_KEY"}
}
JSON
  cat > "$tmp/pools.json" <<'JSON'
{"coder": ["drift-model", "covered-model"]}
JSON
  # secrets carry the covered key but NOT the drifted pool provider's key, and the
  # FLOOR is deliberately empty so ONLY the derivation can flag the drift.
  cat > "$tmp/secrets.json" <<'JSON'
{"CHARON_SELFTEST_COVERED_KEY": "present"}
JSON

  echo "selftest: case 1 — a pool provider whose key-env is unset must be FLAGGED"
  set +e
  out="$(printf '%s' "$KEY_CHECK_PY" | CHARON_STATE_DIR="$tmp" REQUIRED_KEY_ENVS="" python3 - 2>&1)"
  rc=$?
  set -e
  if [ "$rc" -eq 0 ]; then
    echo "selftest FAIL: derivation did not flag the drifted key" >&2
    echo "  (this is exactly what a revert to the hand-maintained list would do)" >&2
    echo "  output: $out" >&2
    return 1
  fi
  case "$out" in
    *CHARON_SELFTEST_DRIFT_KEY*) : ;;
    *) echo "selftest FAIL: failure did not name the drifted key: $out" >&2; return 1 ;;
  esac
  echo "selftest: case 1 ok -> $out"

  echo "selftest: case 2 — with that key present the check must PASS"
  cat > "$tmp/secrets.json" <<'JSON'
{"CHARON_SELFTEST_COVERED_KEY": "present", "CHARON_SELFTEST_DRIFT_KEY": "present"}
JSON
  set +e
  out="$(printf '%s' "$KEY_CHECK_PY" | CHARON_STATE_DIR="$tmp" REQUIRED_KEY_ENVS="" python3 - 2>&1)"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    echo "selftest FAIL: keys present but check still failed: $out" >&2
    return 1
  fi
  echo "selftest: case 2 ok -> $out"
  echo "selftest: PASS"
}

if [ "${1:-}" = "--selftest" ]; then
  run_selftest
  exit $?
fi

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
# REQUIRED_KEY_ENVS is now a NON-REDUCING FLOOR only — the live requirement is this
# list UNION the set derived from pools.json/tiers.json/models.json by KEY_CHECK_PY
# (see above). Keep here only key-envs that live in NO pool/tier and so cannot be
# derived — chiefly global fallback providers (e.g. NeuralWatt). A provider added to
# a pool no longer needs a hand-edit here: its key is required automatically. (Before,
# the CLINE_PASS_API_KEY comment documented exactly the miss this derivation closes.)
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
  "KEY_CHECK_PY=$KEY_CHECK_PY"
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
  # Effective requirement = REQUIRED_KEY_ENVS floor UNION the set derived from the
  # live routing config in /data (pools/tiers/models). KEY_CHECK_PY is the SAME
  # program --selftest exercises, so a fixture proves it flags a drifted key.
  printf '%s' "$KEY_CHECK_PY" | docker exec -i \
    -e REQUIRED_KEY_ENVS="$REQUIRED_KEY_ENVS" \
    -e CHARON_STATE_DIR=/data \
    -e CHARON_SECRETS=/data/secrets.json \
    "$CONTAINER" python3 -
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
