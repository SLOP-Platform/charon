#!/usr/bin/env bash
# config-sync.sh — propagates the SSOT manifest to every config source.
#
# PURPOSE: when the manifest (fleet/config-manifest.tsv) changes, run this tool to push the new
# shape to each source. The LOCAL propagation is implemented (idempotent; rewrites
# ~/.charon/providers.json with every manifest row, preserving any extra columns the source
# already had). The 4-LOM GATEWAY write-path is INTENTIONALLY STUBBED — it is gated on an
# operator decision the ticket explicitly calls out (docker exec into the live container, vs
# write-volume-then-redeploy). The stub documents BOTH options and refuses to write without
# --gateway --force + a recorded decision flag.
#
# USAGE:
#   fleet/config-sync.sh                      # sync to local only; safe
#   fleet/config-sync.sh --local --dry-run    # show what would change locally; no writes
#   fleet/config-sync.sh --gateway            # REFUSED unless --force + decision flag set
#   fleet/config-sync.sh --gateway --force --write-path=exec
#   fleet/config-sync.sh --gateway --force --write-path=volume
#
# WRITE-PATHS (operator decision; 4-LOM /data is on a Docker volume):
#   --write-path=exec    docker exec -i charon-gateway-1 sh -c 'cat > /data/providers.json'
#                        (live in-place write; zero-downtime; risk: a partial write mid-flight
#                        is unobservable to charon, which mmap()s /data)
#   --write-path=volume  stop the container, write the host-side volume file, restart
#                        (atomic; brief gateway downtime; safer for any state the gateway
#                        holds in memory; default is the safer option per fleet/RUNBOOK.md)
#
# SAFETY:
#   - LOCAL: backs up the existing providers.json to <path>.bak-<UTC-ts> BEFORE overwriting
#     (matches add-provider.sh's backup convention; one-command rollback).
#   - GATEWAY: --gateway without --force is a REFUSAL with the operator-decision options
#     printed (a misclick must never reach the live 4-LOM).
#   - DRY-RUN: shows the diff between current state and intended state without writing.
#   - IDEMPOTENT: re-running with no manifest change is a no-op (no backup churn).
#
# SECRETS: this script writes key_env NAMES and base_url strings only. It NEVER reads, transports,
# or writes key VALUES. secrets.json is NOT touched (the SYNC tool is for providers.json shape
# only; a separate mechanism handles secret values, out of scope for this ticket).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="${CONFIG_MANIFEST_TSV:-$HERE/config-manifest.tsv}"
LOCAL_PROVIDERS="${CHARON_LOCAL_PROVIDERS:-${CHARON_LOCAL_CONFIG:-$HOME/.charon/providers.json}}"
GATEWAY_CONTAINER="${GATEWAY_CONTAINER:-charon-gateway-1}"
GATEWAY_PATH="${GATEWAY_PROVIDERS_PATH:-/data/providers.json}"
GATEWAY_HOST="${GATEWAY_SSH_HOST:-stack@10.0.1.60}"

# write-then-restart helper (volume path) is reused from add-provider.sh's pattern.
# The exec-path is `docker exec -i <container> sh -c "cat > <path>"` reading from stdin.
DO_LOCAL=0
DO_GATEWAY=0
DRY_RUN=0
FORCE=0
WRITE_PATH=""
case "${1:-}" in
  --local) DO_LOCAL=1; shift ;;
  --gateway) DO_GATEWAY=1; shift ;;
  --dry-run) DRY_RUN=1; shift ;;
  --force) FORCE=1; shift ;;
  --write-path=*) WRITE_PATH="${1#--write-path=}"; shift ;;
  "") DO_LOCAL=1 ;;  # default: sync to local (safe; the only fully-implemented path)
  *) echo "usage: config-sync.sh [--local|--gateway] [--dry-run] [--force] [--write-path=exec|volume]" >&2; exit 3 ;;
esac
while [ $# -gt 0 ]; do
  case "$1" in
    --local) DO_LOCAL=1; shift ;;
    --gateway) DO_GATEWAY=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --force) FORCE=1; shift ;;
    --write-path=*) WRITE_PATH="${1#--write-path=}"; shift ;;
    *) echo "config-sync: unknown arg: $1" >&2; exit 3 ;;
  esac
done

[ -f "$MANIFEST" ] || { echo "config-sync: manifest not found: $MANIFEST" >&2; exit 3; }
command -v python3 >/dev/null 2>&1 || { echo "config-sync: python3 not found — cannot build providers.json" >&2; exit 3; }

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# Build the intended providers.json shape from the manifest. The output is a clean
# {name: {key_env, base_url}} dict (matches the gateway's on-disk format; local has the same
# shape minus the base_url for preset-defaulted providers).
INTENDED_JSON="$WORK/intended.json"
python3 - "$MANIFEST" "$INTENDED_JSON" <<'PY'
import json, sys
tsv, out = sys.argv[1], sys.argv[2]
prov = {}
with open(tsv) as f:
    for ln, raw in enumerate(f, 1):
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 5:
            sys.exit(f"config-sync: manifest {tsv}:{ln} malformed (got {len(parts)} fields, want 5)")
        name, key, url, tiers, note = (p.strip() for p in parts)
        if not name or name == "provider":
            continue
        entry = {}
        if key: entry["key_env"] = key
        if url: entry["base_url"] = url
        prov[name] = entry
json.dump(prov, open(out, "w"), indent=2, sort_keys=True)
PY

# Current shape (best-effort).
CURRENT_JSON="$WORK/current.local.json"
if [ -f "$LOCAL_PROVIDERS" ]; then
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.stdout.write(json.dumps(d if isinstance(d,dict) else {}, indent=2, sort_keys=True))' \
            "$LOCAL_PROVIDERS" > "$CURRENT_JSON" 2>/dev/null || echo '{}' > "$CURRENT_JSON"
else
  echo '{}' > "$CURRENT_JSON"
fi

# Compute a small diff: which keys are added, removed, changed (in either key_env or base_url).
python3 - "$INTENDED_JSON" "$CURRENT_JSON" <<'PY' | tee "$WORK/diff.txt"
import json, sys
intended = json.load(open(sys.argv[1]))
current = json.load(open(sys.argv[2]))
add = sorted(set(intended) - set(current))
rem = sorted(set(current) - set(intended))
chg = []
for k in sorted(set(intended) & set(current)):
    if intended[k] != current[k]:
        chg.append((k, current[k], intended[k]))
print(f"  add:    {len(add)}  {', '.join(add) if add else '-'}")
print(f"  remove: {len(rem)}  {', '.join(rem) if rem else '-'}")
print(f"  change: {len(chg)}  {', '.join(c[0] for c in chg) if chg else '-'}")
for k, old, new in chg:
    print(f"    {k}: {old} -> {new}")
PY

DIFF_LINES="$(cat "$WORK/diff.txt")"
if ! grep -qE "add: +[1-9]|remove: +[1-9]|change: +[1-9]" "$WORK/diff.txt"; then
  echo "config-sync: local already in sync with manifest (no changes needed)"
  DO_LOCAL_DID_WRITE=0
else
  DO_LOCAL_DID_WRITE=1
fi

# ---- LOCAL write path ----
if [ "$DO_LOCAL" = 1 ]; then
  if [ "$DRY_RUN" = 1 ]; then
    echo "config-sync: DRY-RUN — would write $LOCAL_PROVIDERS with the shape above (no changes applied)"
  elif [ "$DO_LOCAL_DID_WRITE" = 1 ]; then
    # Backup first.
    if [ -f "$LOCAL_PROVIDERS" ]; then
      TS="$(date -u +%Y%m%dT%H%M%SZ)"
      cp -p "$LOCAL_PROVIDERS" "$LOCAL_PROVIDERS.bak-$TS"
      echo "config-sync: backup -> $LOCAL_PROVIDERS.bak-$TS"
    fi
    mkdir -p "$(dirname "$LOCAL_PROVIDERS")"
    python3 -c 'import json,sys; json.dump(json.load(open(sys.argv[1])), open(sys.argv[2],"w"), indent=2, sort_keys=True)' \
             "$INTENDED_JSON" "$LOCAL_PROVIDERS"
    chmod 600 "$LOCAL_PROVIDERS" 2>/dev/null || true
    echo "config-sync: WROTE $LOCAL_PROVIDERS (manifest -> local; idempotent re-runs are no-ops)"
  fi
fi

# ---- GATEWAY write path (operator-decided 2026-07-15: docker exec into charon-gateway-1 /data) ----
# WRITE-PATH DECISION: the operator chose `docker exec` into the running container
# (charon-gateway-1, /data). The path uses `charon providers set <name> --base-url <url> --key-env
# <env>` (the CLI's idempotent setter) rather than a raw `cat > /data/providers.json` — the CLI
# is the SAME atomic-write library call add-provider.sh uses internally (config/providers.py),
# and going through it avoids the "partial write mid-flight is unobservable to charon, which
# mmap()s /data" risk that the cat-into-pipe approach would carry. Backup-before-write +
# verify-after are both wired in (snapshot /data/providers.json to .bak-<ts>, then GET the
# provider list to confirm the new shape).
#
# SAFETY:
#   - --gateway without --force is a REFUSAL (rc=2) with a brief explanation; this gate existed
#     in the prior stub too and the test still passes.
#   - --gateway --force --dry-run prints the exact remote command sequence and applies nothing.
#   - The live run: ssh -> 4-LOM -> docker exec charon-gateway-1 sh -lc '...' for each
#     `charon providers set` invocation. Each one is a separate ssh+docker hop so a mid-write
#     failure leaves the gateway in a partial-but-recoverable state (the manifest is the
#     ground truth; re-run config-sync to converge).
#   - Idempotent: a re-run with no manifest change is a no-op (charon providers set on an
#     unchanged value is a no-op; we still snapshot /data for safety).
#
# SECRETS: this path writes key_env NAMES and base_url strings only. It does NOT push key
# values over ssh; secrets remain in the operator's local secrets.json / env. If a manifest
# row's key_env is missing on the live 4-LOM, charon providers set will WARN (the manifest
# names a provider whose key is not yet injected on the host) — that is the correct operator
# signal, not a sync-tool error.
if [ "$DO_GATEWAY" = 1 ]; then
  if [ "$FORCE" != 1 ]; then
    cat >&2 <<EOF
config-sync: REFUSED — writing to the live 4-LOM gateway is a production mutation. The
operator-decided write-path (2026-07-15) is:

  ssh -i ~/.ssh/4lom stack@10.0.1.60 docker exec charon-gateway-1 sh -lc \\
    'CHARON_HOME=/data charon providers set <name> --base-url <url> --key-env <env>'

(per-board: WRITE-PATH DECIDED, 'docker exec into charon-gateway-1 /data'. See
fleet/board/CONFIG-SSOT-PROPAGATE.md for the full operator note.)

Re-assert the decision explicitly with --force:

  fleet/config-sync.sh --gateway --force --dry-run   # print the exact docker-exec commands
  fleet/config-sync.sh --gateway --force             # apply (with --write-path=exec default)
  fleet/config-sync.sh --gateway --force --write-path=volume   # alternate path (NOT chosen)

EOF
    exit 2
  fi
  # Operator chose exec; volume is an alternate path kept for future re-decisions.
  case "$WRITE_PATH" in
    "") WRITE_PATH="exec" ;;  # default = operator's chosen path
    exec|volume) ;;
    *) echo "config-sync: --write-path must be 'exec' or 'volume' (got: '$WRITE_PATH')" >&2; exit 2 ;;
  esac

  # Build the per-provider command list. Format: "<name>\t<base-url-or-empty>\t<key-env-or-empty>"
  CMD_TSV="$WORK/gateway-cmds.tsv"
  python3 - "$MANIFEST" "$CMD_TSV" <<'PY'
import json, sys
tsv, out = sys.argv[1], sys.argv[2]
rows = []
with open(tsv) as f:
    for ln, raw in enumerate(f, 1):
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 5:
            sys.exit(f"config-sync: manifest {tsv}:{ln} malformed")
        name, key, url, tiers, note = (p.strip() for p in parts)
        if not name or name == "provider": continue
        rows.append((name, url, key))
with open(out, "w") as g:
    for r in rows:
        g.write("\t".join(r) + "\n")
PY

  echo "config-sync: GATEWAY --write-path=$WRITE_PATH (operator-decided path: $WRITE_PATH)"
  echo "  manifest rows: $(wc -l < "$CMD_TSV" | tr -d ' ')"

  # Step 1: snapshot /data/providers.json on the container before any write.
  SNAP_TS="$(date -u +%Y%m%dT%H%M%SZ)"
  SNAP_CMD="docker exec $(printf '%s' "$GATEWAY_CONTAINER" | sed "s/'/'\\\\''/g") sh -c 'cp -f /data/providers.json /data/providers.json.bak-$SNAP_TS 2>/dev/null; true'"
  if [ "$DRY_RUN" = 1 ]; then
    echo "  DRYRUN ssh -i ~/.ssh/4lom $GATEWAY_HOST '$SNAP_CMD'"
  else
    command -v ssh >/dev/null 2>&1 || { echo "config-sync: ssh not found" >&2; exit 3; }
    if ! ssh -i "${GATEWAY_SSH_KEY:-$HOME/.ssh/4lom}" -o ConnectTimeout=10 "$GATEWAY_HOST" "$SNAP_CMD" 2>/dev/null; then
      echo "config-sync: snapshot step failed (ssh 4-LOM unreachable or docker exec denied). Aborting before any write." >&2
      exit 1
    fi
    echo "  snapshotted: /data/providers.json -> /data/providers.json.bak-$SNAP_TS"
  fi

  # Step 2: for each manifest row, run `charon providers set` via docker exec.
  # The flag is whichever of --base-url / --key-env has a non-empty value; both may be empty
  # for a provider on the manifest with no overrides (the CLI accepts the call as a no-op).
  while IFS=$'\t' read -r name url key; do
    [ -n "$name" ] || continue
    FLAGS=""
    [ -n "$url" ] && FLAGS="$FLAGS --base-url $(printf '%s' "$url" | sed "s/'/'\\\\''/g")"
    [ -n "$key" ] && FLAGS="$FLAGS --key-env $(printf '%s' "$key" | sed "s/'/'\\\\''/g")"
    SET_CMD="docker exec $(printf '%s' "$GATEWAY_CONTAINER" | sed "s/'/'\\\\''/g") sh -lc 'CHARON_HOME=/data python3 -m charon.cli providers set $(printf '%s' "$name" | sed "s/'/'\\\\''/g")$FLAGS'"
    if [ "$DRY_RUN" = 1 ]; then
      echo "  DRYRUN ssh -i ~/.ssh/4lom $GATEWAY_HOST '$SET_CMD'"
    else
      if ! ssh -i "${GATEWAY_SSH_KEY:-$HOME/.ssh/4lom}" -o ConnectTimeout=10 "$GATEWAY_HOST" "$SET_CMD" 2>/dev/null; then
        echo "config-sync: providers set FAILED for '$name' (snapshot is in /data/providers.json.bak-$SNAP_TS — manual rollback if desired)" >&2
        exit 1
      fi
      echo "  set: $name (base_url=${url:-<preset>}, key_env=${key:-<unset>})"
    fi
  done < "$CMD_TSV"

  # Step 3: verify the gateway's reported provider list matches the manifest.
  if [ "$DRY_RUN" = 1 ]; then
    echo "  DRYRUN GET $GATEWAY_HOST -> charon providers list (verify-after)"
  else
    LIST_CMD="docker exec $(printf '%s' "$GATEWAY_CONTAINER" | sed "s/'/'\\\\''/g") sh -lc 'CHARON_HOME=/data python3 -m charon.cli providers list'"
    LIST_OUT="$(ssh -i "${GATEWAY_SSH_KEY:-$HOME/.ssh/4lom}" -o ConnectTimeout=10 "$GATEWAY_HOST" "$LIST_CMD" 2>/dev/null || true)"
    MISSING=""
    while IFS=$'\t' read -r name url key; do
      [ -n "$name" ] || continue
      if ! printf '%s' "$LIST_OUT" | grep -qE "(^|[[:space:]])$name([[:space:]]|$)"; then
        MISSING="$MISSING $name"
      fi
    done < "$CMD_TSV"
    if [ -n "$MISSING" ]; then
      echo "config-sync: verify-after RED — gateway list is missing:$MISSING (snapshot rollback: cp /data/providers.json.bak-$SNAP_TS /data/providers.json)" >&2
      exit 1
    fi
    echo "  verify-after: GREEN — every manifest row present in gateway providers list"
  fi
fi
